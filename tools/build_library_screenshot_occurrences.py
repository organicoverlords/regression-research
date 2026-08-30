from __future__ import annotations
import argparse, hashlib, json, re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TEXT_ROOT=ROOT/'02 Evidence'/'library_screenshot_text'
OUT=ROOT/'02 Evidence'/'2026-08-26_library_screenshot_text_occurrences_001.jsonl'
LOCAL_TZ=timezone(timedelta(hours=3))  # Finland EEST for this bounded May 2026 corpus window
FILENAME_TS=re.compile(r'^Näyttökuva (\d{4}-\d{2}-\d{2}) (\d{6})(?:\(\d+\))?$')
SECRET_PATTERNS=[
    re.compile(r'(?i)\bsk-[A-Za-z0-9_-]{12,}\b'),
    re.compile(r'(?i)\b(?:ghp_[A-Za-z0-9]{12,}|github_pat_[A-Za-z0-9_]{12,})\b'),
    re.compile(r'(?i)\bfreellmapi-[A-Za-z0-9_-]{12,}\b'),
    re.compile(r'(?i)((?:api[_ -]?key|access[_ -]?token|private[_ -]?token|password)\s*[:=]\s*["\']?)([^\s"\']{12,})'),
]
TAG_RULES={
 'router':['router','routing','fallback','gigapi','freellmapi'],
 'tool':['tool','tool-call','tool call'],
 'error':['error','failed','failure','invalid'],
 'model':['model','provider','nvidia','mistral','nemotron','llama','deepseek'],
 'agent':['agent','chatgpt','codex','hermes','qwen'],
 'git':['git','branch','commit','pull request','pr '],
 'ui':['browser','ui','workspace','dashboard'],
}
EXTRA_PAGE2={'Näyttökuva 2026-05-26 014950(1).txt','Näyttökuva 2026-05-26 020534.txt','Näyttökuva 2026-05-26 020609.txt','Näyttökuva 2026-05-26 020611.txt'}

def scrub(text:str)->tuple[str,int]:
    total=0
    for rx in SECRET_PATTERNS:
        def repl(m):
            nonlocal total
            if rx.groups >= 2 and m.group(2) == '[REDACTED_CREDENTIAL]':
                return m.group(0)
            total += 1
            return (m.group(1)+'[REDACTED_CREDENTIAL]') if rx.groups>=2 else '[REDACTED_CREDENTIAL]'
        text=rx.sub(repl,text)
    return text,total

def timestamp_for(path:Path)->tuple[str,str]:
    m=FILENAME_TS.match(path.stem)
    if not m: raise ValueError(f'unparseable screenshot timestamp: {path.name}')
    local=datetime.strptime(' '.join(m.groups()),'%Y-%m-%d %H%M%S').replace(tzinfo=LOCAL_TZ)
    return local.isoformat(), local.astimezone(timezone.utc).isoformat().replace('+00:00','Z')

def tags_for(text:str)->list[str]:
    low=text.casefold(); return [tag for tag,needles in TAG_RULES.items() if any(n in low for n in needles)]

def build(root:Path=ROOT)->dict:
    rows=[]; redactions=0
    for page in ('page2','page3'):
        for p in sorted((root/'02 Evidence'/'library_screenshot_text'/page).glob('*.txt')):
            text=p.read_text(encoding='utf-8-sig',errors='replace')
            clean,n=scrub(text); redactions+=n
            if clean!=text: p.write_text(clean,encoding='utf-8')
            local,utc=timestamp_for(p)
            rel=p.relative_to(root).as_posix()
            oid='shot-'+hashlib.sha256((p.name+'|'+local).encode('utf-8')).hexdigest()[:20]
            reviewed=(page=='page2' and p.name not in EXTRA_PAGE2)
            lead=' '.join(clean.split())[:220]
            rows.append({
              'occurrence_id':oid,'library_file_id':None,'library_file_id_status':'PENDING_BACKFILL',
              'filename':p.name[:-4]+'.png','capture_time_local':local,'created_at_utc':utc,
              'timestamp_source':'SCREENSHOT_FILENAME','text_path':rel,'text_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
              'text_status':'FILES_TEXT_EXTRACTION_OR_REVIEWED_FALLBACK','subject':lead,
              'tags':tags_for(clean),'classification':'PENDING_RECONCILIATION',
              'review_status':'VISUALLY_REVIEWED_PREVIOUS_PASS' if reviewed else 'TEXT_EXTRACTED_PENDING_VISUAL_REVIEW',
              'occurrence_indexed':True,'source_batch':page,
            })
    rows.sort(key=lambda r:(r['created_at_utc'],r['occurrence_id']))
    out=root/'02 Evidence'/'2026-08-26_library_screenshot_text_occurrences_001.jsonl'
    out.write_text('\n'.join(json.dumps(r,ensure_ascii=False,separators=(',',':')) for r in rows)+'\n',encoding='utf-8')
    return {'status':'PROVEN','rows':len(rows),'redactions':redactions,'reviewed_previous_pass':sum(r['review_status'].startswith('VISUALLY') for r in rows),'pending_visual':sum(r['review_status'].startswith('TEXT_') for r in rows)}

def main()->int:
    print(json.dumps(build(),ensure_ascii=False,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
