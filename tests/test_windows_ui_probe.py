import os
import unittest
from unittest.mock import patch

from tools import windows_ui_probe


class WindowsUiProbePureTests(unittest.TestCase):
    def test_parent_chain_is_bounded_and_cycle_safe(self):
        processes = {
            10: {"pid": 10, "ppid": 20, "name": "child.exe", "path": "C:/child.exe"},
            20: {"pid": 20, "ppid": 30, "name": "parent.exe", "path": "C:/parent.exe"},
            30: {"pid": 30, "ppid": 20, "name": "cycle.exe", "path": "C:/cycle.exe"},
        }
        chain = windows_ui_probe._parent_chain(processes, 10, max_depth=8)
        self.assertEqual([row["pid"] for row in chain], [10, 20, 30])

    def test_parent_chain_reports_unknown_pid_without_guessing(self):
        chain = windows_ui_probe._parent_chain({}, 77)
        self.assertEqual(chain, [{"pid": 77, "ppid": None, "name": None, "path": None}])

    def test_diff_events_reports_foreground_change_and_new_window_once(self):
        previous = {
            "foreground": {"hwnd": 100},
            "visible_windows": [{"hwnd": 100}],
        }
        current = {
            "captured_at": "2026-09-13T00:00:01Z",
            "foreground": {"hwnd": 200, "pid": 2},
            "visible_windows": [{"hwnd": 100}, {"hwnd": 200, "pid": 2}],
        }
        seen = {100}
        events = windows_ui_probe._diff_events(previous, current, seen)
        self.assertEqual([event["kind"] for event in events], ["foreground_changed", "visible_window_created_or_discovered"])
        self.assertEqual(events[0]["previous_hwnd"], 100)
        self.assertEqual(seen, {100, 200})
        self.assertEqual(windows_ui_probe._diff_events(current, current, seen), [])

    def test_watch_rejects_unbounded_or_too_fast_requests(self):
        with self.assertRaises(ValueError):
            windows_ui_probe.watch(windows_ui_probe.MAX_WATCH_SECONDS + 1, 100)
        with self.assertRaises(ValueError):
            windows_ui_probe.watch(1, windows_ui_probe.MIN_INTERVAL_MS - 1)

    def test_watch_emits_attribution_events_from_bounded_samples(self):
        samples = [
            {
                "status": "OK",
                "captured_at": "2026-09-13T00:00:00Z",
                "foreground": {"hwnd": 1, "pid": 10},
                "visible_windows": [{"hwnd": 1, "pid": 10}],
            },
            {
                "status": "OK",
                "captured_at": "2026-09-13T00:00:01Z",
                "foreground": {"hwnd": 2, "pid": 20},
                "visible_windows": [{"hwnd": 1, "pid": 10}, {"hwnd": 2, "pid": 20}],
            },
        ]
        with patch.object(windows_ui_probe, "capture", side_effect=samples), patch.object(
            windows_ui_probe.time, "monotonic", side_effect=[0.0, 0.0, 1.0]
        ), patch.object(windows_ui_probe.time, "sleep"):
            result = windows_ui_probe.watch(0.5, 100)
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["samples"], 2)
        self.assertEqual(
            [event["kind"] for event in result["events"]],
            ["foreground_changed", "visible_window_created_or_discovered"],
        )


@unittest.skipUnless(os.name == "nt", "Windows-only Win32 attribution smoke test")
class WindowsUiProbeBehaviorTests(unittest.TestCase):
    def test_capture_returns_visible_window_attribution(self):
        payload = windows_ui_probe.capture()
        self.assertEqual(payload["status"], "OK")
        self.assertIn("captured_at", payload)
        self.assertIsInstance(payload["visible_windows"], list)
        for window in payload["visible_windows"]:
            self.assertGreater(int(window["hwnd"]), 0)
            self.assertIn("pid", window)
            self.assertIn("process_name", window)
            self.assertIn("executable", window)
            self.assertIsInstance(window["parent_chain"], list)
            self.assertLessEqual(len(window["parent_chain"]), windows_ui_probe.MAX_PARENT_DEPTH)


if __name__ == "__main__":
    unittest.main()
