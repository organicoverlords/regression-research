# S1 Model-Bearing Visual Library Catalogue Mission

This file is the current additive mission brief for the five S1 timed workers.

**This file supplements, and never replaces or shortens, the full recurring-worker launcher, `RULES.md`, `AGENTS.md`, and `fresh-worker-generation-launch.md`. All normal reasoning, utilization, recovery, collision, routing, issue/WIP convergence, proof and reporting behavior remains active.**

## Single S1 objective

All five S1 timed workers focus on one convergence issue until the user changes direction or the issue is actually complete:

**Tiny3D #442 — Exhaustively visually audit and fulfill the model-bearing asset catalogue newest-to-oldest**
https://github.com/organicoverlords/tiny3d/issues/442

Do not select unrelated P3 visual polish, generic proof cleanup, animation work, catalogue infrastructure, asset generation, or other visual tasks merely because they are available. They are in scope only when current evidence shows they are the smallest load-bearing action needed to advance #442.

The five workers are one catalogue-fulfillment swarm. Reconcile #442, its linked WIP, exact current asset identities, and exact collision scopes before starting new work. Existing coherent WIP wins. Workers must not all mutate or render the same asset at once; take genuinely independent uncovered contributions from #442.

## Population and order

The campaign processes only real model-bearing assets:

- `.glb`
- `.ply`
- Unreal materialized/model content represented by `.uasset` / exact UE mesh identity

Image-only, screenshot-only, thumbnail-only, prompt-only, and preview-only records are **not** catalogue work items. Images are evidence after a real model identity is established; they are never substitutes for inspecting the model.

Start with the **newest generated/model-bearing asset and work backward** using canonical generation/creation provenance. Persist the ordering basis. Do not use filename sorting as a fake creation order when stronger provenance exists.

If the newest item is blocked on one exact dependency, preserve the gate and advance another independent contribution on that same item or the next newest unresolved eligible item. Do not jump to unrelated work.

## Per-asset completion contract

Every eligible asset must eventually have one explicit audited catalogue state. A completed audit requires all applicable items below, with unknowns left explicit rather than guessed.

### 1. Identity and provenance

Resolve and record:

- canonical logical/content/Tiny3D identity;
- exact source/model payload path, type and hash;
- source/generator provenance and best generation/creation timestamp evidence;
- exact variant/family relationships without collapsing distinct meshes or visual variants;
- exact P3/UE materialized mesh/content identity when one exists or is expected.

Never assume two records are the same asset because names look similar.

### 2. Naming once and correctly

Establish one canonical human-readable display name per logical asset and preserve all previous identifiers as searchable aliases, including when applicable:

- source filename/stem;
- generator/output name;
- old catalogue name;
- Tiny3D asset id/content hash;
- UE package/object path;
- historical aliases and misspellings that are already in use.

Canonical naming must be semantic and evidence-backed, not a cleaned-up filename guess. Search by any retained alias should resolve to the same canonical record when identity is unambiguous.

Do not blindly mass-rename `.uasset` packages. If a physical UE rename is truly required, use the existing redirector-aware Unreal owner and prove references remain valid. Canonical catalogue naming/aliasing is mandatory even when the physical package name is retained.

### 3. Standardized twelve-view inspection of the actual model

Every audited model gets a deterministic 12-view visual inspection set from the actual verified payload, not merely an existing thumbnail or historical screenshot.

Use one stable twelve-view convention that gives full 360-degree horizontal silhouette coverage plus useful elevated/depressed coverage so geometry, topology, material and proportion faults cannot hide behind a hero angle. Persist view labels, camera convention and exact source identity.

For `.glb` / `.ply`, use the existing supported headless/offscreen model rendering owner. For UE-only/materialized `.uasset` meshes, use the existing supported Unreal capture owner. Reuse and repair existing owners rather than creating another rendering pipeline.

The worker performing the audit must inspect the resulting pixels.

### 4. Source/library model versus actual UE mesh

Treat the source/library model and the UE materialized mesh as separate identities until evidence proves equivalence.

When a UE mesh/content identity exists or should exist:

- resolve the exact UE package/object;
- compare identity, geometry, scale/orientation, materials and visible result against the source/library model;
- classify mismatches such as wrong mesh binding, stale materialization, geometry change, variant substitution, scale/orientation drift, material divergence, naming collision, missing lineage or unknown;
- when actual UE content differs materially, produce a standardized 12-view set from the **actual UE mesh** and compare source/library and UE view sets directly;
- do not promote a name match, import receipt or path match into visual equivalence.

