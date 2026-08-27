# Issue #122 canonical claim-to-evidence ledger

Snapshot basis:
- Git `origin/main`: `1b192cd1b5745e5c5e535f9737fe5f8a0a650c23`
- GitHub issue #122 canonical body `updatedAt`: `2026-08-27T11:56:41Z`
- canonical body SHA-256: `2d61ca86f4047d9f00c4eab04d627930d99a7d70fa1f1063acce21a48b1ccd78`

Purpose: make the canonical report auditable without turning later synthesis into stronger evidence than its sources. This ledger is a forensic index, not a new causal experiment and not an assistant-stack design.

## Evidence tiers

- **A - preserved primary artifact:** exact bytes, screenshot, transport/result record, or exact pre/post rule block committed in this repository.
- **B - deterministic derived artifact:** a committed analysis/fixture derived from preserved inputs with explicit causal limits.
- **C - published raw-chat forensic extraction:** an issue comment that reports a bounded read of raw conversation evidence. It is pinned by immutable comment ID and body SHA-256, but it remains secondary to the underlying raw conversation bytes.
- **D - canonical synthesis:** the issue body or later summary comment. D is useful for navigation only and never upgrades A/B/C evidence.

## Core repository evidence

| ID | Tier | Artifact | SHA-256 | Git blob | What it can support |
| --- | --- | --- | --- | --- | --- |
| E01 | A | `02 Evidence/issue122/2026-08-25_122229_EEST_pre-repair-memory-block.txt` | `6db44de30f4871a54f2552c344677f176bae5520d0593b0669b404a7c145dede` | `68ab12a4b020bbed39e1e555658454637145d2b9` | Exact 12:22 pre-repair user-visible memory block. |
| E02 | A | `02 Evidence/issue122/2026-08-25_123749_EEST_repaired-memory-block.txt` | `313fe9ef220e769434b2d218f90e39e53afe007b5b2e500c6c02ce570ea21c3a` | `104c560f16379810003bd4fe2d5cdfe1ef277ba1` | Exact 12:37 repaired user-visible memory block. |
| E03 | B | `02 Evidence/issue122/2026-08-25_1226-1237_rule-provenance.md` | `1258355ba565fab866ac91fa026c5f7c6ca26fd27cea0b2eb0cc343c455853ca` | `8ad8e2290f73e5b3467685aa1145a4180097ee92` | Provenance that the 12:26 rewrite lacked the missing-tool safeguard and the post-12:30 repaired state restored it. |
| E04 | B | `02 Evidence/issue122/2026-08-25_1230-1244_behavior-boundary.md` | `411ea5fc4af6c79704a9e2be87fd8764a75e81c6fbeef3f920247bb066e0c5f9` | `90d6dba38a46d15efad9905b0f80816ca2acf78b` | User-visible 12:30 failure vs 12:40-12:44 successful fresh-chat behavior; explicitly leaves delivery mechanism open. |
| E05 | B | `02 Evidence/issue122/2026-08-25_1230_interruption-tool-discovery-boundary.md` | `5fea34c816a0ced986c526c81de59db3ea4d2f5c53e5c52254b1ddafce15363e` | `d56f22bf9a9d6e9c243614e84cf07f881cbaa5d1` | 12:30 is an interruption/continuation failure, not a fresh-chat control; tool absence must be tested before promoted to unavailability. |
| E06 | B | `02 Evidence/issue122/2026-08-25_1226-web-activation-local-negative.md` | `e309e3d2118acc779835136f82f4cf3e74bd716dd51abd4b4c5c78f404066e18` | `20d2bd49e29bff3b422a35cafebc6146d53181e7` | Existing local sources contain no direct Settings-application witness; does not prove Web PI was never applied. |
| E07 | B | `02 Evidence/issue122-2026-08-26_1819-finalization-mechanism.json` | `d6466d46cd3e0957be1b0ad774c28bbd868b60912ac01039bd753b08955bc99f` | `eac19a4afae94527f16c72f2ae550dbb8263f097` | 18:19 completion-classification error: unmet in-scope acceptance was downgraded to optional hardening instead of consuming `READ_SAME_PROCESS_ID`. |
| E08 | B | `02 Evidence/issue122/2026-08-26_1819-terminal-ordering.json` | `5108466f5bfdddd3d13f21c2351645f92f5831cd806640706c0a5abd1d878ac1` | `9d7e1baaf0ecfc0342e608ca16a36ffedbdf7811` | Ordinary successful model stop, unread required result, and rejection of a universal ~24m45 cutoff; its older ?first recurrence? wording is superseded by C05 below. |
| E09 | B | `02 Evidence/issue122/2026-08-27_policy-feedback-loop-boundary.json` | `97ac772f3a28467f1d0fdf0f99bf0ef458f71412b70b2cb6dce1aee1690f3745` | `4c21de3428d809eea01c4c80c33bd0be2d46b940` | Policy-amplification cycle is partially proven; active-tail is neither sufficient for persistence nor necessary for overprocessing. |
| E10 | B | `02 Evidence/issue122/2026-08-27_scope-expansion-causal-decomposition.json` | `ae068929639513d8a8f0780fb9922e80a4fed41dea244023b631a35045915cd6` | `13d5ed7cd4f6113ac01f4975d4e9868e126e12ac` | Separates unrelated-defect adoption from a post-acceptance procedural integration tail; latter recurs before v1.15 active-tail. |
| E11 | B | `02 Evidence/issue122-fresh-chat-regression-matrix.json` | `c09bfafd04ff4eab3b789babb14fe32961ee1f3642a0f17cfc48762a2362f23d` | `0a607e4b78431e29d044faef7db3e473d082f07b` | Eight historical controls, 8/8 fixture pass; calibration evidence, not authorization for a live configuration change. |
| E12 | B | `03 Fixtures and Experiments/issue122-acceptance-boundary-classification.json` | `598721d3cc81fa33ac2ccda4ae82a0a8929f9d08bea9fb157c867925562f2caf` | `dc11e6d50172692bb7a9e23f704864b1afcba577` | Encodes the task-local acceptance boundary: unmet acceptance must continue; satisfied acceptance plus incidental activity may stop. |
| E13 | A | `02 Evidence/issue122/2026-08-25_123045_EEST_mcp-unavailable-before-rule.png` | `9915df835c8a652cc3fcc5d26aa42e9d5f74e1ea56037c535a149bc70de2f232` | `627df960164f9a0f8a7dbeb8b626ac327e22ab03` | User-visible pre-repair MCP refusal. |
| E14 | A | `02 Evidence/issue122/2026-08-25_124351_EEST_fresh-memory-work-executes.png` | `7cbd14a6d12db72540336372e9793f7a9dd29733390f92744b123ecfa8873362` | `f29425bd5e0df7fc62413465353edc07ed9eff20` | User-visible fresh memory-work execution after repaired state exists. |
| E15 | A | `02 Evidence/issue122/2026-08-25_124358_EEST_fresh-p3-work-executes.png` | `4ffad90bd3f4c57c4ac69007f4492b672edeaf65d7f040d9cf7b2a153071ef52` | `4834a4f65c685cf27aa74933769627226740c3f2` | User-visible fresh P3 execution after repaired state exists. |
| E16 | A | `02 Evidence/issue122/2026-08-25_124403_EEST_fresh-memory-work-replicate.png` | `3fb8be76c56bf96a3404d418c273cb9e1e33902f7b26c55f2dd3540a78bdfa0b` | `7818c5c24f53aab189d6651a8cea5cb77ff0f503` | Independent fresh memory-work replication. |

