import importlib.util
import json
from pathlib import Path
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("swarm_route_node_identity", ROOT / "tools" / "swarm_route.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def test_registry_distinguishes_gpu_desktop_from_laptop():
    data = json.loads((ROOT / "04 Operating Contracts" / "execution-node-topology.json").read_text(encoding="utf-8-sig"))
    desktop = data["nodes"]["kone-gpu-desktop"]
    laptop = data["nodes"]["omen-linux-laptop"]
    assert desktop["user_alias"] == "GPU machine"
    assert desktop["machine_class"] == "desktop"
    assert desktop["gpu"] == "NVIDIA GeForce GTX 1660 SUPER"
    assert laptop["user_alias"] == "laptop"
    assert laptop["machine_class"] == "laptop"
    assert laptop["gpu"] == "NVIDIA GeForce GTX 1070 with Max-Q Design"
    assert desktop["route_label"] == "windows"
    assert laptop["route_label"] == "omen"
    assert desktop != laptop


def test_hostname_verified_identity_is_explicit_and_distinct():
    desktop = m._bind_node_identity("windows", "KONE")
    laptop = m._bind_node_identity("omen", "aatuska-OMEN-by-HP-Laptop-15-dc0xxx")
    assert desktop["node_id"] == "kone-gpu-desktop"
    assert desktop["node_alias"] == "GPU machine"
    assert desktop["node_identity_status"] == "VERIFIED_HOSTNAME"
    assert laptop["node_id"] == "omen-linux-laptop"
    assert laptop["node_alias"] == "laptop"
    assert laptop["node_identity_status"] == "VERIFIED_HOSTNAME"
    assert desktop["node_id"] != laptop["node_id"]


def test_hostname_mismatch_does_not_borrow_expected_machine_identity():
    identity = m._bind_node_identity("windows", "SOME-OTHER-WINDOWS-HOST")
    assert identity["node_id"] is None
    assert identity["expected_node_id"] == "kone-gpu-desktop"
    assert identity["node_identity_status"] == "HOSTNAME_MISMATCH"


def test_windows_probe_binds_resource_sample_to_kone():
    with mock.patch.object(m.platform, "node", return_value="KONE"):
        probe = m.probe_windows()
    assert probe["node_id"] == "kone-gpu-desktop"
    assert probe["node_alias"] == "GPU machine"
    assert probe["machine_class"] == "desktop"
    assert probe["observed_hostname"] == "KONE"
    assert probe["node_identity_status"] == "VERIFIED_HOSTNAME"


def test_omen_probe_payload_collects_hostname_and_gpu_name():
    code = m._omen_probe_code()
    assert '"observed_hostname":os.uname().nodename' in code
    assert 'name,utilization.gpu,memory.used,memory.free' in code


def test_new_assignment_carries_node_identity_from_probe():
    probe = {
        "observed_at": "2026-09-09T00:00:00Z",
        "omen": {
            "available": True,
            "mem_available_gb": 12,
            "disk_free_gb": 60,
            "root_disk_free_gb": 60,
            "nvme_disk_free_gb": 60,
            "load1": 1,
            "cpu_count": 12,
            **m._bind_node_identity("omen", "aatuska-OMEN-by-HP-Laptop-15-dc0xxx"),
        },
        "windows": {"available": True, **m._bind_node_identity("windows", "KONE")},
        "vps": {"available": False, **m._bind_node_identity("vps")},
    }
    original = m.probe_all
    try:
        m.probe_all = lambda: probe
        with tempfile.TemporaryDirectory() as td:
            result = m.route_work(Path(td) / "state.json", "node-identity-test", "portable", 600, False)
    finally:
        m.probe_all = original
    assert result["route"] == "omen"
    assert result["node_id"] == "omen-linux-laptop"
    assert result["node_alias"] == "laptop"
    assert result["node_identity_status"] == "VERIFIED_HOSTNAME"


def test_failed_omen_probe_is_still_bound_to_expected_node_without_false_verification(tmp_path):
    original = m.Path.home
    try:
        m.Path.home = classmethod(lambda cls: tmp_path)
        probe = m.probe_omen(timeout=0.01)
    finally:
        m.Path.home = original
    assert probe["available"] is False
    assert probe["node_id"] is None
    assert probe["expected_node_id"] == "omen-linux-laptop"
    assert probe["node_identity_status"] == "HOSTNAME_UNOBSERVED"


def test_windows_gpu_telemetry_is_inside_kone_bound_probe():
    fake = mock.Mock(returncode=0, stdout="NVIDIA GeForce GTX 1660 SUPER, 44, 3000, 3144, 96.5, 82\n")
    with mock.patch.object(m.platform, "node", return_value="KONE"), mock.patch.object(m, "_run", return_value=fake):
        probe = m.probe_windows()
    assert probe["node_id"] == "kone-gpu-desktop"
    assert probe["gpu"]["name"] == "NVIDIA GeForce GTX 1660 SUPER"
    assert probe["gpu"]["utilization_pct"] == 44
    assert probe["gpu"]["power_draw_w"] == 96.5


def test_windows_assignment_is_kone_not_laptop():
    probe = {
        "observed_at": "2026-09-09T00:00:00Z",
        "omen": {"available": True, "mem_available_gb": 12, "disk_free_gb": 60, "root_disk_free_gb": 60, "nvme_disk_free_gb": 60, "load1": 1, "cpu_count": 12, **m._bind_node_identity("omen", "aatuska-OMEN-by-HP-Laptop-15-dc0xxx")},
        "windows": {"available": True, **m._bind_node_identity("windows", "KONE")},
        "vps": {"available": False, **m._bind_node_identity("vps")},
    }
    original = m.probe_all
    try:
        m.probe_all = lambda: probe
        with tempfile.TemporaryDirectory() as td:
            result = m.route_work(Path(td) / "state.json", "lowvram-node-test", "lowvram", 600, False)
    finally:
        m.probe_all = original
    assert result["route"] == "windows"
    assert result["node_id"] == "kone-gpu-desktop"
    assert result["node_alias"] == "GPU machine"
    assert result["machine_class"] == "desktop"


def test_assignment_preserves_hostname_mismatch_instead_of_guessing_node():
    probe = {
        "observed_at": "2026-09-09T00:00:00Z",
        "omen": {"available": False, **m._bind_node_identity("omen")},
        "windows": {"available": True, **m._bind_node_identity("windows", "OTHER-HOST")},
        "vps": {"available": False, **m._bind_node_identity("vps")},
    }
    original = m.probe_all
    try:
        m.probe_all = lambda: probe
        with tempfile.TemporaryDirectory() as td:
            result = m.route_work(Path(td) / "state.json", "mismatch-node-test", "windows-only", 600, False)
    finally:
        m.probe_all = original
    assert result["route"] == "windows"
    assert result["node_id"] is None
    assert result["expected_node_id"] == "kone-gpu-desktop"
    assert result["node_identity_status"] == "HOSTNAME_MISMATCH"
