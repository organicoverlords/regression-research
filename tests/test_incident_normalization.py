import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/'02 Evidence'/'2026-08-25_mcp_tool_routing_incident_index.json'

class IncidentNormalizationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls): cls.data=json.loads(INDEX.read_text(encoding='utf-8-sig'))
 def test_cases_have_provenance_and_action_delta(self):
  self.assertGreaterEqual(len(self.data['cases']),2)
  for case in self.data['cases']:
   self.assertTrue(case['first_wrong_substantive_move'])
   self.assertTrue(case['correct_next_substantive_action'])
   self.assertTrue(case['decisive_evidence'])
   report=case.get('source_report')
   if report: self.assertTrue((ROOT/report).is_file(),case['id'])
   raw=case.get('raw_transcript')
   if raw: self.assertTrue((ROOT/raw).is_file(),case['id'])
   support=case.get('supporting_evidence')
   if support: self.assertTrue((ROOT/support).is_file(),case['id'])
 def test_duplicate_groups_do_not_double_count_cases(self):
  ids={case['id'] for case in self.data['cases']}
  for group in self.data['duplicate_groups']:
   self.assertIn(group['canonical_case'],ids)
   self.assertGreaterEqual(len(group['members']),2)
   for path in group['members']: self.assertTrue((ROOT/path).is_file(),path)
 def test_unsupported_reasoning_is_explicitly_excluded(self):
  for case in self.data['cases']:
   self.assertTrue(case['unsupported_claims_excluded'],case['id'])
  self.assertIn('Private reasoning is excluded',self.data['evidence_boundary'])

if __name__=='__main__': unittest.main()
