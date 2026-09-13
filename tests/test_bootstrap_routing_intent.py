import json
from pathlib import Path

import tools.stack_atlas as stack_atlas
from tools.stack_atlas import COMPONENTS, _fit_bootstrap_glance_budget

ROOT = Path(__file__).resolve().parents[1]


def test_execution_node_topology_carries_routing_intent():
    payload = json.loads((ROOT / "04 Operating Contracts" / "execution-node-topology.json").read_text(encoding="utf-8"))
    policy = payload["routing_policy"]
    assert policy["default_execution_node"] == "omen-linux-laptop"
    assert policy["substantive_execution"] == "OMEN_REQUIRED"
    assert policy["kone_execution"] == "MANDATORY_WINDOWS_CI_LIGHT_ONLY"
    assert policy["kone_capacity_fallback"] is False
    assert "default_execution" in payload["nodes"]["omen-linux-laptop"]["roles"]
    assert "mandatory_windows_ci_light" in payload["nodes"]["kone-gpu-desktop"]["roles"]



def test_bootstrap_execution_node_projection_keeps_routing_policy(monkeypatch):
    monkeypatch.setattr(stack_atlas, "ATLAS_LIVE_ROOT", ROOT)
    projected = stack_atlas._bootstrap_execution_node_topology()
    assert projected["routing_policy"]["default_execution_node"] == "omen-linux-laptop"
    assert projected["routing_policy"]["kone_capacity_fallback"] is False
    assert "mandatory_windows_ci_light" in projected["nodes"]["kone-gpu-desktop"]["roles"]
    assert "default_execution" in projected["nodes"]["omen-linux-laptop"]["roles"]


def test_bootstrap_critical_guidance_surfaces_machine_routing():
    guidance = stack_atlas._bootstrap_critical_guidance()
    assert "machine_routing" in guidance
    assert "OMEN is default/required substantive execution" in guidance["machine_routing"]
    assert "KONE is mandatory windows-ci-light only" in guidance["machine_routing"]

def test_bootstrap_compaction_preserves_execution_roles_and_policy():
    policy = {
        "authority": "CURRENT_USER_DIRECTION_AND_SWARM_ROUTING_COHORT",
        "default_execution_node": "omen-linux-laptop",
        "substantive_execution": "OMEN_REQUIRED",
        "kone_execution": "MANDATORY_WINDOWS_CI_LIGHT_ONLY",
        "kone_capacity_fallback": False,
    }
    glance = {
        "schema": "bootstrap.v1",
        "swarm_topology": {
            "authority": "CURRENT_USER_DIRECTION_AND_STABLE_PARTITION_SLOTS",
            "chatgpt_subscription_count": 2,
            "recurring_worker_partitions": {"S1": 5, "S2": 5},
            "recurring_workers_total": 10,
            "routine_recurring_recovery": {},
            "operator_handoff": {},
            "manual_workers": {},
            "execution_nodes": {
                "authority": "CANONICAL_EXECUTION_NODE_IDENTITY",
                "available": True,
                "status": "OK",
                "routing_policy": policy,
                "local_node_id": "kone-gpu-desktop",
                "local_observed_hostname": "KONE",
                "nodes": {
                    "kone-gpu-desktop": {
                        "display_name": "KONE GPU desktop",
                        "route_label": "windows",
                        "machine_class": "desktop",
                        "roles": ["mcp_control_transport", "mandatory_windows_ci_light"],
                    },
                    "omen-linux-laptop": {
                        "display_name": "OMEN Linux laptop",
                        "route_label": "omen",
                        "machine_class": "laptop",
                        "roles": ["default_execution", "portable", "heavy"],
                    },
                },
            },
        },
        "bootstrap": {"critical_guidance": {"machine_routing": "keep"}},
        "workers": {"archive_sample": ["x" * 7000], "attention": ["y" * 7000]},
    }
    bounded = _fit_bootstrap_glance_budget(glance, max_bytes=16_000, compaction_target_bytes=4_000)
    nodes = bounded["swarm_topology"]["execution_nodes"]
    assert nodes["routing_policy"] == policy
    assert "mandatory_windows_ci_light" in nodes["nodes"]["kone-gpu-desktop"]["roles"]
    assert "default_execution" in nodes["nodes"]["omen-linux-laptop"]["roles"]
    assert bounded["bootstrap"]["critical_guidance"]["machine_routing"] == "keep"


def test_github_runner_recovery_requires_intent_confirmation():
    runner = COMPONENTS["github_runner"]
    precondition = runner["recovery_precondition"]
    assert "offline/failed health is evidence only" in precondition
    assert "intended enabled/running state" in precondition
    assert "KONE is never restored as general capacity" in precondition
    assert "windows-ci-light" in precondition
