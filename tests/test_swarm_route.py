import importlib.util
from pathlib import Path
import tempfile, unittest
ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("swarm_route",ROOT/"tools"/"swarm_route.py")
m=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(m)
def facts(omen=True,mem=12,disk=60,load1=1,cpus=12,lane1=False,lane2=False,vps=True):
    return {"observed_at":"2026-09-07T20:00:00Z","omen":{"available":omen,"mem_available_gb":mem,"disk_free_gb":disk,"load1":load1,"cpu_count":cpus,"lane1_build_active":lane1,"lane2_build_active":lane2},"windows":{"available":True},"vps":{"available":vps}}
class TransportContractTests(unittest.TestCase):
    def test_omen_probe_uses_stable_lan_ip(self):
        self.assertEqual(m.OMEN_HOST, "192.168.0.128")
        self.assertEqual(m.OMEN_HOST_KEY_ALIAS, "192.168.0.128")
class RouteDecisionTests(unittest.TestCase):
    def test_pins(self):
        f=facts(); self.assertEqual(m.choose_route("lowvram",f,{})[0],"windows"); self.assertEqual(m.choose_route("windows-only",f,{})[0],"windows")
    def test_omen_default(self):
        for kind in ("portable","portable-light","heavy","p3-runtime"): self.assertEqual(m.choose_route(kind,facts(),{})[0],"omen")
    def test_windows_fallback(self):
        f=facts(omen=False,vps=False); route,reason=m.choose_route("portable",f,{})
        self.assertEqual(route,"windows"); self.assertIn("OMEN_UNAVAILABLE",reason)
    def test_vps_light_only(self):
        f=facts(mem=1,vps=True); self.assertEqual(m.choose_route("portable-light",f,{})[0],"vps"); self.assertEqual(m.choose_route("heavy",f,{})[0],"windows")
    def test_leases_are_observability_not_capacity(self):
        leases={str(i):{"route":"omen","kind":"heavy" if i==0 else "portable-light"} for i in range(12)}
        self.assertEqual(m.choose_route("heavy",facts(),leases)[0],"omen")
        self.assertEqual(m.choose_route("portable",facts(),leases)[0],"omen")
        self.assertEqual(m.choose_route("portable-light",facts(),leases)[0],"omen")
    def test_lane1_activity_does_not_change_machine_route(self):
        self.assertEqual(m.choose_route("p3-runtime",facts(lane1=True),{})[0],"omen")
    def test_dedicated_nvme_uses_modest_hard_floor(self):
        self.assertEqual(m.choose_route("heavy",facts(disk=15),{})[0],"windows")
        self.assertEqual(m.choose_route("heavy",facts(disk=16),{})[0],"omen")
        self.assertEqual(m.choose_route("p3-runtime",facts(disk=12),{})[0],"omen")
    def test_state_roundtrip_release(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"state.json"; s=m.empty_state(); s["assignments"]["x"]={"work_id":"x","route":"omen","kind":"portable","expires_at":"2099-01-01T00:00:00Z"}; m.save_state(p,s)
            self.assertEqual(m.load_state(p)["assignments"]["x"]["route"],"omen"); self.assertTrue(m.release_work(p,"x")["released"]); self.assertNotIn("x",m.load_state(p)["assignments"])
    def test_low_disk_runs_one_reclaim_then_reprobes(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"state.json"
            original_probe=m.probe_all; original_omen=m.probe_omen; original_reclaim=m.reclaim_omen_scratch
            calls=[]
            try:
                m.probe_all=lambda: facts(disk=9)
                m.reclaim_omen_scratch=lambda kind: (calls.append(kind) or {"attempted":True,"ok":True,"target_free_gb":16})
                m.probe_omen=lambda: facts(disk=30)["omen"]
                result=m.route_work(p,"disk-recovery","portable",600,False)
            finally:
                m.probe_all=original_probe; m.probe_omen=original_omen; m.reclaim_omen_scratch=original_reclaim
            self.assertEqual(calls,["portable"])
            self.assertEqual(result["route"],"omen")
            self.assertTrue(result["capacity_recovery"]["ok"])
    def test_same_work_id_reuses_one_cohort_decision(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"state.json"
            original=m.probe_all
            calls=[]
            try:
                m.probe_all=lambda: (calls.append(1) or facts())
                first=m.route_work(p,"issue-758","portable",600,False)
                m.probe_all=lambda: (_ for _ in ()).throw(AssertionError("second worker must reuse cohort assignment"))
                second=m.route_work(p,"issue-758","portable",600,False)
            finally:
                m.probe_all=original
            self.assertEqual(len(calls),1)
            self.assertEqual(first["decision_id"],second["decision_id"])
            self.assertTrue(second["reused"])
            self.assertEqual(second["route"],"omen")
if __name__=="__main__": unittest.main()
