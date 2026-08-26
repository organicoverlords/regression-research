from __future__ import annotations
import argparse, json
from collections import Counter
from pathlib import Path
ALLOWED={"CONVERSATION_SCREENSHOT_NEW","CONVERSATION_SCREENSHOT_ALREADY_COVERED","DUPLICATE","NON_CONVERSATION_IMAGE","UNREADABLE/AMBIGUOUS"}
REQUIRED={"file_id","filename","created_at_utc","classification","review_status","subject","evidence_quality","memory_action"}
def load_jsonl(path:Path)->list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8-sig").splitlines() if x.strip()]
def validate(rows:list[dict])->dict:
    errors=[]; seen=set()
    for i,row in enumerate(rows,1):
        missing=sorted(REQUIRED-row.keys())
        if missing: errors.append(f"line {i}: missing {','.join(missing)}")
        fid=row.get("file_id")
        if fid in seen: errors.append(f"line {i}: duplicate file_id {fid}")
        seen.add(fid)
        if row.get("classification") not in ALLOWED: errors.append(f"line {i}: invalid classification")
        if row.get("review_status")!="VISUALLY_REVIEWED": errors.append(f"line {i}: review_status must be VISUALLY_REVIEWED")
        if row.get("classification")=="DUPLICATE" and not row.get("duplicate_of_file_id"): errors.append(f"line {i}: duplicate missing duplicate_of_file_id")
    by_id={r.get("file_id"):r for r in rows}
    for i,row in enumerate(rows,1):
        if row.get("classification")=="DUPLICATE":
            target=by_id.get(row.get("duplicate_of_file_id"))
            if target is None: errors.append(f"line {i}: duplicate target missing from shard")
            elif row.get("sha256") and target.get("sha256") and row["sha256"]!=target["sha256"]: errors.append(f"line {i}: duplicate sha256 mismatch")
    return {"status":"PROVEN" if not errors else "REJECTED","rows":len(rows),"counts":dict(Counter(r.get("classification") for r in rows)),"errors":errors}
def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("inventory",type=Path); a=p.parse_args(); result=validate(load_jsonl(a.inventory)); print(json.dumps(result,ensure_ascii=False,indent=2)); return 0 if result["status"]=="PROVEN" else 1
if __name__=="__main__": raise SystemExit(main())
