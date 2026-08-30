from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INVENTORY_GLOB='2026-08-26_library_screenshot_shard_*.jsonl'
OCCURRENCE_GLOB='*_library_screenshot_text_occurrences_*.jsonl'

def canonical_text_sha256(path:Path)->str:
    text=path.read_text(encoding='utf-8-sig',errors='replace')
    canonical=text.replace('\r\n','\n').replace('\r','\n').encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()

def _load_jsonl(path:Path)->list[dict]:
    return [json.loads(x) for x in path.read_text(encoding='utf-8-sig').splitlines() if x.strip()]

def _rows(root:Path=ROOT):
    out=[]
    for p in sorted((root/'02 Evidence').glob(INVENTORY_GLOB)):
        for n,r in enumerate(_load_jsonl(p),1):
            r['_inventory']=p.name; r['_line']=n; r.setdefault('occurrence_id',r.get('file_id')); out.append(r)
    for p in sorted((root/'02 Evidence').glob(OCCURRENCE_GLOB)):
        for n,r in enumerate(_load_jsonl(p),1):
            r['_inventory']=p.name; r['_line']=n; out.append(r)
    seen=set(); unique=[]
    for r in sorted(out,key=lambda r:(r.get('created_at_utc',''),r.get('occurrence_id') or r.get('file_id') or '')):
        key=r.get('occurrence_id') or r.get('file_id')
        if key in seen: continue
        seen.add(key); unique.append(r)
    return unique

def _text(row:dict, root:Path=ROOT)->str:
    p=row.get('text_path')
    if not p:
        return ''
    allowed=(root/'02 Evidence'/'library_screenshot_text').resolve()
    q=(root/p).resolve()
    if q != allowed and allowed not in q.parents:
        return ''
    return q.read_text(encoding='utf-8-sig',errors='replace') if q.is_file() else ''

def _tokens(s:str)->list[str]: return re.findall(r'[\w.-]+',s.casefold(),flags=re.UNICODE)
def searchable(row:dict, root:Path=ROOT)->str: return ' '.join([str(row.get('subject','')),' '.join(map(str,row.get('tags',[]))),_text(row,root)]).casefold()
def excerpt(text:str, query:str, width:int=240)->str:
    flat=' '.join(text.split()); low=flat.casefold(); toks=_tokens(query); pos=min([low.find(t) for t in toks if low.find(t)>=0] or [0]); a=max(0,pos-width//3); return flat[a:min(len(flat),a+width)]
def search(query:str, *, context:int=2, limit:int=5, root:Path=ROOT)->dict:
    rows=_rows(root); toks=_tokens(query); matches=[]
    for i,r in enumerate(rows):
        hay=searchable(r,root); score=sum(1 for t in toks if t in hay)
        if toks and score==0: continue
        matches.append((score,i,r))
    matches.sort(key=lambda x:(x[0],x[2].get('created_at_utc','')),reverse=True)
    def mini(x): return {'timestamp':x.get('created_at_utc'),'occurrence_id':x.get('occurrence_id'),'file_id':x.get('file_id') or x.get('library_file_id'),'filename':x.get('filename'),'subject':x.get('subject')}
    compact=[]
    for score,i,r in matches[:limit]:
        compact.append({'timestamp':r.get('created_at_utc'),'occurrence_id':r.get('occurrence_id'),'file_id':r.get('file_id') or r.get('library_file_id'),'filename':r.get('filename'),'subject':r.get('subject'),'classification':r.get('classification'),'review_status':r.get('review_status'),'score':score,'text_excerpt':excerpt(_text(r,root),query),'before':[mini(x) for x in rows[max(0,i-context):i]],'after':[mini(x) for x in rows[i+1:i+1+context]]})
    return {'query':query,'occurrence_count':len(matches),'indexed_occurrences':len(rows),'returned':len(compact),'matches':compact}
def main()->int:
    p=argparse.ArgumentParser(description='Search timestamped screenshot occurrence text with temporal neighbors and frequency counts'); p.add_argument('query'); p.add_argument('--context',type=int,default=2); p.add_argument('--limit',type=int,default=5); a=p.parse_args(); print(json.dumps(search(a.query,context=max(0,a.context),limit=max(1,a.limit)),ensure_ascii=False,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
