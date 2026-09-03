import json, unittest
from pathlib import Path

class SourceInventoryCorrections(unittest.TestCase):
    def setUp(self):
        self.data=json.loads(Path('memory/sources.json').read_text(encoding='utf-8'))
        self.items={x['id']:x for x in self.data['candidate_source_inventory']}
    def test_every_inventory_class_is_defined(self):
        defined=set(self.data['classes'])
        for item in self.items.values(): self.assertIn(item['class'],defined,item)
    def test_agent_rules_repo_is_the_live_canonical_policy_source(self):
        item=self.items['agent-rules-repo']
        self.assertEqual(item['class'],'LIVE_CANONICAL')
        self.assertIn('organicoverlords/agent-rules@rules/live',item['location'])
        self.assertIn('single canonical',item['role'])
    def test_repo_rule_files_are_navigation_not_policy_authority(self):
        item=self.items['repo-rule-pointer']
        self.assertEqual(item['class'],'VERIFIED_EVIDENCE')
        self.assertEqual(item['scope'],'project')
        self.assertIn('not policy authority',item['role'])
    def test_nexus_availability_records_measured_file_count(self):
        n=self.items['nexus-memory']
        self.assertEqual(n['availability'],'available')
        self.assertEqual(n['observed_file_count'],1)
        self.assertTrue(n['observed_at'].startswith('2026-08-25'))
    def test_no_measured_available_source_is_unknown(self):
        for item in self.items.values():
            if 'observed_file_count' in item: self.assertNotEqual(item['availability'],'unknown',item)

if __name__=='__main__':unittest.main()
