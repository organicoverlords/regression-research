# S1 Visual Proof Sprint Mission

This file is the current mission brief for the five S1 timed workers.

**This is an additive mission file only. It must never replace, shorten, simplify, or stand in for the full recurring-worker launcher/prompt, shared RULES.md, AGENTS.md, or fresh-worker-generation-launch.md contract. S1 workers keep the same long-form timed-worker reasoning, utilization, recovery, routing, work-selection, convergence, and reporting behavior; this file only changes the S1 mission emphasis.**

## Mission

Act as a coordinated visual-proof improvement swarm. Improve the end-to-end route from GPT-generated or GPT-selected visual intent/assets, through the shared asset/library layer, into the live P3 game world, and finally into reviewable visual proof.

The goal is not merely to produce more screenshots or assets. Make the whole route smoother, faster, more reliable, easier to inspect, and easier to iterate:

**GPT intent/reference -> asset/library selection or generation -> library qualification -> game-world placement/use -> capture -> independent visual review -> fix -> recapture -> PROVEN**

## What S1 workers should optimize

- Reduce friction moving a useful visual idea or generated asset into the qualified library and then into the actual game world.
- Find and fix broken handoffs, unnecessary manual steps, confusing paths, stale wrappers, missing metadata, weak previews, bad defaults, or proof gaps along that route.
- Prefer improvements to the existing canonical path over creating parallel pipelines.
- Reuse existing qualified assets and existing WIP before generating or importing duplicates.
- Make visual review fast: canonical viewpoints, stable capture inputs, easy comparison to previous captures, and exact artifact/run identity.
- Make failures legible: distinguish generation failure, library qualification failure, import/material failure, world-placement failure, camera/capture failure, and actual visual-quality failure.
- Keep the game-world result as the acceptance target. A library entry, generated mesh, build, or screenshot path alone is not success.

## Swarm behavior

The five S1 workers should behave like one sprint swarm around the same route, not five unrelated implementers.

Useful contributions include:

- removing one concrete bottleneck in the GPT -> library -> game route;
- improving asset preview/qualification so bad assets are rejected before expensive world integration;
- improving library metadata or lookup so GPT can reliably choose the right existing asset;
- making materialization/import into Unreal more deterministic;
- improving placement, scale, materials, lighting, camera, or capture behavior when that is the visible blocker;
- comparing the latest candidate against previous/baseline captures and identifying regressions;
- independently reviewing another worker's capture and recording visible defects;
- tightening the supported proof route so a new candidate can be captured and reviewed with less ceremony.

Do not all edit the same scene or asset at once. Prefer independent review, proof, tooling, library, import, and integration slices around the same current candidate. Existing WIP wins over duplicate implementation.

## Visual proof rule

The producer must inspect its own rendered pixels before handoff. The producer may reject its own capture or mark it NOT_PROVEN, but must not promote its own work to PROVEN. Final PROVEN requires independent visual review by another worker.

A useful review should identify concrete visible findings such as framing, silhouette, scale, material response, lighting, readability, camera behavior, environment coherence, gameplay readability, or regression against the previous best capture.

## Default priority

When several useful actions are available, prefer the one that most reduces the time and uncertainty between:

1. having a good visual idea or asset available to GPT,
2. finding/qualifying it in the shared library,
3. seeing it correctly in the actual game world,
4. capturing it reliably,
5. getting an independent visual verdict,
6. applying the next fix.

The sprint succeeds when this loop becomes materially smoother and the actual game world looks better under independent review.


## Timed-worker execution posture

The S1 timed-worker launcher is intentionally long, demanding, and non-blocking. This mission file supplies the visual objective; it does not supply the worker's full reasoning posture by itself.

S1 workers should use sustained reasoning, inspect real evidence, challenge weak assumptions, compare alternatives, and continue through useful non-conflicting work for the timed run window. A blocked build, runtime, editor, generation job, capture route, exact Busy scope, PR gate, or another worker's mutation does not end the run when another useful contribution remains inside this same GPT -> library -> game-world -> visual-proof objective.

Non-blocking does not mean filler. When one action is blocked, preserve its gate and move to the highest-value ready contribution in another stage of this same pipeline: retrieval, qualification, library metadata, materialization, integration, capture, visual review, regression comparison, tooling repair on the supported path, convergence, or handoff. Yield early only under the canonical true-no-safe-work condition.

The standard to aim for is challenging: do not settle for the first technically passing route or the first plausible screenshot. Ask what would make the next visual iteration materially faster, clearer, more deterministic, and more visually convincing in the actual game world, then improve the existing owner that most limits that outcome.
