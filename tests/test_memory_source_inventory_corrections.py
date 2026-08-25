import json, unittest
from pathlib import Path

class SourceInventoryCorrections(unittest.TestCase):
    def setUp(self):
        self.data=json.loads(Path('memory/sources.json').read_text(encoding='utf-8'))
        self.items={x['id']:x for x in self.data['candidate_source_inventory']}
    def test_every_inventory_class_is_defined(self):
        defined=set(self.data['classes'])
        for item in self.items.values(): self.assertIn(item['class'],defined,item)
    def test_current_shared_policy_source_is_live_canonical(self):
        self.assertEqual(self.items['local-shared-agent-policy']['class'],'LIVE_CANONICAL')
        self.assertIn('SHARED-AGENT-POLICY.md',self.items['local-shared-agent-policy']['location'])
    def test_repo_agents_md_is_explicit_live_policy_source(self):
        self.assertEqual(self.items['repo-agents-md']['class'],'LIVE_CANONICAL')
        self.assertEqual(self.items['repo-agents-md']['scope'],'project')
    def test_nexus_availability_records_measured_file_count(self):
        n=self.items['nexus-memory']
        self.assertEqual(n['availability'],'available')
        self.assertEqual(n['observed_file_count'],1)
        self.assertTrue(n['observed_at'].startswith('2026-08-25'))
    def test_no_measured_available_source_is_unknown(self):
        for item in self.items.values():
            if 'observed_file_count' in item: self.assertNotEqual(item['availability'],'unknown',item)

if __name__=='__main__':unittest.main()
