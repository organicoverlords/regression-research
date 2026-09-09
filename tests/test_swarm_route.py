import importlib.util
from pathlib import Path
import json, subprocess, tempfile, unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("swarm_route",ROOT/"tools"/"swarm_route.py")
m=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(m)
def facts(omen=True,mem=12,disk=60,root_disk=None,nvme_disk=None,load1=1,cpus=12,lane1=False,lane2=False,vps=True):
    root_disk=disk if root_disk is None else root_disk; nvme_disk=disk if nvme_disk is None else nvme_disk
    return {"observed_at":"2026-09-07T20:00:00Z","omen":{"available":omen,"mem_available_gb":mem,"disk_free_gb":nvme_disk,"root_disk_free_gb":root_disk,"nvme_disk_free_gb":nvme_disk,"load1":load1,"cpu_count":cpus,"lane1_build_active":lane1,"lane2_build_active":lane2},"windows":{"available":True},"vps":{"available":vps}}
class GitHubReadAccelerationTests(unittest.TestCase):
    def test_github_read_cli_prefers_gh_swarm_on_path(self):
        with mock.patch.object(m.shutil,"which",side_effect=lambda name: "C:/tools/gh-swarm.exe" if name=="gh-swarm" else "C:/tools/gh.exe"):
            self.assertEqual(m._github_read_cli(),"C:/tools/gh-swarm.exe")

    def test_github_read_cli_falls_back_to_real_gh(self):
        with mock.patch.object(m.shutil,"which",side_effect=lambda name: None if name=="gh-swarm" else "C:/tools/gh.exe"), mock.patch.object(m.Path,"is_file",return_value=False):
            self.assertEqual(m._github_read_cli(),"C:/tools/gh.exe")

    def test_vps_probe_uses_selected_read_cli(self):
        payload={"runners":[{"name":"P3-VPS-LIGHT","status":"online","busy":False,"labels":[{"name":m.VPS_RUNNER_LABEL}]}]}
        completed=subprocess.CompletedProcess([],0,json.dumps(payload),"")
        with mock.patch.object(m,"_github_read_cli",return_value="gh-swarm"), mock.patch.object(m,"_run",return_value=completed) as run, mock.patch.object(m,"_bind_node_identity",return_value={}):
            result=m.probe_vps(timeout=1.25)
        run.assert_called_once_with(["gh-swarm","api","repos/organicoverlords/p3/actions/runners"],1.25)
        self.assertTrue(result["available"])
        self.assertTrue(result["online"])
        self.assertFalse(result["busy"])

class TransportContractTests(unittest.TestCase):
    def test_omen_probe_uses_stable_lan_ip(self):
        self.assertEqual(m.OMEN_HOST, "192.168.0.128")
        self.assertEqual(m.OMEN_HOST_KEY_ALIAS, "192.168.0.128")
    def test_omen_probe_detects_dynamic_lane_wrapper_processes(self):
        code=m._omen_probe_code()
        self.assertIn('argv_active("run-p3-linux-lane.sh",1)',code)
        self.assertIn('argv_active("run-p3-linux-lane.sh",2)',code)
        self.assertIn('argv_active("run-p3-linux-lane.sh",3)',code)
        self.assertIn('argv_active("run-p3-linux-light.sh")',code)
        self.assertIn('active("p3-linux-lane@2.service") or argv_active("run-p3-linux-lane.sh",2)',code)
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
    def test_runtime_checks_root_and_nvme_tiers(self):
        route,reason=m.choose_route("p3-runtime",facts(root_disk=11,nvme_disk=60),{})
        self.assertEqual(route,"windows"); self.assertIn("ROOT_DISK_LOW",reason)
        route,reason=m.choose_route("p3-runtime",facts(root_disk=60,nvme_disk=11),{})
        self.assertEqual(route,"windows"); self.assertIn("NVME_DISK_LOW",reason)
        self.assertEqual(m.choose_route("portable",facts(root_disk=1,nvme_disk=60),{})[0],"omen")

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
    def test_legacy_assignment_drains_without_renewing(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"state.json"; s=m.empty_state()
            original_expiry="2099-01-01T00:00:00Z"
            s["assignments"]["legacy"]={"work_id":"legacy","route":"vps","kind":"portable-light","reason":"OMEN_LIGHT_CAPACITY_FULL_VPS_LIGHT_OVERFLOW","expires_at":original_expiry}
            m.save_state(p,s)
            reused=m.route_work(p,"legacy","portable-light",600,False)
            self.assertTrue(reused["reused"])
            self.assertTrue(reused["policy_migration_pending"])
            self.assertEqual(reused["expires_at"],original_expiry)
    def test_current_epoch_assignment_renews(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"state.json"
            original=m.probe_all
            try:
                m.probe_all=lambda: facts()
                first=m.route_work(p,"current-epoch","portable",60,False)
                second=m.route_work(p,"current-epoch","portable",600,False)
            finally:
                m.probe_all=original
            self.assertEqual(first["policy_epoch"],m.POLICY_EPOCH)
            self.assertFalse(second["policy_migration_pending"])
            self.assertGreater(m.parse_time(second["expires_at"]),m.parse_time(first["expires_at"]))
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
