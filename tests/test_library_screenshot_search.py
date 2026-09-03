from pathlib import Path
from tools.library_screenshot_search import search, _rows, canonical_text_sha256

ROOT=Path(__file__).resolve().parents[1]


def test_search_reports_occurrence_count_and_neighbors():
    r=search('tool',context=1,limit=3,root=ROOT)
    assert r['indexed_occurrences']==len(_rows(ROOT))
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
    assert len(_rows(ROOT)) >= 274



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


def test_canonical_text_sha256_is_newline_portable(tmp_path):
    lf=tmp_path/'lf.txt'; crlf=tmp_path/'crlf.txt'
    lf.write_bytes(b'alpha\nbeta\n')
    crlf.write_bytes(b'alpha\r\nbeta\r\n')
    assert canonical_text_sha256(lf)==canonical_text_sha256(crlf)


def test_all_occurrence_text_hashes_match_indexed_files():
    import json
    ledgers=sorted((ROOT/'02 Evidence').glob('*_library_screenshot_text_occurrences_*.jsonl'))
    rows=[]
    for ledger in ledgers:
        rows.extend(json.loads(x) for x in ledger.read_text(encoding='utf-8-sig').splitlines() if x.strip())
    assert rows
    for row in rows:
        path=ROOT / row['text_path']
        assert path.is_file(), row['text_path']
        assert canonical_text_sha256(path)==row['text_sha256'], row['filename']


def test_page4_occurrence_ledger_is_fully_reconciled():
    import json
    from collections import Counter
    ledger=ROOT/'02 Evidence'/'2026-08-27_library_screenshot_text_occurrences_002.jsonl'
    rows=[json.loads(x) for x in ledger.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
    assert len(rows)==57
    assert len({r['library_file_id'] for r in rows})==57
    assert all(r['library_file_id_status']=='EXACT_LIBRARY_LIST' for r in rows)
    assert all(r['review_status']=='VISUALLY_REVIEWED' for r in rows)
    assert all(r['reconciliation_status']=='FINAL_VISUAL_REVIEW_2026-08-27' for r in rows)
    assert Counter(r['classification'] for r in rows)=={
        'CONVERSATION_SCREENSHOT_NEW':35,
        'NON_CONVERSATION_IMAGE':21,
        'DUPLICATE':1,
    }


def test_page4_exact_duplicate_keeps_its_own_occurrence():
    import json
    ledger=ROOT/'02 Evidence'/'2026-08-27_library_screenshot_text_occurrences_002.jsonl'
    rows=[json.loads(x) for x in ledger.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
    duplicate=[r for r in rows if r['classification']=='DUPLICATE']
    assert len(duplicate)==1
    r=duplicate[0]
    assert r['duplicate_of_library_file_id']=='file_00000000c7e07246b0f8706c32f9142f'
    assert r['image_sha256']=='64d983e7df5d46625488ee9e2b8049a988adafb2fcb829b60d68a3e8dbadf23b'


def test_page5_occurrence_ledger_is_fully_reconciled():
    import json
    from collections import Counter
    ledger=ROOT/'02 Evidence'/'2026-08-27_library_screenshot_text_occurrences_003.jsonl'
    rows=[json.loads(x) for x in ledger.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
    assert len(rows)==100
    assert len({r['library_file_id'] for r in rows})==100
    assert len({r['occurrence_id'] for r in rows})==100
    assert all(r['library_file_id_status']=='EXACT_LIBRARY_LIST' for r in rows)
    assert all(r['review_status']=='VISUALLY_REVIEWED' for r in rows)
    assert all(r['reconciliation_status']=='FINAL_VISUAL_REVIEW_2026-08-27' for r in rows)
    assert Counter(r['classification'] for r in rows)=={
        'CONVERSATION_SCREENSHOT_NEW':17,
        'NON_CONVERSATION_IMAGE':78,
        'DUPLICATE':5,
    }


def test_page5_exact_duplicates_keep_separate_occurrences():
    import json
    ledger=ROOT/'02 Evidence'/'2026-08-27_library_screenshot_text_occurrences_003.jsonl'
    rows=[json.loads(x) for x in ledger.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
    by_id={r['library_file_id']:r for r in rows}
    expected={
        'file_0000000099ec722f99125116de8f1749':('file_00000000d50c722fa08fa2d8202a9fb8','bd7199a3342a2a394e000f892d3ce0d08146e4eb9eece9e7fa02bff7827e610e'),
        'file_00000000ebe071f4a99cf3ccb6c06d4e':('file_000000003d907246b7e481beea133d20','e891a8cfac658846aae6fcf99fa9565cb999b648a2e77da2dc0bafe9524b886f'),
        'file_000000006620720aa93604ceb1fa7794':('file_0000000009b071f4b6665445ca8f1671','0b341f4eaeddbdbebf69d6a0bcbdcee3b87cbeccfb07987efb94af349bb8a38c'),
        'file_0000000032807246adcd5340cc66f523':('file_000000006d047246a5a5cfa46083615e','4e375a18289b0b26efbb6b6b4d5dca0aeddc357367c9df2d853842669157b89f'),
        'file_0000000042bc7246826e3a2f6611691a':('file_000000006488724682a9dce0678f1266','67d1298b8dd33a089095c33b59c6ee2c06e6898fc24373b17b005e7ddca3cccb'),
    }
    duplicates={r['library_file_id']:r for r in rows if r['classification']=='DUPLICATE'}
    assert set(duplicates)==set(expected)
    for duplicate_id,(target_id,image_sha256) in expected.items():
        r=duplicates[duplicate_id]
        assert target_id in by_id
        assert r['duplicate_of_library_file_id']==target_id
        assert r['image_sha256']==image_sha256
