# Pre-message command / polling trace

## Immediate command sequence most relevant to the reroute

1. `98afd94e-30c9-473e-99b7-82a76903ed6f` — compare avian checkpoint `8a5d776` to current Tiny3D main, archive immutable snapshot, probe CLI entrypoint. Direct `cli.py` invocation failed on package-relative import; no mutation.
2. `62bbcb06-fbb5-43e2-b8f2-bb12d2e092e2` — run package entrypoint + `tests.test_avian`; 71/71 PASS.
3. `4b8be859-687f-44c7-9cd5-b8b165ca0ac4` — inspect exact Eagle/Hummingbird/Owl source references and supported `compile_avian` owner path; output was bounded/truncated at 100k chars.
4. `13133bb9-68df-4a9b-b6c0-dadc2692346c` — inspect `compile_avian` definition and Blender discovery contract.
5. `d3b9fbd8-cfdb-436a-930b-381c90496338` — read exact P3 UAsset `RelativeFilename` metadata for Eagle/Hummingbird/Owl and confirm likely source roots.
6. `fc8ce9a2-0ccc-4f67-8cc9-e3022b99be7d` — inspect source sizes, Blender 5.2, and candidate invocation. `Get-FileHash` was unavailable in that PowerShell host; no source mutation.
7. `175121ae-e27a-4f75-8dd8-a0038285e9e1` — inspect avian worker exit/QA contract and hash exact source files with Python.
8. `cb55decd-1d71-40f3-85bf-8a4a4a83c87d` — Blender 5.2 worker replay on Hummingbird. Three `read_output` observations; process completed successfully.
9. `179451c0-d4dd-4655-8087-f05d0aa0b435` — first Hummingbird verification attempt via raw `importlib` load; failed on package-relative import.
10. `cfba1a0b-e589-424c-9d72-c9e1c0785580` — corrected package import; Hummingbird `verify_portable_avian` ACCEPTED with unchanged QA.
11. `68cb301a-bac4-48ff-8c3c-f2793fbd1c96` — Blender 5.2 worker replay on Eagle. Three `read_output` observations; process completed successfully.
12. `e4a43090-ff1a-49a9-9074-a1fa4c20a769` — verify Eagle, then run Owl worker in the same process call. Three `read_output` observations. Eagle remained fail-closed on BODY stretch; Owl worker completed successfully.
13. `2e436854-52e6-4678-b489-87a30550c207` — verify Owl; remained fail-closed on collapse.
14. `08b81d99-b936-4e51-9c16-c237b51f7045` — exact Busy claim on Tiny3D issue #10, post immutable review evidence, release claim.
15. `fce55e17-0afb-4160-889f-d6e6030ae1ac` — full `compile_avian` Hummingbird portable-pack proof in disposable workspace; two **pre-message** `read_output` polls. Completed exit 0.

## Full visible polling distribution before the user interruption

| Process | Purpose | Runtime | Visible pre-message `read_output` count |
|---|---|---:|---:|
| `28b01a8f-bcaf-498d-8bda-39113d10ec2b` | Tiny3D full CI-equivalent suite | 107.403 s | 13 |
| `cb55decd-1d71-40f3-85bf-8a4a4a83c87d` | Hummingbird Blender worker | 28.436 s | 3 |
| `68cb301a-bac4-48ff-8c3c-f2793fbd1c96` | Eagle Blender worker | 31.450 s | 3 |
| `e4a43090-ff1a-49a9-9074-a1fa4c20a769` | Eagle verify + Owl worker | 24.388 s | 3 |
| `fce55e17-0afb-4160-889f-d6e6030ae1ac` | Hummingbird full pack | 36.434 s | 2 |
| **Total** |  |  | **24** |

The full-suite read sequence included two explicit `no_change=true` responses. The final Hummingbird process had only two pre-message reads, so the immediate event is not evidence for a simple “too many polls on this one process” threshold.

## Earlier visible command categories in the same `go` turn

Before the avian review, the same caller also used bounded `start_process` calls for:

- inspecting and patching the P3 Asset Registry catalog bridge for OBJ import-origin classification;
- focused P3 tests, current-main replay, commit/push, PR creation, merge-guard execution, and issue #10 evidence recording;
- Tiny3D PR #383 state checks, exact-head full-suite proof, main-ref claim, exact-head merge, current-main catalog/job replay, and issue handoff;
- BusyCoordinator claim inspection and immutable checkpoint discovery.

Conversation-visible aggregate for the entire pre-message continuation: **39 `start_process` + 24 `read_output` = 63 process-tool interactions**.

These counts are intentionally labeled conversation-visible. They are suitable for orchestration analysis but are not substituted for transport-level request logs.
