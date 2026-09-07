## 2026-09-07 contribution and delivery plan
Authority remains docs/v2/P3_V2_NORTH_STAR.md; detailed refinement: docs/v2/P3_PLAYABLE_MATCH_DIRECTION.md.
Roadmap relation: #803 is **Milestone A** of the North Star finished-game roadmap. Finish this integrated friend-playable match before pulling later content-expansion/polish milestones into this issue; once #803/#941 are accepted, workers derive the next unmet milestone/issues from the North Star without requiring user issue gardening.

| Required result | Existing issue / mutation owner | Handoff / acceptance |
| --- | --- | --- |
| Join, play, finish, replay | #2442; existing session menu/launcher/match owner | Ordinary solo and LAN routes, two perspectives, clear failure/retry and clean rematch |
| Creep/terrain/defense counterplay | #2437/#2440 with #1012/#1033 | Real navigation changes after edit/build/destroy; no permanent route soft lock |
| Movement and readable combat | #2439/#2461, #2441/#1091 | Ski/grapple route affects a live fight; readable tells/impact in both views |
| Meaningful spending | #2438 | Earn -> choice -> visible lane consequence under authoritative economy |
| Full generated character motion | #2610, #331/#394, Tiny3D #372 | Current roster state/transition proof and exact returned asset attribution |
| Combined playability | #2611 | Fixed real-match workload, measured cost/budget and no visual/gameplay regression |
| Final user acceptance | #941 | One compatible build/content/configuration completes the normal-user match sequence |

Respect existing source WIP: #2605 placement, #2600 route rollback, #2603 wave phase and #2606 ski HUD are current review/integration candidates, not prompts for duplicate patches. File owners integrate overlapping contributions. P3LaneWarHUDWidget.cpp and P3TowerDefenseFeatureActor.cpp are shared serialization boundaries; different UI labels/checklists are not parallel source scopes.

### Priority and closure
Finish ready gameplay and the integrated user path before optional technology experiments or infra refinement. #599/#611 remain maintenance owners, not parent permission gates for #803. Use normal build/proof owners only to resolve a demonstrated blocker. The dated architecture program's lane/capacity observations are history, not current worker or machine state.

Use a single exact scenario/head/content set for normal launch -> join/solo -> fight/move -> reshape/build/destroy -> earn/spend -> win/loss -> replay. Existing source/contract passes are valuable but cannot close missing runtime or visual steps. Record the first unmet step and reuse still-valid proof.

No new product ledger, orchestrator or acceptance framework is needed: this issue and #941 remain the composition record. Design completion is not match completion.

---

Authority: `docs/v2/P3_V2_NORTH_STAR.md` (product thesis + immediate friend-playable priority; update in PR #802).
Parent/default-path acceptance: #611.
Existing component owners: #413 base/core assets, #414 battlefield, #205 character roster/animation, #206 earthworks+building+destruction, #331 qualified asset intake.

## Goal

Ship the first **friend-playable V2 Lane War** as one integrated multiplayer product slice, not a set of disconnected subsystem demos.

## Required match

- Two opposing teams/bases on the V2 production path.
- Each team visibly has **walls/defences + a base/house asset + a Core asset**.
- The Core is the heart/objective creeps and enemy players try to destroy and is server-authoritative/player-placeable or movable so the player can choose its defended position.
- A clear 3D road/lane connects the bases; ordinary creeps follow it toward the opposing Core.
- Players can construct additional defences around the Core and along the lane.
- Valid construction/earthworks/destruction change real traversal and creep navigation.

## Movement, combat and terrain

- Grappling hook, Tribes-style momentum skiing/surfing, earthworks, rapid building, destruction and spells/abilities all work in the same two-player match.
- Earthworks raises/lowers lane ground to create ramps/ski lines, berms, trenches/pits, high ground, blockers and creep reroutes.
- Destruction/counter-building can reopen or reshape routes.
- Creeps react to blockers/terrain rather than walking through meaningful changes.

## Economy

- Creep-related play and elapsed time award spendable gold.
- Gold can buy at minimum **additional allied creep/minion spawns** and upgrades that visibly affect the live Lane War.
- Gold, purchases, spawns and upgrades are server-authoritative and replicated.

## Characters and spells

- The chosen first playable roster is fully animated through real gameplay states: locomotion, skiing/traversal, grapple/air states where applicable, attacks/spells, defeat and respawn.
- Spells/abilities have readable cast/start, active/travel, impact/result and resource/cooldown feedback where applicable.
- No static/partially animated placeholder character counts for the milestone.

## Acceptance

1. Host can start a normal two-player session and a friend can join through a user-facing flow; developer-only PIE is not final acceptance.
2. Both players see complete opposing bases and the road/lane.
3. Creeps spawn, navigate, fight and damage the enemy Core.
4. Players fight with visible spells while using grapple/ski/high-mobility traversal.
5. Terrain or construction changes a creep/player route; destruction or counter-building changes it again.
6. Gold rises from creep-related play/time and can be spent on extra creep/minion spawns or an upgrade that changes the match.
7. Destroying a Core produces replicated match resolution.
8. Canonical reviewed visual proof shows both bases, creeps, full character animation, spells, terrain/build/destruction interaction, economy feedback and match resolution on one compatible head.
9. The user receives a practical launch/test path for playing with a friend plus representative proof media.

## Scope rule

Compose and finish existing V2 owners. Do not create duplicate movement, construction, earthworks, combat, Lane War or asset systems for this issue. This issue owns the integrated playable result and friend-test acceptance.