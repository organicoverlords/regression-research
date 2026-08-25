import json
import tempfile
import unittest
from pathlib import Path
from tools.five_day_correlation import ISSUE_28_SNAPSHOT, build_day_metrics, build_outcome_join, parse_transport, write_outputs

class FiveDayCorrelationTests(unittest.TestCase):
 def test_transport_parser_counts_calls_and_long_reads_by_eest_day(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'transport.jsonl'
   rows=[
    {'at':'2026-08-23T21:30:00Z','mcp_tool':'read_output','duration_ms':9500},
    {'at':'2026-08-23T21:31:00Z','mcp_tool':'start_process','duration_ms':20},
    {'at':'2026-08-23T21:32:00Z','path':'/health'},
   ]
   p.write_text('\n'.join(json.dumps(r) for r in rows)+'\n',encoding='utf-8')
   got=parse_transport(p)
   self.assertEqual(got['status'],'ok')
   self.assertEqual(got['daily_counts']['2026-08-24'],2)
   self.assertEqual(got['slow_reads_ge_9s']['2026-08-24'],1)
   self.assertEqual(got['health_daily']['2026-08-24'],1)
 def test_missing_days_remain_explicit_and_snapshot_fallback_is_labeled(self):
  metrics=build_day_metrics({'status':'unavailable'},ISSUE_28_SNAPSHOT)
  self.assertIsNone(metrics['2026-08-21']['mcp_calls_total'])
  self.assertEqual(metrics['2026-08-21']['mcp_calls_source'],'missing')
  self.assertEqual(metrics['2026-08-24']['mcp_calls_total'],14960)
  self.assertEqual(metrics['2026-08-24']['mcp_calls_source'],'issue28_snapshot')
 def test_yield_metric_is_independently_reproducible(self):
  join=build_outcome_join()
  self.assertEqual(join['2026-08-23']['merges_per_1k_calls'],round(95/5212*1000,3))
  self.assertGreater(join['2026-08-23']['merges_per_1k_calls'],join['2026-08-24']['merges_per_1k_calls'])
 def test_machine_outputs_have_five_day_rows(self):
  data={'schema_version':'1','day_metrics':build_day_metrics({'status':'unavailable'},ISSUE_28_SNAPSHOT),'outcome_join':build_outcome_join()}
  with tempfile.TemporaryDirectory() as td:
   paths=write_outputs(Path(td),data)
   self.assertTrue(Path(paths['json']).is_file())
   lines=Path(paths['csv']).read_text(encoding='utf-8').splitlines()
   self.assertEqual(len(lines),6)

if __name__=='__main__': unittest.main()
