import json, subprocess, sys, unittest
from tools.build_admission import evaluate
class BuildAdmissionTests(unittest.TestCase):
 def test_writable_filesystem_can_still_be_denied(self):
  r=evaluate(free_gb=21.35,threshold_gb=25,filesystem_writable=True)
  self.assertTrue(r['filesystem_writable']); self.assertFalse(r['build_admitted']); self.assertIn('disk_admission_floor',r['blockers'])
  self.assertTrue(r['non_disk_work_admitted']); self.assertFalse(r['worker_should_stop'])
 def test_crossing_floor_restores_admission(self):
  r=evaluate(free_gb=25.01,threshold_gb=25,filesystem_writable=True)
  self.assertTrue(r['build_admitted']); self.assertTrue(r['non_disk_work_admitted']); self.assertFalse(r['worker_should_stop'])
 def test_safe_reclaim_is_reported_without_assuming_mutation(self):
  r=evaluate(free_gb=21,threshold_gb=25,filesystem_writable=True,reclaimable_safe_gb=5)
  self.assertTrue(r['would_admit_after_safe_reclaim']); self.assertEqual(r['free_after_safe_reclaim_gb'],26)
 def test_cli_is_machine_readable(self):
  out=subprocess.check_output([sys.executable,'tools/build_admission.py','--free-gb','21','--threshold-gb','25','--filesystem-writable','true'],text=True)
  self.assertFalse(json.loads(out)['build_admitted'])
if __name__=='__main__': unittest.main()