If the UE mesh is the authoritative current game asset and the library model is stale/wrong, record that explicitly and route the repair through the existing Tiny3D/P3 identity/materialization owner rather than hiding the mismatch.

### 5. Correct metadata and searchable description

Populate or repair the existing canonical catalogue surfaces with factual metadata including as applicable:

- category and semantic role;
- tags and aliases;
- concise factual searchable description;
- dimensions/bounds and scale/orientation/pivot notes;
- triangle/topology facts;
- material slots, texture maps/resolution/transparency and visible material behavior;
- rig/skeleton/skin/blend shapes;
- animation/deformation capability and known limitations;
- LOD/collision information when established;
- Tiny3D/P3 strongest proof states and explicit gaps;
- exact visual-review artifact identities.

Use the existing Tiny3D catalogue/library list/search/show owner established by #311. Do not create a second catalogue database or Vault-only truth store.

### 6. Visual analysis, faults and rating

Each asset receives an explicit visual assessment based on the actual 12-view pixels. Record concrete findings such as:

- silhouette quality;
- proportions and shape readability;
- obvious geometry/topology defects;
- holes, floating parts, self-intersection or clipping;
- normals/shading artifacts;
- UV/texture defects;
- material plausibility and response;
- asymmetry or duplicated/Janus features;
- scale/orientation/pivot problems;
- likely gameplay/readability suitability;
- mismatch against the UE version when applicable.

Use one stable rating rubric across the campaign. A score without rationale is insufficient. Record fault severity and enough text that ChatGPT can later search for assets by strengths, weaknesses or failure modes.

### 7. Aggregate ranking and fault catalogue

Maintain deterministic aggregate outputs from the per-asset records so ChatGPT/workers can answer without rescanning raw directories:

- total eligible assets;
- audited / unaudited / blocked counts;
- newest-to-oldest ordered queue and current next unresolved item;
- category/role counts;
- best-rated assets overall and by meaningful category;
- worst-rated assets overall and by meaningful category;
- exact faults for low-rated assets;
- source/library ↔ UE mismatch list;
- missing-12-view list;
- missing-UE-comparison list;
- naming conflicts and alias collisions;
- metadata gaps;
- duplicate and variant families without collapsing distinct visual variants.

The canonical searchable data belongs in the existing Tiny3D catalogue/library surfaces. Stack Atlas should navigate ChatGPT to those surfaces. Vault may preserve campaign history, reports and evidence, but it is history/evidence rather than a competing current asset authority.

## Visual-proof discipline

Actual rendered pixels are required for visual claims. Structural verification, manifests, hashes, technical metadata and historical thumbnails are supporting evidence only.

A producer must inspect its own output and may mark it REJECTED / NOT_PROVEN with concrete visible findings. Where the existing proof contract requires independent review for PROVEN, retain that independent-review requirement; this mission does not weaken it.

Do not generate a new asset merely because the current one is poor. Generation is in scope only when #442 reaches a genuine missing/replacement asset requirement through an existing owner. The primary task is inventory, inspection, comparison, naming, metadata, ranking and searchable catalogue fulfillment.

## Non-blocking five-worker behavior

A blocked render, Unreal lane, GPU job, exact Busy scope, CI/merge gate, missing proof path or another worker's current asset mutation blocks only that contribution.

Useful independent #442 contributions include:

- resolving the deterministic eligible population and newest-to-oldest order;
- auditing a distinct current asset's 12 views;
- resolving a distinct asset's UE identity and comparison;
- generating UE 12 views for a proven mismatch;
- fixing canonical names/aliases/search metadata for distinct assets;
- repairing an existing renderer/catalogue/import owner that directly blocks current audits;
- writing or validating per-asset factual metadata/rating/fault records;
- aggregating best/worst, fault, mismatch and gap reports from already-audited records;
- independently reviewing another worker's visual evidence when required;
- integrating/landing existing #442 WIP.

Do not create permanent worker roles. On every timed run, choose the highest-value uncovered non-conflicting #442 contribution from live evidence and continue useful work for the normal timed window.

## Completion

S1 remains focused on #442 until every eligible model-bearing asset in the deterministic newest-to-oldest population has an explicit terminal catalogue state: fully audited, explicitly blocked with the exact missing owner/evidence, or intentionally excluded because it is not actually a model-bearing asset.

Completion requires no silent image-only substitutions, no unresolved canonical naming ambiguity, no unaudited model presented as visually understood, no unrecorded visible faults, and no unsupported assumption that a source/library model equals the UE mesh.
