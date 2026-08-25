import json, unittest
from pathlib import Path

class SourceInventoryTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads(Path('memory/sources.json').read_text(encoding='utf-8'))
    def test_inventory_records_are_structured_and_classified(self):
        items=self.data['candidate_source_inventory']
        self.assertTrue(items)
        self.assertTrue(all(isinstance(x,dict) for x in items))
        required={'id','location','class','scope','freshness','availability'}
        for x in items:self.assertTrue(required.issubset(x),x)
    def test_required_source_families_are_present(self):
        ids={x['id'] for x in self.data['candidate_source_inventory']}
        for expected in {'regression-research','agents-repo','docs-repo','local-agents','claude-history','codex-history','nexus-memory','chatgpt-personal-context','aitube-memory','level6-memory','traycer-artifacts','project-repos'}:
            self.assertIn(expected,ids)
    def test_legacy_seed_is_recovery_not_canonical(self):
        items={x['id']:x for x in self.data['candidate_source_inventory']}
        self.assertEqual(items['legacy-seed']['class'],'RECOVERY_ONLY')
    def test_unavailable_sources_are_explicit(self):
        allowed={'available','optional','unknown','unavailable'}
        self.assertTrue(all(x['availability'] in allowed for x in self.data['candidate_source_inventory']))

if __name__=='__main__':unittest.main()
