from pathlib import Path
from tools.library_screenshot_inventory import load_jsonl, validate
ROOT=Path(__file__).resolve().parents[1]
SHARD=ROOT/'02 Evidence'/'2026-08-26_library_screenshot_shard_000.jsonl'
def test_reviewed_shard_is_valid():
    result=validate(load_jsonl(SHARD)); assert result['status']=='PROVEN'; assert result['rows']==15; assert result['counts']['DUPLICATE']==2
def test_duplicate_requires_exact_target():
    rows=load_jsonl(SHARD); rows[10]=dict(rows[10]); rows[10].pop('duplicate_of_file_id'); assert validate(rows)['status']=='REJECTED'