## Raw-chat forensic extraction anchors

These comments are pinned because several newer boundary corrections have not yet been promoted into standalone repository artifacts. They are **Tier C**, not primary bytes.

| ID | Issue comment | Body SHA-256 | Extraction |
| --- | --- | --- | --- |
| C01 | `#5437836160` | `92abf8575306ce93648c8c75b07e768b0cbb74140896002cf130854fc2649b02` | v1.15 origin correction: user authorized fixing defects; implementation overgeneralized them into a global completion gate. |
| C02 | `#5437871872` | `57acb5547448714bec5fe6704962ee15da9de00293f62c780c72015802fd6ded` | 20:28 user theory -> shared Git-specific policy mutation before experiment -> user stops/rolls it back. |
| C03 | `#5437880486` | `09161ca42777080345c9406e84b6a352f0e2aebd2291febeb89e0a68003cdf30` | Controlled follow-up rejects the Git-specific timeout theory. |
| C04 | `#5437893598` | `5766df957b774f39880f5c54c0821a1e4bf9547218790b8d04d1d3d38a1bae71` | 21:03 authorization does not substitute for discovering the real mechanism; invented queue gate does not land. |
| C05 | `#5437944987` | `0c1f70acf6322a0f0456bfcef32a8db57cd046c11dff982d7f7c777760f9e21e` | 17:43 is the earliest currently confirmed direct-assistant recurrence found after the established good state. |
| C06 | `#5437949954` | `df8821268aefc13588bf3ddc3038b804143967034434635878bc697806d5e028` | 17:10 ?finally working? is a swarm/workflow statement, not standalone direct-assistant-health evidence. |
| C07 | `#5437965494` | `b63c51aeec19193bcb39c7d1d086a1c5d59e8c382f0f21e3a0901bb52857cf23` | Self-generated false-boundary candidate: unsupported `tool time ended` explanation is semantically reused at 17:43 and 18:19. |
| C08 | `#5437976300` | `e0132d3ea35c25a8c4eb376d3497501c77c2656e8ae1df1904a678937281b5f3` | Stronger provenance: worker had already retracted the phrase as invented before the main assistant reified it as platform fact. |
| C09 | `#5438342690` | `c4e089df1f8382197ee31b215f1a6a0e1cb7e90c8e5b0489259b6e8e1fd333c1` | Good-state survival matrix and positive direct-work controls. |
| C10 | `#5438348955` | `5ba601ad85d4a60311e9ab2ec166b990d0989d5e34a103024249b6d004466162` | Good-state survival ledger; smallest evidence-backed behavioral kernel. |
| C11 | `#5438418459` | `e9a4858d7a08a3eeb9ce887f08a6a4323bb6a5a12216fe519b09d37b8e62f93e` | 18:52 -> 20:06 Settings correlation is model-confounded and not a clean PI A/B. |

