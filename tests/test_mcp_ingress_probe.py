import json
import tempfile
import unittest
from pathlib import Path

from tools.mcp_ingress_probe import ProbeStep, _read_new_jsonl, _target_path, classify_observation, load_plan


class McpIngressProbeTests(unittest.TestCase):
    def test_classifies_pre_backend_drop_when_transport_fails_without_arrival(self):
        result = classify_observation(status=None, error="TimeoutError", backend_events=[], request_id=None)
        self.assertEqual(result, "PRE_BACKEND_OR_EDGE_DROP")

    def test_failed_request_with_uncorrelated_backend_activity_stays_ambiguous(self):
        events = [{"event": "request_start", "request_id": "r1"}]
        result = classify_observation(status=None, error="RemoteDisconnected", backend_events=events, request_id=None)
        self.assertEqual(result, "FAILURE_WITH_UNCORRELATED_BACKEND_ACTIVITY")

    def test_response_request_id_proves_backend_arrival(self):
        events = [{"event": "request_start", "request_id": "abc"}]
        result = classify_observation(status=401, error=None, backend_events=events, request_id="abc")
        self.assertEqual(result, "BACKEND_ARRIVED")

    def test_response_without_backend_telemetry_is_not_called_backend_proof(self):
        result = classify_observation(status=200, error=None, backend_events=[], request_id=None)
        self.assertEqual(result, "EDGE_RESPONDED_BACKEND_UNOBSERVED")

    def test_path_prefix_is_preserved(self):
        self.assertEqual(_target_path("/clone-a", "mcp"), "/clone-a/mcp")
        self.assertEqual(_target_path("/clone-a", "/.well-known/oauth-protected-resource/clone-a/mcp"), "/.well-known/oauth-protected-resource/clone-a/mcp")
        self.assertEqual(_target_path("", "health"), "/health")

    def test_jsonl_reader_is_cursor_bounded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "transport.jsonl"
            first = json.dumps({"event": "request_start", "request_id": "a"}) + "\n"
            path.write_text(first, encoding="utf-8")
            events, offset = _read_new_jsonl(path, 0)
            self.assertEqual([event["request_id"] for event in events], ["a"])
            with path.open("a", encoding="utf-8") as handle:
                handle.write("{bad\n")
                handle.write(json.dumps({"event": "request_start", "request_id": "b"}) + "\n")
            events, _ = _read_new_jsonl(path, offset)
            self.assertEqual([event["request_id"] for event in events], ["b"])

    def test_plan_accepts_structured_body_and_string_headers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "plan.json"
            path.write_text(json.dumps([{"method": "post", "path": "mcp", "body": {"jsonrpc": "2.0"}, "headers": {"content-type": "application/json"}}]), encoding="utf-8")
            steps = load_plan(path)
            self.assertEqual(steps, [ProbeStep("POST", "mcp", '{"jsonrpc":"2.0"}', {"content-type": "application/json"})])


if __name__ == "__main__":
    unittest.main()


