import importlib.util
from pathlib import Path
import tempfile, unittest
ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("swarm_route",ROOT/"tools"/"swarm_route.py")
m=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(m)
def facts(omen=True,mem=12,disk=60,root_disk=None,nvme_disk=None,load1=1,cpus=12,lane1=False,lane2=False,vps=True,windows_disk=120):
    root_disk=disk if root_disk is None else root_disk; nvme_disk=disk if nvme_disk is None else nvme_disk
    return {"observed_at":"2026-09-07T20:00:00Z","omen":{"available":omen,"mem_available_gb":mem,"disk_free_gb":nvme_disk,"root_disk_free_gb":root_disk,"nvme_disk_free_gb":nvme_disk,"load1":load1,"cpu_count":cpus,"lane1_build_active":lane1,"lane2_build_active":lane2},"windows":{"available":True,"disk_free_gb":windows_disk},"vps":{"available":vps}}
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
    def test_only_explicit_light_windows_ci_can_select_kone(self):
        f=facts()
        self.assertEqual(m.choose_route("windows-ci-light",f,{})[0],"windows")
        for kind in ("lowvram","windows-only"):
            route,reason=m.choose_route(kind,f,{})
            self.assertEqual(route,"blocked")
            self.assertEqual(reason,"KONE_WORK_EXECUTION_RESTRICTED_TO_LIGHT_MANDATORY_CI")
    def test_omen_default(self):
        for kind in ("portable","portable-light","heavy","p3-runtime"): self.assertEqual(m.choose_route(kind,facts(),{})[0],"omen")
    def test_general_work_blocks_when_omen_is_unavailable(self):
        for kind in ("portable","portable-light","heavy","p3-runtime"):
            route,reason=m.choose_route(kind,facts(omen=False,vps=False),{})
            self.assertEqual(route,"blocked")
            self.assertIn("OMEN_UNAVAILABLE",reason)
    def test_general_work_never_uses_windows_as_capacity_fallback(self):
        route,reason=m.choose_route("portable",facts(omen=False,vps=False,windows_disk=120),{})
        self.assertEqual(route,"blocked")
        self.assertIn("OMEN_UNAVAILABLE",reason)
    def test_light_windows_ci_ignores_generic_disk_threshold(self):
        route,reason=m.choose_route("windows-ci-light",facts(windows_disk=1),{})
        self.assertEqual(route,"windows")
        self.assertEqual(reason,"MANDATORY_LIGHT_WINDOWS_CI")

    def test_explicit_kone_owner_cannot_bypass_light_ci_boundary(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,"SWARM_ROUTE_KONE_RESTRICTED"):
                m.route_work(Path(td)/"state.json","forbidden-kone-owner","portable",600,False,owner_node_id="kone-gpu-desktop")
    def test_vps_light_requires_explicit_execution_capability(self):
        f=facts(mem=1,vps=True)
        self.assertEqual(m.choose_route("portable-light",f,{})[0],"blocked")
        self.assertEqual(m.choose_route("portable-light",f,{},allow_vps=True)[0],"vps")
        self.assertEqual(m.choose_route("heavy",f,{},allow_vps=True)[0],"blocked")
    def test_leases_are_observability_not_capacity(self):
        leases={str(i):{"route":"omen","kind":"heavy" if i==0 else "portable-light"} for i in range(12)}
        self.assertEqual(m.choose_route("heavy",facts(),leases)[0],"omen")
        self.assertEqual(m.choose_route("portable",facts(),leases)[0],"omen")
        self.assertEqual(m.choose_route("portable-light",facts(),leases)[0],"omen")
    def test_lane1_activity_does_not_change_machine_route(self):
        self.assertEqual(m.choose_route("p3-runtime",facts(lane1=True),{})[0],"omen")
    def test_dedicated_nvme_uses_modest_hard_floor(self):
        self.assertEqual(m.choose_route("heavy",facts(disk=15),{})[0],"blocked")
        self.assertEqual(m.choose_route("heavy",facts(disk=16),{})[0],"omen")
        self.assertEqual(m.choose_route("p3-runtime",facts(disk=12),{})[0],"omen")
    def test_runtime_checks_root_and_nvme_tiers(self):
        route,reason=m.choose_route("p3-runtime",facts(root_disk=11,nvme_disk=60),{})
        self.assertEqual(route,"blocked"); self.assertIn("ROOT_DISK_LOW",reason)
        route,reason=m.choose_route("p3-runtime",facts(root_disk=60,nvme_disk=11),{})
        self.assertEqual(route,"blocked"); self.assertIn("NVME_DISK_LOW",reason)
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
    def test_legacy_vps_assignment_requires_explicit_capability_to_reuse(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"state.json"; s=m.empty_state()
            original_expiry="2099-01-01T00:00:00Z"
            s["assignments"]["legacy"]={"work_id":"legacy","route":"vps","kind":"portable-light","reason":"OMEN_LIGHT_CAPACITY_FULL_VPS_LIGHT_OVERFLOW","expires_at":original_expiry}
            m.save_state(p,s)
            reused=m.route_work(p,"legacy","portable-light",600,False,allow_vps=True)
            self.assertTrue(reused["reused"])
            self.assertTrue(reused["policy_migration_pending"])
            self.assertEqual(reused["expires_at"],original_expiry)

    def test_default_caller_replaces_unexecutable_vps_assignment(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"state.json"; s=m.empty_state()
            s["assignments"]["legacy"]={"work_id":"legacy","route":"vps","kind":"portable-light","reason":"OMEN_UNAVAILABLE_VPS_LIGHT_OVERFLOW","expires_at":"2099-01-01T00:00:00Z"}
            s["probe"]={**facts(omen=False,vps=True),"observed_at":m.iso(m.utc_now())}
            m.save_state(p,s)
            with self.assertRaisesRegex(ValueError,"SWARM_ROUTE_NO_SAFE_NODE"):
                m.route_work(p,"legacy","portable-light",600,False)
    def test_legacy_windows_fallback_is_not_reused(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"state.json"; state=m.empty_state()
            state["assignments"]["old-windows"]={"work_id":"old-windows","route":"windows","kind":"portable","reason":"OMEN_UNAVAILABLE_WINDOWS_FALLBACK","policy_epoch":m.POLICY_EPOCH-1,"expires_at":"2099-01-01T00:00:00Z"}
            state["probe"]={**facts(omen=False,vps=False),"observed_at":m.iso(m.utc_now())}
            m.save_state(p,state)
            with self.assertRaisesRegex(ValueError,"SWARM_ROUTE_NO_SAFE_NODE"):
                m.route_work(p,"old-windows","portable",600,False)
            self.assertNotIn("old-windows",m.load_state(p)["assignments"])

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
    def test_distinct_work_ids_share_one_fresh_capacity_probe(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"state.json"
            original=m.probe_all
            calls=[]
            try:
                m.probe_all=lambda: (calls.append(1) or {**facts(),"observed_at":m.iso(m.utc_now())})
                first=m.route_work(p,"issue-849-a","portable",600,False)
                second=m.route_work(p,"issue-849-b","portable",600,False)
            finally:
                m.probe_all=original
            self.assertEqual(len(calls),1)
            self.assertFalse(first["probe_cache_reused"])
            self.assertTrue(second["probe_cache_reused"])
            self.assertEqual(second["probe_cache_ttl_seconds"],m.PROBE_TTL_SECONDS)
            self.assertEqual(first["probe_observed_at"],second["probe_observed_at"])

    def test_refresh_probe_bypasses_shared_probe_cache(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"state.json"
            original=m.probe_all
            calls=[]
            try:
                m.probe_all=lambda: (calls.append(1) or {**facts(),"observed_at":m.iso(m.utc_now())})
                m.route_work(p,"issue-849-refresh-a","portable",600,False)
                refreshed=m.route_work(p,"issue-849-refresh-b","portable",600,True)
            finally:
                m.probe_all=original
            self.assertEqual(len(calls),2)
            self.assertFalse(refreshed["probe_cache_reused"])

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
