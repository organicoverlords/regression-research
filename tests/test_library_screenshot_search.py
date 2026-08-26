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
