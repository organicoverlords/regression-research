from pathlib import Path
from tools.library_screenshot_search import search, _rows
from tools.build_library_screenshot_occurrences import scrub

ROOT=Path(__file__).resolve().parents[1]


def test_search_reports_occurrence_count_and_neighbors():
    r=search('tool',context=1,limit=3,root=ROOT)
    assert r['indexed_occurrences']==217
    assert r['occurrence_count'] >= r['returned']
    assert r['occurrence_count'] > 17
    if r['matches']:
        assert 'before' in r['matches'][0] and 'after' in r['matches'][0]


def test_search_uses_extracted_text_not_only_subject():
    r=search('desktop-bootstrap',context=1,limit=5,root=ROOT)
    assert r['occurrence_count'] >= 1
    assert any(x['filename']=='image(8).png' for x in r['matches'])


def test_exact_duplicate_screenshots_remain_separate_occurrences():
    names=[r.get('filename','') for r in _rows(ROOT)]
    assert any(n.endswith('190023.png') for n in names)
    assert any(n.endswith('190023(1).png') for n in names)
    assert len(_rows(ROOT))==217


def test_scrub_replaces_credential_value_not_occurrence():
    cleaned,count=scrub('api_key=sk-'+'x'*24+' useful surrounding evidence')
    assert count==1
    assert '[REDACTED_CREDENTIAL]' in cleaned
    assert 'useful surrounding evidence' in cleaned
    assert 'sk-'+'x'*24 not in cleaned


def test_ingested_redaction_has_no_live_generic_assignment_value():
    matches=list((ROOT/'02 Evidence'/'library_screenshot_text'/'page2').glob('*104732.txt'))
    assert len(matches)==1
    text=matches[0].read_text(encoding='utf-8-sig',errors='replace')
    assert '[REDACTED_CREDENTIAL]' in text


def test_text_path_cannot_escape_screenshot_corpus():
    from tools.library_screenshot_search import _text
    assert _text({'text_path':'../CHANGELOG.md'},ROOT)==''
    assert _text({'text_path':'02 Evidence/../CHANGELOG.md'},ROOT)==''

def test_reconciled_occurrence_ledger_has_stable_ids_and_final_classes():
    import json
    ledger=ROOT/'02 Evidence'/'2026-08-26_library_screenshot_text_occurrences_001.jsonl'
    rows=[json.loads(x) for x in ledger.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
    assert len(rows)==117
    assert len({r['library_file_id'] for r in rows})==117
    assert all(r['library_file_id_status']=='BACKFILLED_EXACT_LIBRARY_FILENAME' for r in rows)
    assert all(r['classification']!='PENDING_RECONCILIATION' for r in rows)
    assert all(r['review_status']!='TEXT_EXTRACTED_PENDING_VISUAL_REVIEW' for r in rows)


def test_reconciled_occurrence_classification_counts():
    import json
    from collections import Counter
    ledger=ROOT/'02 Evidence'/'2026-08-26_library_screenshot_text_occurrences_001.jsonl'
    rows=[json.loads(x) for x in ledger.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
    assert Counter(r['classification'] for r in rows)=={
        'NON_CONVERSATION_IMAGE':82,
        'CONVERSATION_SCREENSHOT_NEW':31,
        'DUPLICATE':4,
    }


def test_reconciled_duplicates_keep_separate_occurrences_and_exact_targets():
    import json
    ledger=ROOT/'02 Evidence'/'2026-08-26_library_screenshot_text_occurrences_001.jsonl'
    rows=[json.loads(x) for x in ledger.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
    by_id={r['library_file_id']:r for r in rows}
    duplicates=[r for r in rows if r['classification']=='DUPLICATE']
    assert len(duplicates)==4
    for r in duplicates:
        target=r.get('duplicate_of_library_file_id')
        assert target and target in by_id
        assert target != r['library_file_id']
        assert len(r.get('image_sha256',''))==64
