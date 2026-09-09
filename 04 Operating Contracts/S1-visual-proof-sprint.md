# S1 Visual Library Inventory Catalogue Fulfillment

Mission ID: `S1-VISUAL-LIBRARY-CATALOG-442`
Current convergence issue: `organicoverlords/tiny3d#442`

This is the current additive mission file for all five canonical S1 timed workers. It does not replace the long launcher or shared RULES/AGENTS contracts. It narrows S1 product work to one outcome until #442 is complete.

## Single outcome

Exhaustively turn the real model-bearing Tiny3D asset library into a visually inspected, correctly named, searchable, comparable catalogue that ChatGPT can reliably retrieve through the existing Tiny3D catalogue/search surfaces and Stack Atlas/Vault navigation.

Do not spend S1 runs on unrelated Raincoat, gameplay-proof, capture, presentation, or general P3 visual work unless that exact work directly unblocks #442 catalogue fulfillment for a currently audited asset. The catalogue campaign is the S1 priority.

## Eligibility and order

Process only assets that resolve to a real 3D payload. Eligible payloads include `.glb`, `.ply`, and Unreal mesh/content assets such as `.uasset`. Do not count image-only, thumbnail-only, concept-only, or preview-only records as inventory work.

Start from the newest generated/model-bearing asset and work backward by canonical generation/creation time. Do not cherry-pick easy or attractive assets ahead of newer unresolved eligible assets unless another worker already owns the exact conflicting audit slice.

The first seeded target on #442 is:
- asset id `e2c85820bce3d3f84398ff748c29178fcb1dca88af755b3e46feb3dc8120e916`
- exact GLB SHA-256 `b2eaedfa95b6bd36f94a03f4397cde040ed2476f1f2ad98b7021a99be45bdeac`

## Required per-asset audit

Every eligible asset must eventually have all of the following bound to the exact asset/model identity:

1. Canonical source/model identity and hashes.
2. Correct canonical name, normalized aliases, generator/source names, and replacement/supersession relationships.
3. Category, subcategory, role/use terms, normalized searchable tags, and a dense factual searchable description.
4. Technical facts needed for retrieval/comparison: format, geometry counts, dimensions/bounds, materials, textures, UVs, rigging/animation facts where applicable, and relevant Unreal identity.
5. Standardized twelve-view visual evidence from the actual model, not a single thumbnail. Use the existing Tiny3D preview owner and the canonical `twelve_standard_v1` view set when available.
6. Actual pixel inspection of those views. Record visible form, silhouette, materials, color, surface character, notable features, positive qualities, defects, suspicious/ugly details, occlusions/uncertainties, and role-fit observations. Automated geometry/material checks support this review but never replace pixel inspection.
7. A quality rating with concise rationale. Preserve both strengths and faults; do not sanitize bad assets.
8. Searchable fault labels and suitability notes so later ChatGPT retrieval can answer queries such as best/worst, broken materials, bad silhouette, naming conflict, duplicate variant, wrong role, or UE mismatch.
9. Reviewer lineage required by shared policy: evaluator worker identity, review revision/timestamp, durable worker-report reference, and exact asset/media identity. Later reviews append; they do not overwrite earlier reviews.
10. Final audit state that makes missing work queryable instead of implicit.

## Twelve-view and Unreal comparison rule

Treat Tiny3D/source models and Unreal meshes as different until equivalence is proven.

For every asset with a P3/Unreal materialization or plausible UE counterpart:
- resolve the exact Unreal object/package/mesh identity;
- compare source/Tiny3D model identity against the actual UE mesh/content, including geometry/bounds/material identity where evidence exists;
- inspect the model visually from the standardized twelve views;
- if the UE mesh differs materially, generate an equivalent twelve-view set from the actual UE mesh and compare the two sets directly;
- record a mismatch class and concrete differences rather than assuming same-name assets are the same thing.

A source GLB screenshot cannot prove UE equivalence. A UE screenshot cannot substitute for inspection of the source/library model.

## Naming must converge

Do not leave unresolved `candidate`, filename soup, generator garbage, conflicting aliases, or role guesses as the canonical public identity once evidence resolves the object. Establish one stable human-readable canonical name and retain useful historical/source names as aliases. Naming should describe what the asset actually is, not what an old prompt hoped it would be.

Flag and resolve:
- same asset under multiple names;
- different assets sharing one misleading name;
- source name versus generated result mismatch;
- Tiny3D name versus UE object name mismatch;
- variant/version relationships;
- superseded or rejected names that must remain searchable as aliases only.

## Aggregate catalogue obligations

The existing Tiny3D catalogue/search owner must expose enough structured evidence to query and rank the inventory without rescanning the filesystem. The campaign must ultimately support:
- newest-to-oldest audited queue;
- audited vs unaudited assets;
- best and worst rated assets;
- strongest and weakest per category;
- fault lists and recurring fault types;
- naming conflicts and aliases;
- source-vs-UE mismatches;
- rejected/superseded variants;
- missing twelve-view evidence;
- missing metadata/reviewer lineage;
- category, role, material, form, color, style, quality, technical, and fault searches.

Vault is history/navigation/evidence, not a second asset database. Stack Atlas should route ChatGPT to the canonical Tiny3D catalogue/search owner rather than duplicating the catalogue in Vault prose.

## Swarm entry and collision behavior

All five S1 workers converge on #442, but do not duplicate the same exact mutation or visual review.

On each run:
1. Read #442 current plan/recent material evidence once.
2. Reconcile exact active WIP for the newest unresolved eligible asset.
3. Take the highest-value uncovered slice for that asset: twelve-view generation, actual pixel review, metadata/naming, technical comparison, UE identity/comparison, catalogue projection/searchability, independent review, landing/integration, or the next newest asset when the current one is fully covered or exact-conflicted.
4. Leave durable results in the normal issue/PR/catalogue/report surfaces so another S1 worker can continue without rediscovery.
5. When an exact slice is blocked, take another non-conflicting #442 slice. Do not fall back to unrelated P3 visual work.

If this mission file is missing or unreadable at S1 startup, that is a worker-routing defect. Record the exact missing path in the worker report and do not silently substitute an unrelated visual mission as though the S1 catalogue direction had been satisfied.

## Completion

#442 is not complete after building catalogue infrastructure or rendering a few examples. Completion requires exhaustive traversal of the eligible model-bearing library newest-to-oldest, with each asset carrying the required visual/technical/naming/search metadata and comparison state, plus aggregate searchable best/worst/fault/category views. Missing evidence must remain explicit and queryable until closed.
