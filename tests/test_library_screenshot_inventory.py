from pathlib import Path
from tools.library_screenshot_inventory import load_jsonl, validate
ROOT=Path(__file__).resolve().parents[1]
SHARD=ROOT/'02 Evidence'/'2026-08-26_library_screenshot_shard_000.jsonl'
def test_reviewed_shard_is_valid():
    result=validate(load_jsonl(SHARD),root=ROOT); assert result['status']=='PROVEN'; assert result['rows']==100; assert result['text_indexed']==100; assert result['counts']['DUPLICATE']==4
def test_duplicate_requires_exact_target():
    rows=load_jsonl(SHARD); rows[10]=dict(rows[10]); rows[10].pop('duplicate_of_file_id'); assert validate(rows,root=ROOT)['status']=='REJECTED'
def test_every_occurrence_has_searchable_text_file():
    rows=load_jsonl(SHARD)
    assert all(r['occurrence_indexed'] is True for r in rows)
    assert all((ROOT/r['text_path']).read_text(encoding='utf-8-sig',errors='replace').strip() for r in rows)