Canonical URLs are `https://github.com/organicoverlords/regression-research/issues/122#issuecomment-<id>` for each C-row.

## Canonical claim ledger

| Claim | Current classification | Supporting evidence | Causal/epistemic limit |
| --- | --- | --- | --- |
| K01. Fresh-chat strong-good behavior is established by 12:40-12:41 Aug 25, after the repaired rule block exists. | **Established behavior boundary** | E01-E05, E13-E16 | Does not identify which hidden delivery surface injected the repaired behavior. |
| K02. The good state is not explained by one magic prompt; positive controls support a compact kernel: immediate bounded execution, live-state reconciliation, capability attempt before absence, correction precedence, task-local route resilience, acceptance-matched proof, worker/main separation. | **Supported survival kernel** | E11, C09, C10 | This is a behavior-survival inference, not a claim about OpenAI internal instruction ranking. |
| K03. 17:43 Aug 26 is the earliest currently confirmed direct-assistant premature-finalization recurrence found after the established good state. | **Established current boundary** | C05; C06 prevents the 17:10 misclassification | C05 is a forensic extraction pending standalone artifact promotion; ?earliest currently found? is not ?first possible occurrence.? |
| K04. 18:19 is a completion-classification error: an unmet in-scope acceptance criterion was downgraded to optional hardening and the assistant finalized instead of consuming the required process continuation. | **Established mechanism for that turn** | E07, E08, E12 | It is no longer the earliest known direct recurrence; it remains the strongest instrumented instance. |
| K05. A deterministic ~24m45/~26-minute cutoff, raw tool count, gross context size, explicit truncation, or +2 ms result/final ordering does not distinguish the failure. | **Rejected as simple deterministic explanation** | E07, E08; canonical negative controls | Does not exclude softer context/effort pressure as a probabilistic contributor. |
| K06. `tool time ended` underwent a provenance-classification failure: assistant-authored/retracted status text was promoted to unsupported platform fact and then reused semantically at later premature finals. | **Generation/reification/reuse established; causation open** | C07, C08; E07/E08 independently reject the claimed cutoff | No intervention proves the 17:16 explanation mechanistically caused the 17:43 or 18:19 decisions. |
| K07. v1.13 cannot be the origin of the first currently confirmed direct recurrence because 17:43 predates it. | **Falsified as origin** | C05 plus policy chronology summarized in E09 | Does not prove v1.12 or other policy/context pressure caused 17:43. |
| K08. v1.15 active-tail was an authorized fix with an overgeneralized implementation; it is neither sufficient to prevent premature stopping nor necessary for procedural overprocessing. | **Partially proven policy-amplification relation** | E09, E10, C01 | One clause is not established as the cause of all later failures. |
| K09. User hypotheses/error reports do not justify promotion into durable/shared authority before testing; the 20:28 Git theory was promoted first and later experimentally rejected. | **Established historical promotion failure** | C02, C03 | This supports promotion discipline; it does not imply user hypotheses are unreliable or require proof before the user may change behavior. |
| K10. Authorization to fix/change establishes permission and objective, not a proven diagnosis or known implementation mechanism. | **Established distinction from historical cases** | C01, C04 | The user does not need to prove a preference or requested behavioral change; the constraint is on the assistant inventing causal/mechanistic facts while implementing it. |
| K11. The 21:52 Persistent Execution rule and the 18:52 -> 20:06 Settings sequence are not clean causal A/Bs because model family changes across the behavioral boundary. | **Causal attribution open/model-confounded** | C11; canonical raw request metadata for 21:52 | Behavioral contrast remains real; only prompt/Settings causality is unproven. |
| K12. Existing local archaeology does not identify whether repaired fresh-chat behavior arrived via Web Personal Instructions, Saved Memory, or another injected-context mechanism. | **Open; local source class exhausted** | E04, E06 | Reopen only with a genuinely new source class or an explicitly authorized same-model delivery canary. |
| K13. Completion should be driven by inherited task-local acceptance: unmet acceptance -> continue; satisfied acceptance plus unrelated activity -> stop cleanly. | **Regression invariant supported by opposite-case evidence** | E07, E10, E12 | This is the bounded correction to both premature stopping and runaway active-tail behavior; it is not a global ?never stop? rule. |
| K14. Worker/swarm success is not direct-assistant success and worker-authored state is not platform telemetry. | **Established provenance/authority separation** | C06, C08, C10 | Worker evidence may still be relevant evidence; it simply cannot silently become main-assistant or platform authority. |

## Supersession rules

1. If a Tier C finding is later promoted into a committed A/B artifact, add the new artifact and keep the C-row only as provenance; do not delete the historical extraction.
2. If a newer primary artifact contradicts a derived artifact, update the claim classification and mark the older derived wording superseded rather than rewriting its historical bytes.
3. The canonical issue body may summarize this ledger, but body edits are Tier D and cannot increase confidence by repetition.
4. Open delivery/causal questions stay open until the required evidence class exists. Absence of a surviving local witness is not proof that an event did not occur.
5. No entry in this ledger authorizes a live ChatGPT Personal Instructions, Saved Memory, Settings, personality, or other configuration mutation.
