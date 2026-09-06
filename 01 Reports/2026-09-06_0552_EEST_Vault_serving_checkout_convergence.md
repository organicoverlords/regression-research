# Vault serving checkout convergence

Date: 2026-09-06 EEST
Issue: #125
Initial baseline: origin/main `3c7b8d04e95b1a264932eb988dfcdbfd41883a55`; concurrent evidence convergence advanced main to `6901ee25d6bb95891e233c370afcd489d8f49807` before final cleanup
Serving pre-convergence HEAD: `ffb68e1ecf929116f7300b13baf5ba0e5827761d`

## Preservation applied

- `memory/memory-bank.jsonl`: current main was an exact 339-line prefix of serving live; preserved all 15 append-only live records.
- `02 Evidence/mcp-security-routing-events.jsonl` and both MCP incident reports were preserved concurrently by PR #614 / `6901ee25d6bb95891e233c370afcd489d8f49807`. Newline-normalized content was verified identical to the serving evidence before cleanup.
- `04 Operating Contracts/fresh-worker-generation-launch.md`: retained current-main text and ported only the unique route-recovery sentence from the serving checkout.

## Intentionally not transplanted

Already-current-main content was not copied from the stale serving checkout: `memory/README.md`, memory Git-sync/recent/timeline tests, repo timeline tests, and the corresponding memory/repo tools.

Stale/superseded serving units were not copied: `docs/assistant-stack-operational-atlas.md`, `tools/stack_atlas.py`, `tests/test_stack_atlas.py`, `tools/worker_report_history.py`, `tests/test_worker_report_history.py`, local `tests/test_bootstrap_health.py`, and local `04 Operating Contracts/mcp-known-good-freeze.json`. Current main remains authoritative for those files.

## Unresolved local-only material preserved without activation

The serving checkout carried a test-only ownership-collision assertion patch with no matching current contract implementation. It is preserved below exactly as a review artifact and is not applied to current tests:

```diff
--- origin/main/tests/test_memory_bootstrap.py
+++ serving-live/tests/test_memory_bootstrap.py
@@ -37,18 +37,17 @@
 
         self.assertIn("The scheduler provides recurrence only", text)
         self.assertIn("Workers never administer workers", text)
-        self.assertIn("About 24 minutes remains the timed utilization target", text)
-        self.assertIn("existing >=80% completion guard", text)
-        self.assertIn("Utilization never requires creating a new work identity", text)
-        self.assertIn("work identity follows the canonical shared issue-first rules", text)
+        self.assertIn("About 24 minutes is a utilization target", text)
         self.assertIn("A blocker changes scope; it does not end unrelated work", text)
+        self.assertIn("ownership collision is a scope-redirection event, not a stopping condition", text)
+        self.assertIn("do not end a run or return `blocked by ownership`", text)
+        self.assertIn("expand to an adjacent unclaimed slice", text)
+        self.assertIn("help the owning work with read-only analysis/evidence/support", text)
         self.assertIn("BusyCoordinator is collision control only", text)
         self.assertIn("worker-reports/current/<automation-id>.md", text)
         self.assertIn("Near the start of every timed run", text)
         self.assertIn("before any command that may consume a material part of the useful run window", text)
         self.assertIn("`state: RUNNING`", text)
-        self.assertIn("`state: TOOL_INTERVAL_OPEN`", text)
-        self.assertIn("artifact lifecycle state only and never process liveness", text)
         self.assertNotIn("metrics.json.latest_reports", text)
         self.assertNotIn("PENDING_REVIEW", text)
         self.assertNotIn("Remote Desktop Commander", text)
```

The serving checkout also carried an untracked P3 runtime tooling receipt with no established durable consumer. Its exact content is preserved here rather than keeping `Saved/` dirty:

```json
{
  "route": {
    "kind": "PYTHON",
    "executable": "C:\\Users\\Lauri\\AppData\\Roaming\\uv\\python\\cpython-3.11.15-windows-x86_64-none\\python.exe",
    "version": "Python 3.11.15",
    "provenance": "PREINSTALLED_KNOWN",
    "probe_status": "PASS",
    "arguments_prefix": []
  },
  "network": {
    "listener": false,
    "bind": null,
    "exposure": "NONE"
  },
  "unattended": {
    "prompt_observed": false,
    "fallback_used": false,
    "route_rejection": null,
    "attempts": [
      {
        "executable": "C:\\Users\\Lauri\\AppData\\Roaming\\uv\\python\\cpython-3.11.15-windows-x86_64-none\\python.exe",
        "command": "C:\\Users\\Lauri\\AppData\\Roaming\\uv\\python\\cpython-3.11.15-windows-x86_64-none\\python.exe  --version",
        "outcome": "PASS",
        "version": "Python 3.11.15",
        "reason": "",
        "prompt_observed": false
      }
    ]
  }
}
```

Receipt SHA-256: `2ac1256c7bd27c597967b4731f52c5b1d8bf84ea01a233c7469a5ef9dbc2cff4`.

## Recovery copy

Before cleanup, the full tracked binary diff and every untracked file were copied outside the repo to:
`C:\Users\Lauri\AppData\Local\Temp\vault-serving-convergence-backup-20260906-055052`

Tracked patch SHA-256: `2c6c386002c1d964e59f8fbc28f5504fda182edb43f3e03937c4ddd0809aa4c0`.
This recovery copy is rollback evidence only; current repo truth is the converged main content above.
