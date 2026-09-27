# Product-mode investigation: state snapshot

**Status: SNAPSHOT, documentation only. Written 2026-09-24.** Purpose: a fresh session can resume the investigation and the decisions without re-deriving any evidence. It records facts, evidence and open decisions. **It deliberately contains no recommendation and no next-step proposal.**

**Update, 2026-09-27 (last): at most one robot broken down at a time (Product-mode guard), and a measurement of how stuck robots recover (section 13).**

**Update, 2026-09-27: the Phase 4 PRODUCT tab is built and verified end to end in a real browser (section 12).**

**Update, 2026-09-27 (later): a manual "Mark as fixed" for broken-down robots (Java overlay + Python recover action, section 11); Product-mode backend logic work is closed, Phase 4 frontend is next.**

**Update, 2026-09-27: an occupied-drop-cell rule was applied to the Java task generator (section 10.7): real-stack abandonment 41.1% to 22.1%, no dead stretches; accepted as the final backend state.**

**Update, 2026-09-26: the Product-mode task-backlog freeze was FIXED in Java and `simulation/product/` (section 10); the agent-level stall investigation is closed and nothing agent-level was applied.**

**Update, 2026-09-25: V6b is APPLIED.** The agent-side movement guard reviewed in `docs/MOVEMENT_GUARD_V6B_PROPOSAL.md` was applied to `robot_agent/agent.py` (68 lines added, 0 removed) with 13 new tests. See "V6b applied" in section 3 (Defect 2). Decision (b) is decided; decisions (a) and (e) remain open and (a) is independent; (c) is moot. A separate read-only liveness investigation was opened (section 9). Where a statement below says nothing was applied to `robot_agent/agent.py` beyond the `start_tick` edit, it describes the state before this update.

**Update, 2026-09-25:** read-only investigation of decision (b) added a Defect 2 addendum (section 3): `d_deadlock`'s audited result is a byproduct of the adjacency gap, and two lower-cost physical-guard candidates, V6 and V6b, were found and measured in scratch processes. Nothing was applied to the repository; decision (b) is still open (section 5).

**Update, later on 2026-09-24:** Defect 3 (the COMM_DELAY blackout) has since been **FIXED in Product mode** by an approved guard that lives entirely in `simulation/product/`. See section 0, section 3 (Defect 3) and section 4. Every other section is otherwise as originally written; where a sentence would now be wrong it has been amended and marked.

## 0. For a reader skimming

> **The audited 270-run benchmark result (0 collisions, 21.74% on `i_parallel_aisles`) is unaffected by all three findings below and remains valid and unchanged.** Two things have been applied to the working tree, both uncommitted, and neither touches the benchmark path: (1) an earlier, separately approved one-argument edit (`start_tick`, Defect 1) in `robot_agent/agent.py`, stated in full in section 3 (a fresh full benchmark with it in place reproduced every headline number and 0/270 collisions; the only metric that moved was `g_high_load` DECENTRALIZED_PROPOSED, 28 to 37 ticks); and (2) the Defect 3 fix, a Product-mode-only guard in `simulation/product/world_faults.py` and `simulation/product/session.py` that refuses to *start* a COMM_DELAY episode while two robots are within 2 cells of each other. With it, the deterministic soak (vanilla detector, faults on) went from **63 to 33 colliding runs out of 120** and the message-blackout collision class from 34 first-collisions to **0**. Nothing in `collision_engine/`, `robot_agent/` (beyond the `start_tick` edit), `InProcessBus`, any scenario, any test or the benchmark harness was changed for it.

---

## 1. What Product mode is, and why it was built

**Framing source.** The task asked for this document to reference `SESSION_ROLLOVER.md`'s framing. **No file with that name exists anywhere in the repository** (searched the whole tree). The framing below is taken from the original task brief and from `CLAUDE.md`. Nothing here depends on that file.

**Goal.** A new **PRODUCT** tab in the dashboard: a live, seeded, continuously running warehouse-operations session in which the *real* pipeline produces everything shown: seed, task creation (Java), assignment (Java `TaskAllocationService`), live push to Python, robot state, local A\* planning, peer-intent messaging, conflict detection, priority resolution, movement, rerouting, deadlock handling, injected world faults, task reassignment (Java), telemetry and events, Java, WebSocket, dashboard. The existing Presentation/Explanation tab, Benchmark & Proof view, all nine scenarios and all benchmark results stay as they are.

**Non-negotiable design principles (from the brief).**
1. Conflicts, yielding, congestion, deadlocks and rerouting must *emerge* from real traffic. Only three exogenous world faults may be injected: AISLE_BLOCK (timed clear), ROBOT_OFFLINE, COMM_DELAY of exactly 1 tick (described in the brief as "the only message fault covered by benchmark `d_deadlock`").
2. Layer ownership: business events originate in Java; world faults in the Python simulated world; movement decisions by robots; assignment/reassignment by Java. The frontend never generates data and never talks to Python.
3. Product mode runs DECENTRALIZED_PROPOSED only, on the real `simulation/warehouse/demo_map.py`, 4-6 robots.
4. **Product sessions are exploratory. The 0/270 collision result and the 21.74% figure apply only to the offline benchmark, and the UI must say so.**
5. No fake data; rule-based only.

**Hard rules that apply.** No git write operations. Do not modify `collision_engine/` decision logic, `simulation/referee.py`, `planner/`, any file in `simulation/scenarios/`, the benchmark harness, or the scenario registry. Tier A files (`collision_engine/*`, `simulation/referee.py`, `robot_agent/agent.py`, `shared/python/models.py`, `docs/00_SHARED_CONTRACTS.md`, and contract mirrors) need explicit written approval before any edit.

### 1.1 Phase status

| Phase | Content | State |
|---|---|---|
| 0 | Inspect and report, capture baseline | Done. Baseline `raw_results.csv` SHA-256 `a30616690fc1424b3cf74a84b3b4e0ac3a451c196acb4639aa52e262917056d0` |
| 1 | Python product driver + observability | Done. Gate: pytest 286 passed / 27 subtests; fresh 270-run benchmark **byte-identical** to baseline (same SHA-256); grep confirmed no benchmark/scenario path imports `simulation.product` |
| 2 | Java task lifecycle and live assignment | Done. JUnit 38/38 (no new Java tests written); live end-to-end over real HTTP (task lifecycle, OFFLINE-to-reassignment loop closed live, manual injection round trip) |
| 3 | World faults + soak test | Fault generator built in Phase 1. Stale-robot revert cap added and stress-tested live (5 reverts, then FAILED). **Soak test found collisions and was stopped**; this document is the result of that investigation |
| 4 | Frontend PRODUCT tab | **Not started** |
| Final | `docs/PRODUCT_MODE.md` | **Not written.** Three Python docstrings (`simulation/product/session.py`, `world_faults.py`, `__init__.py`) refer to it |

### 1.2 What was built

- **Python, `simulation/product/` (new):** `session.py` (`ProductSession`: a tick loop on a background thread, robots `PR1..PRn` starting IDLE at distinct pickup points, assignments only via an inbox, NEGOTIATION events enriched from the real `Conflict`, per-tick COMM_FLOW records via a delegating transport wrapper, TASK_COMPLETED detection, a 30-tick stall watchdog, a **3-tick reassignment cooldown** with deferred assignments), `task_inbox.py`, `envelope.py` (event tagging; every eventId prefixed with the session id), `world_faults.py` (seeded `WorldFaultGenerator`; guards: 15-tick cooldown, max 2 concurrent faults, never block an occupied cell, real-planner feasibility check).
- **Python, `simulation/runner.py` (edited):** a module-level `_product_session`, the single-run lock extended to cover product sessions, and four routes: `POST /control/product/start`, `/control/product/stop`, `/control/task`, `/control/inject`.
- **Java (new):** `ProductSessionService` (own poll thread; seeded tick-driven task generation from the cached `WarehouseMap`; backlog cap 3; reuses the unmodified `TaskAllocationService.allocatePendingTasks()`; exact-cell-plus-IDLE completion detection; stale-robot safety net capped at 5 reverts, then the task is marked FAILED), `ProductController` (`/api/product/session/start|stop`, `GET /api/product/session`, `POST /api/product/inject`), `ProductSessionStatusDto`.
- **Java (edited):** `SimulationClient`, four additive methods (`startProduct`, `stopProduct`, `assignTask`, `injectProductFault`).
- **Deliberate namespacing:** product robots are `PR1..PRn` (scenarios use `R1..Rn`) and product event ids carry the session id, because the Java `RobotCacheService` and `events` table are global and never cleared.
- **Not done from the brief's verification list:** at least 10 end-to-end sessions of 300+ ticks plus LIVE sessions, the seed-reproducibility write-up, and the trust audit table.

---

## 2. Evidence conventions (read before the defect sections)

- **Deterministic harness.** Every number below comes from a harness that feeds tasks and manual faults from *inside* the tick thread, so runs differ only by code: 5 robots, real `demo_map.py`, seeds 1-120, 420 ticks (150 for fault-free scans), reassignment cooldown 3, the `start_tick` edit present in the working tree, backend pushes disabled.
- **Superseded numbers.** The earlier soak figures (2,363 collisions, then 2,448 and 2,851) came from harnesses that read `agent.state` from an external thread, which is a race and makes runs non-reproducible. They are **not comparable** with the tables here. The first figure (2,363) was additionally inflated by a genuine race in that scratch harness (reassigning robots that were not actually idle).
- **Vocabulary.** "Vanilla" = the current, unmodified `collision_engine/`. "V4" = the adjacency candidate restricted to MOVING peers; "V4h" = its head-on-only subset; "V3" = the same without the MOVING restriction; "V5" = V4 plus an experimental tick-free "same next cell" check. All variants were grafted onto the unmodified class in scratch processes; **none was ever applied to the repository**.
- **Metric.** Runs with at least one referee collision, out of 120. Total collision counts are unreliable: one stuck pair produces one event per tick (four runs stayed co-located for 304-396 ticks).

---

## 3. The three defects, in order of discovery

### Defect 1: replan tick misalignment (`start_tick`), CLAUDE.md Known Bugs #4

- **Root cause.** `RobotAgent.tick()` in `robot_agent/agent.py` called `self.planner.plan(...)` without `start_tick`, so the planner defaulted to 0 and every replanned path was stamped 1, 2, 3, ... unrelated to the real simulation clock. `ConflictDetector`'s space-time checks then compare incomparable tick values for any robot that has replanned.
- **Exercised by the 9 scenarios?** *The condition* runs in every scenario that replans mid-run (measured with the edit in place, seed 1, DECENTRALIZED_PROPOSED: `c_narrow_aisle` 1, `d_deadlock` 2, `e_blocked_aisle` 1, `f_task_reassignment` 1, `g_high_load` 9; the other four 0), and it has a measurable effect: fixing it changes `g_high_load`. **No scenario produced a collision from it (0/270 before and after).** This is a deliberate departure from the phrasing "none of the three were exercised": for Defect 1 what no scenario exercised is a *collision consequence*, not the code path.
- **Status.** Fix **written and validated, present as an uncommitted edit in the working tree of `robot_agent/agent.py`, not merged/committed** (`git show HEAD:robot_agent/agent.py` does not contain it). It is *active* in the working tree, so every run cited in this document executed with it. It is being decided together with Defect 2.
- **The edit.** One added argument in the `plan(...)` call, `start_tick=current_tick - 1`, plus a rewritten comment block above it (hunk shown in section 7).
- **Validation.** Full pytest 286 passed / 27 subtests (unchanged). Fresh 270-run benchmark diffed against the baseline: `i_parallel_aisles` 23/19/18 and `b_intersection` 9/10/11 unchanged; 0/270 collisions in both runs; exactly one (scenario, mode) pair changed: **`g_high_load` DECENTRALIZED_PROPOSED 28 to 37 ticks** (0 collisions either way; the cost predicted in the old code comment). Output was written outside the repo (see section 7).
- **Evidence that it did not, by itself, explain the Product-mode collisions.** Soak with the edit plus the cooldown: 2,448 collisions before versus 2,851 after (non-deterministic harness, so indicative only). In the deterministic harness the seed-57 swap still occurs with the edit in place and the cooldown at 0 (2 collisions) and at 3 (1 collision). In that trace `PR2`'s replanned path *is* correctly stamped (`(6,14,21),(7,14,22),...` at tick 21). It was the first hypothesis for the soak collisions and it turned out not to be the cause of the seed-57 collision.
- **Correction needed to a code comment (not edited).** The comment block beside the edit in `robot_agent/agent.py` says the misalignment "empirically produced real, referee-verified collisions under Product mode". **That claim was not established**: no collision was ever isolated to this defect. The comment overstates the evidence. Recorded here; the file was not touched.

### Defect 2: exact-adjacency, face-to-face blind spot, CLAUDE.md Known Bugs #11

- **Root cause.** The detector compares each robot's own planned path with a peer's broadcast `plannedPath`. Both hold only *future* waypoints; the cell a robot stands on is never in either list (the agent pops each waypoint on entering it, `agent.py`). For two adjacent, both-moving, face-to-face robots (each one's next cell is the other's current cell) the leg between their cells is in neither list, so `_check_same_cell`, `_check_crossing` and `_check_headon` all have nothing to match. `_check_crossing` accepts `own_pos`/`peer_pos_raw` but never uses them. A second contributing weakness: a WAITING robot's remaining path keeps its old tick stamps (never re-stamped), defeating the tick-keyed checks.
- **Detection by gap** (unmodified detector; robots on one row facing each other; gap 1 = adjacent): **gap 1 always undetected; gap 2 undetected when either path is stale-stamped (detected as SAME_CELL only if stamps line up); gap 3 or more detected.**
- **One root cause, two collision shapes.** The same missing information produces an **edge swap** when both robots move in one tick, or a **same-cell** collision when the earlier-ticking robot has already stepped into a cell and the later one then steps in. The tick loop is sequential, so the second robot decides on the first one's post-move position.
- **Exercised by the 9 scenarios?** **No.** An instrumented per-tick scan of all 9 (DECENTRALIZED_PROPOSED, seed 1, benchmark map) found the adjacent-facing state only in `d_deadlock` (6 snapshots) and `g_high_load` (5). In every one of them the robots were WAITING (stationary), except one `d_deadlock` snapshot with one MOVING and one WAITING robot, so the stationary-peer guard held them apart. Both-moving never occurred. The other 7 scenarios never reached the state.
- **Status.** Documented in CLAUDE.md Known Bugs #11 and in `docs/COLLISION_DETECTION_ADJACENCY_GAP.md` (full diff and 10 drafted regression tests). **The detector candidate (V4/V4h) was NOT applied. Updated 2026-09-25: the agent-side movement guard V6b WAS applied (see "V6b applied" below); the detector blind spot itself remains unfixed.**
- **Evidence traces (deterministic, `PR` robots, `start_tick` edit present).**
  - **Seed 57, fault-free, tick 21 to 22 (edge swap).** `PR2` finishes at (5,14) at tick 18 and is reassigned; `PR3` waits at (8,14) with a path stamped `(7,14,18),(6,14,19),(5,14,20)`. At tick 21 `PR2` replans (fresh stamps, priority 5) and `PR3` (priority 1) receives that path in the same tick but `detect()` returns `None` (no common tick; `PR2`'s leg `(6,14)->(7,14)` absent). `PR3` resumes; at tick 22 `PR2` moves (6,14)->(7,14) and `PR3` moves (7,14)->(6,14). Referee: swap.
  - **Seed 14, fault-free, tick 3 (same-cell).** `PR1` (7,0)->(11,14) and `PR4` (11,0)->(1,4) meet head-on on row 0. Tick 1: `PR4` detects SAME_CELL at (9,0) and waits (correct). Tick 2 (gap 2, `PR4`'s path stale): all four checks False against `PR1`. Tick 3: `PR1` steps to (10,0), adjacent to `PR4`; `PR4` replans and sees `PR1` post-move: all checks False (gap 1), the guard does not hold (10,0) because `PR1` is MOVING with a path, and `PR4` steps into (10,0). Referee: both in (10,0).
- **Effect of the candidate (colliding runs out of 120).**

| Configuration | Vanilla | V3 | V4 | V4h | V5 |
|---|---|---|---|---|---|
| Fault-free, 150 ticks | 47 | not run | 8 | not run | 9 |
| Soak (faults on), 420 ticks | 63 | 44 | 45 | 45 | not run |
| Soak with COMM_DELAY disabled | 31 | not run | 6 | not run | not run |

  First-collision geometry: vanilla soak 12 edge swaps + 51 same-cell; V3 0 + 44; V4 0 + 45 (V4h not classified).
- **Real cost, precisely.**
  - **Throughput.** Mean tasks completed per 420-tick run: **13.1 to 11.1 (about 15%)** with all faults on (vanilla to V4). With COMM_DELAY disabled: total 1,382 to 1,086 tasks over 120 runs, **11.5 to 9.05 per run (about 21%)**. These figures include the effect of collisions leaving robots stuck.
  - **`d_deadlock`.** 12 to 8 ticks, deadlock activations 2 to 0, reroutes 2 to 1, idle ticks 16 to 8, collisions 0, on all 10 seeds. Mechanism: the scenario's constant 1-tick delay makes `R1`'s MOVING label one tick old; at tick 3 `R2` (waiting at (11,9)) sees `R1` face to face at (10,9); vanilla returns nothing, so both wait until `DeadlockDetector` fires, while an adjacency-aware detector reports a head-on and `R2` yields. **Four implementations (V3, V4, V4h, V5 — V5 builds on V4) all give this identical result**, so it is inherent to closing the gap in that state rather than an artifact of one approach.
  - **`g_high_load`.** Under V4/V5 it is byte-identical to vanilla, including its 9 deadlock-detector activations (its deadlock firing is unaffected). Under V3 (no MOVING restriction) it changes: 37 to 33 ticks, activations 9 to 6.
  - **Existing tests.** Vanilla-plus-V4/V4h: 284 of 286 pass. The two failures are `simulation/tests/test_runner.py::TestDeadlockCountReflectsRealDetector::test_deadlock_count_is_not_the_old_yield_proxy` and `::test_deadlock_count_matches_detector_activations_when_it_fires`, which use `d_deadlock` as the scenario that must make the detector fire. V3 additionally fails `collision_engine/tests/test_detection.py::TestStationaryPeerOccupancy::test_waiting_peer_standing_on_our_next_cell_is_detected`.
  - **Benchmark scenarios.** 80 of 90 (scenario, seed) runs byte-identical under V4; only `d_deadlock` changes; `i_parallel_aisles` 18 and `b_intersection` 11 unchanged; collisions 0.
- **Not established.** The V5 experiment (tick-free "same next cell" check) fixed seed 9 but gave no net gain (9 vs 8 colliding fault-free runs); seed 12 tick 6 shows why (the shared cell is the second waypoint on one path and the other path is stale). Whether a proper tick re-alignment would work has not been tried.

#### Defect 2 addendum (2026-09-25): what `d_deadlock` actually proves, and two lower-cost physical-guard candidates

All of this is **read-only scratch work; nothing below was applied to the repository.** Scratch scripts live outside the repo (`v6.py`, `dd_matrix*.py`, `dd_probe.py`, `corridor.py`, `class_indep.py`, `trace_v6.py`, `soak_v.py`, and their logs, in the adjacency scratch directory).

**(1) `d_deadlock`'s audited result is a byproduct of this defect.** Trace (benchmark map, seed 1): at tick 2 `R2` (lower priority) correctly waits on a same-cell conflict at (10,9) and `R1` steps into it; the robots are now adjacent and face to face, `detect()` returns `None` for both from tick 3, and the mutual wait is held only by the physical stationary-peer guard plus resume-on-clear until the 5-tick stall detector fires at tick 7. Both activations classify as exact face-to-face pairs. The map around row 9 is an open field (rows 9 and 10 free, free space beyond), so a sidestep is always available; an adjacency-aware detector makes `R2` yield at tick 3 by the existing priority rule (8 ticks, 0 activations). Across 12 variants (separation 2-8, message delay 0 or 1) the unmodified detector **collides in 7, resolves cleanly in 3, and reaches the safe mutual wait in 2** (separation 4 and 8, delay 1); at delay 0 and separation 4 it collides. The deadlock detector itself is confirmed on genuine deadlocks by evidence independent of `d_deadlock`: a scratch single-file corridor with no bypass gives 23 activations in 120 ticks, never completes, 0 collisions, identical under vanilla/V4/V6; the same corridor with a bypass and delay 0 recovers (1 activation, 34 ticks, 0 collisions, identical under all three); `g_high_load` keeps its 9 activations (with the uncommitted `start_tick` edit) under V4, V6 and V6b, of which 2 are face-to-face, 1 a non-facing blocker and 6 stalls whose blocking peer is not on the next cell (not traced further). **Limit:** the corridor-with-bypass case with delay 1 did not recover (23 activations, never completes), identically under all variants; one seed and geometry, not investigated. This is recorded in CLAUDE.md Known Bugs #11 as a scoping correction, not a retraction.

**(2) Two physical-guard candidates that leave detection untouched (both scratch prototypes, both in `robot_agent/agent.py` territory, i.e. Tier A):**
- **V6**: in `_advance_one_cell_if_clear` and `_waiting_condition_cleared`, refuse to move when a peer's reported position is my next cell AND that peer's reported next waypoint is my current cell (an exact face-to-face pair). The pair then waits and the existing stall detector recovers it.
- **V6b** = V6 plus a **loser-side shared-next-cell guard**: refuse to move when a higher-priority peer's reported next waypoint equals my next cell (priority order mirrors `_should_step_aside()`: higher task priority wins, ties go to the lexicographically lower robot id).

| Metric (deterministic harness, Defect 3 guard in place, 120 seeds) | Vanilla | V4 | V6 | V6b |
|---|---|---|---|---|
| Changes | (none) | `collision_engine/detection.py` | `agent.py` physical guard | `agent.py` physical guard |
| Colliding runs, fault-free, 150 ticks | 47 | 8 | 10 | 8 |
| Colliding runs, faults on, 420 ticks | 33 | 6 | 11 | 4 |
| Tasks completed, faults on (vs vanilla 1,427) | 1,427 | 1,138 (-20.3%) | 1,311 (-8.1%) | 1,250 (-12.4%) |
| First-collision residual, faults on | 12 swaps + 11 face-to-face + 8 converge + 5 stopped-MOVING | 2 converge + 4 stopped-MOVING | 9 converge + 2 stopped-MOVING | 3 converge + 1 stopped-MOVING |
| 9 scenarios x 10 seeds, DECENTRALIZED_PROPOSED (90 runs) | baseline | only `d_deadlock` differs (12 to 8 ticks, 2 to 0 activations) | 0 of 90 differ | 0 of 90 differ |
| `d_deadlock` | 12 ticks / 2 activations | 8 / 0 | 12 / 2 | 12 / 2 |
| Full pytest | 286 passed | 284 (2 `d_deadlock` tests fail) | 286 passed | 286 passed |
| `d_deadlock`-geometry matrix (12 variants), collisions | 7 | 2 | 3 | 1 |

The remaining V6b collision in that matrix is separation 2 with delay 1 (see (3)). V6b was slower than vanilla in matrix cells where vanilla already resolved cleanly (separation 5 / 6 with delay 0: 9 / 11 ticks versus 13 / 14) because the loser now holds while the winner passes. The V6/V6b numbers are single-run prototypes, not reviewed code.

**(3) Why V6 still collided at separations 2, 5, 6 with 1-tick delay (tick-by-tick traces).** Not the Defect 3 blackout; a related member of the message-delay family (staleness, not absence) plus two known weaknesses:
- **Separation 2 (tick 1):** `R1` (8,9) and `R2` (10,9) both step into (9,9). Under a constant 1-tick delay nobody has received anything on tick 1 (`heard peer pos={}` for both). No agent-side guard can act on information that does not exist; it is a start-up blind window, closed by any guard only if the robots are not placed two cells apart at tick 0. Product mode is unlikely to produce it (sessions start with delay 0 at distinct pickup points, and the Defect 3 guard refuses activations when robots are within 2 cells), but that was not proven impossible.
- **Separation 5 (tick 3) and 6 (tick 4):** the higher-priority robot ticks first and steps into the shared cell; the waiting robot, ticking second, hears the winner's message from the previous tick (position one cell behind reality, next waypoint = the cell it has already entered). Three things line up: (i) the waiter's own path keeps stale tick stamps (`(11,9,2)`) against the winner's fresh ones (`(11,9,3)`), so `SAME_CELL` is blind and `detect()` returns `None` (cause (a)); (ii) the current-cell omission (Defect 2) hides the reversed pair; (iii) V6's guard compares against the peer's reported CURRENT position, which is exactly the stale field, so it does not fire. With delay 0 the same geometry is safe because the waiter hears the winner's post-move position and `_waiting_condition_cleared()`'s raw-position check holds it.
- **What extends cheaply:** checking the peer's current position more (the hypothesis) cannot help, because that field is the stale one. The reported NEXT waypoint is not stale in the same way (under 1-tick delay it equals the peer's actual current cell), so a loser-side check on it closes both cases. That is V6b.
- **Tick order caveat (reasoned, not isolated by a dedicated test).** If the loser ticks first, the same rule should still hold it back, because it depends on the winner's reported next waypoint, not on tick order. In `d_deadlock` the winner ticks first; the soak mixes orders and gave 4 colliding runs of 120.

**(4) Reconciling the two smaller classes with Defect 2's fix (causal test).** Class shares by "first collision" are confounded: a detector change alters the trajectory, so a run's first collision can be replaced by a later one. Direct test: for each vanilla (guarded-repo, faults on) collision, re-run the same seed under V4 and find the first tick at which any robot's position differs.

| Class | Vanilla cases | V4 leaves run byte-identical and the same collision recurs | V4 changes behaviour at or before the collision tick |
|---|---|---|---|
| Stale-stamp converging paths | 8 | 2 (seeds 9, 55) | 6 (in 5, exactly at the collision tick) |
| Stopped-MOVING peer | 5 | 1 (seed 98) | 4 |
| Face-to-face (control) | 11 | 0 | 11 |

So the classes are **partly overlapping** with Defect 2's fix: the classifier's "converging paths" label includes adjacency-catchable start-up cases (mostly tick 4), plus a genuinely independent residual (seeds 9, 55, 98). V5 moved the fault-free "converging" count only from 7 to 6.

#### V6b applied (2026-09-25, approved)

- **Applied:** the diff in `docs/MOVEMENT_GUARD_V6B_PROPOSAL.md` section 3, to `robot_agent/agent.py` only (CRLF preserved; verified byte-for-byte against the tested copy; 68 added lines, 0 removed). Rule 1: exact face-to-face pair, both hold. Rule 2: a higher-priority peer's next waypoint is my next cell, only the loser holds.
- **Tests:** 13 new (12 in `robot_agent/tests/test_agent.py`, 1 in `simulation/tests/test_runner.py::TestDeadlockScenarioInvariance`). On the unpatched agent 8 test functions fail (5 unit, the geometry-matrix test with 6 subtests, both seed replays) and 5 pass by design; all pass after the patch. **Full suite 299 passed / 33 subtests (was 286 / 27).**
- **Benchmark (fresh 270-run runs, outside the repo): byte-identical.** V6b with the `start_tick` edit present: `raw_results.csv` SHA-256 `32d492d87ccbf3bb3c1673645fe2e25a32e0c836fcb94abd801cd184274cdb5e`, equal to the post-`start_tick` pre-V6b run. V6b with the `start_tick` edit emulated absent: `a30616690fc1424b3cf74a84b3b4e0ac3a451c196acb4639aa52e262917056d0`, equal to the audited baseline. 0/270 collisions in both; `i_parallel_aisles` 23/19/18, `b_intersection` 9/10/11, `d_deadlock` 12 ticks / 2 activations.
- **Soak (deterministic harness, vanilla detector, Defect 3 guard in place, cooldown 3, 120 seeds):**

| | Before V6b | V6b applied |
|---|---|---|
| Colliding runs, faults on, 420 ticks | 33 | **4** (3 converging paths, 1 stopped-MOVING peer) |
| Colliding runs, fault-free, 150 ticks | 47 | **8** (7 converging paths, 1 stopped-MOVING peer) |
| Tasks completed, faults on | 1,427 | 1,250 (-12.4%; -6.7% vs a `start_tick`-free baseline) |
| Tasks completed, fault-free | 1,625 | 1,521 (-6.4%) |

- **Winner-hold cost (rule 1 holds both robots, including the winner).** On the real `d_deadlock` pair: `R1` (winner) is `WAITING` t3-t8 (6 ticks), the stall detector fires t7 (`R2`, reroutes) and t8 (`R1`, holds its ground), `R2` sidesteps t8, `R1` advances t9: 12 ticks, identical to the unmodified agent. Immediate continuation is not physically available (the loser occupies the winner's next cell). A detector-level fix (V4) resolves the same pair in 8 ticks (winner waits 2), so rule 1 costs about 4 extra ticks per pair. Hold-episode lengths over the soak: fault-free 90 / 178 / 72 / 19 (1-2 / 3-5 / 6-30 / >30 ticks); with faults 438 / 116 / 82 / 54.
- **NEGOTIATION `peerRobotId`: cosmetic; the guard's behaviour is not.** The label is read after the tick and feeds no metric. Across all 9 benchmark scenarios the whole event stream and all six metrics are identical with and without V6b. Pre-existing `peerRobotId: None` on CONTINUE (324 of 890 fault-free events, vanilla); labels naming a robot other than the resolver's peer: vanilla 0/890 fault-free and 11/833 with faults, V6b 9/887 and 16/850. Known, low-severity, deferred. In the cells where the guard changes behaviour, `idleTicksTotal`, `deadlockCount` and `rerouteCount` do change (that is behaviour, not labelling).
- **Known limitation found after applying (not fixed):** the guard does not check the peer's status. With faults on, 68% of guard hold-ticks (12,036 of 17,614) are for dead (injected-OFFLINE) robots: rule 1 (9,163) is redundant with the stationary-peer guard; rule 2 (2,873 ticks, about 1.1% of all robot-ticks) is a false hold. A dead robot's agent status is not sticky (a REASSIGN_TASK verdict sets BLOCKED), so peers see BLOCKED (9,082 ticks), OFFLINE (2,868) or WAITING (86). No effect on the fault-free benchmark or fault-free soak.
- **Decision independence.** (a) `start_tick` is independent (2 x 2 verified) and still open; (c) the two `d_deadlock`-based tests still pass, so it is moot; (e) untouched.

### Defect 3: message blackout at COMM_DELAY transitions

- **Root cause.** Product mode's COMM_DELAY fault is implemented as an *episode*: `WorldFaultGenerator.try_apply_comm_delay` sets the bus's `delay_ticks` from 0 to 1 mid-run and `clear_expired_comm_delay` sets it back to 0 five ticks later. On the **start tick**, the broadcasts of *earlier-ticking* robots for that tick are held, so each later-ticking robot receives **no message at all** from them. `RobotAgent` rebuilds its peer-held-cell map and detector inputs from *that tick's received messages only*, so a stationary peer it had tracked for many ticks disappears for one tick and the robot walks into it.
- **Plain statement.** **This is a Product-mode fault-generator design flaw, not a defect in the core coordination system.** `d_deadlock` runs a *constant* 1-tick delay from tick 0 and therefore never has a transition tick.
- **A caveat a reader should know (fact, not a change of conclusion).** The *susceptibility* is real and lives in `robot_agent/agent.py`: the agent has no last-known memory of a peer across ticks, so any mid-run message loss would trigger the same collision. Message drop (`drop_rate`) is wired but not used by any scenario, so no benchmark exercises it. In this codebase the only thing that produces the transition is Product mode's own toggling.
- **Exercised by the 9 scenarios?** **No.** No scenario changes the bus delay mid-run.
- **Status.** **FIXED in Product mode (2026-09-24, approved, uncommitted).** *Originally written as "Identified, not fixed, not designed"; the fix is described in the next bullet.*
- **The fix (Product-mode-only; lives entirely in `simulation/product/`).**
  - **Mechanism found by reading `InProcessBus`.** `_enqueue()` reads `delay_ticks` fresh, per message, at broadcast time, and `advance_tick()` promotes whatever is already buffered regardless of the current setting. So the **deactivation** edge (1 to 0) is safe: leftover buffered messages are still promoted and new ones flow immediately. The **activation** edge (0 to 1) is the only dangerous one, and it cannot be timed away: going from 0-tick to 1-tick latency in a single-threaded, fixed-order tick loop always costs one same-tick delivery for any later-ticking robot that depended on an earlier-ticking peer. A steady mid-episode tick is a continuous, uniformly 1-tick-stale flow, not a blackout.
  - **What was changed.** `WorldFaultGenerator._adjacent_pair_exists(gt_positions, threshold=2)` (new static method, ground-truth positions only, Manhattan distance, no path/tick/priority reasoning, so it is not a reimplementation of `collision_engine/` logic; the grid is 4-connected) and `try_apply_comm_delay(tick, transport_bus, gt_positions)`, which now raises `FaultGuardRejected` when any two robots are within 2 cells. `maybe_generate` (same file) and `_apply_manual_injection` (`session.py`) pass `gt_positions` through. A rejected attempt takes the same path as every other guard rejection (a SYSTEM "fault skipped" event for auto-generation, an injection-rejected event for manual) and does not update the fault cooldown, so the generator retries on later ticks. The method name still says "adjacent" although the threshold is 2. `clear_expired_comm_delay` is unchanged.
  - **Threshold history.** Approved first at 1 (orthogonally adjacent). A pre-implementation check on the 33 traced blackout collisions found all 33 at distance 1 with a stationary sitter, but it only examined single-mover cases. The soak at threshold 1 left one blackout case, **seed 95, tick 3**: COMM_DELAY started at tick 3, the two robots (`PR3`, `PR4`) were at distance 2 and **both** stepped into one cell. Threshold 2 was then approved and closes it.
  - **Result (deterministic harness, vanilla detector, faults on, 120 seeds, 420 ticks, cooldown 3, `start_tick` edit present).**

    | | Colliding runs / 120 | COMM_DELAY episodes applied | COMM_DELAY attempts rejected by the guard |
    |---|---|---|---|
    | Before (guard neutralised in a scratch control, reproduces the earlier figure exactly) | **63** | 240 | 0 |
    | Guard, threshold 1 | 34 | 68 | 162 (70.4% of 230 attempts) |
    | **Guard, threshold 2 (current)** | **33** | **58** | **172 (74.8% of 230 attempts)** |

    Episodes fell from 240 to 58 (2.0 to 0.48 per 420-tick run on average). All COMM_DELAY rejections were the guard; no cooldown or "already active" rejection occurred for COMM_DELAY. AISLE_BLOCK rejections in the same soak were 28, all "would strand a task" or "no eligible cell".
  - **Residual, first-collision classification at threshold 2** (same classifier as before): 12 runs whose first collision was an edge swap; and by first vertex event, **11 face-to-face same-cell (Defect 2's same-cell shape), 8 stale-stamp converging paths, 5 MOVING-labelled peer stopped (3 BLOCKED + 2 WAITING), and 0 blackout** (34 before the guard). So the residual is **not exclusively Defect 2**: it is Defect 2 (swaps and face-to-face) plus the two independent classes already listed under "Other same-cell classes".
  - **Not re-measured with the guard:** the V4 (adjacency candidate) configuration.
  - **What the guard does not do.** It does not remove the agent's underlying susceptibility (no last-known memory of a peer across ticks, in `robot_agent/agent.py`); it only stops Product mode's own fault generator from creating the transition at a moment when it matters. It constrains fault realism: about three quarters of COMM_DELAY attempts are declined because some pair of robots is within 2 cells.
  - **Benchmark and `d_deadlock` are unaffected.** The guard runs only inside `WorldFaultGenerator`, which only `simulation/product/session.py` constructs. `simulation.product` is imported only by `simulation/runner.py` (lazy imports inside the Product routes) and by itself; no benchmark, scenario or test file imports it. `d_deadlock` applies a constant `MessageFaultConfig(delay_ticks=1)` from tick 0 through the scenario path, so it has no activation edge and never reaches this code. Full pytest after the change: 286 passed, 27 subtests, unchanged.
- **Evidence (as originally written, before the fix).**
  - **Seed 2, faults on, tick 71.** `PR2` had tracked `PR1` waiting at (11,11) for several ticks (tick 70 held-cell map `{(12,3):PR5, (11,11):PR1}`). At tick 71 `PR2`'s receive contains nothing from `PR1` (while `PR5`'s message arrives), the map becomes `{(12,3):PR5}`, `PR2`'s detector returns `None`, and it moves (10,11)->(11,11) into the waiting `PR1`.
  - **Seed 82, tick 25.** `PR5` receives nothing from `PR2`, forgets it is sitting at (7,0), and enters it. The pair then stays co-located for 396 ticks.
  - **Statistic.** **33 of 33** examined first-collisions of this class (mover received no message from the robot it entered) fall exactly on a COMM_DELAY start tick, with the sitter ticking earlier than the mover.
- **Aftermath (a separate observation).** After a collision the two robots stay in one cell: nothing compares a robot's own cell with a peer's. In four runs the pair stayed co-located for 304-396 ticks. This inflates total collision counts.

### Other same-cell classes found (not among the three, pre-existing, independent)

| Class | Trace | Share of first same-cell events (vanilla fault-free 30 / vanilla soak 56 / V4 soak 45) |
|---|---|---|
| Two waiting robots converge on one cell; tick-keyed SAME_CELL blind because both paths carry stale, different stamps (cause a) | Seed 9, tick 17: `PR4` `(11,4,14)` vs `PR5` `(11,4,16)`, both resume together | 7 / 9 / 2 |
| Earlier-ticking robot enters a cell whose MOVING-labelled occupant then stops that tick | Seed 69, tick 5: `PR3` enters (2,0); `PR4` (labelled MOVING) then waits on a third robot | 1 / 5 / 3 |
| Face-to-face adjacency (Defect 2's same-cell shape) | Seed 14, tick 3 | 22 / 8 / 0 |
| Message blackout (Defect 3) | Seed 2, tick 71 | 0 / 34 / 40 |

On vanilla fault-free, 4 runs had a swap first and a same-cell collision later, so same-cell collisions are not merely unmasked by the swap class; they were already present on vanilla.

---

## 4. The three-way interaction

- **Fixing Defect 2 does not fix Defect 3.** With V4 applied and COMM_DELAY on, 45 of 120 runs still collide, and 40 of those 45 first collisions are the message-blackout class.
- **Colliding soak runs out of 120 (deterministic harness, cooldown 3):**

| | COMM_DELAY on | COMM_DELAY disabled entirely |
|---|---|---|
| Vanilla detector | **63** | **31** |
| Adjacency candidate (V4) | **45** | **6** |

- Read across the table: disabling COMM_DELAY alone (no detector change) takes 63 to 31; the adjacency candidate alone takes 63 to 45; both together take it to 6. With COMM_DELAY disabled, the adjacency candidate takes 31 to 6. In terms of colliding runs, Defect 3 is the larger contributor to Product-mode soak collisions, and it is the dominant cause of what remains after Defect 2's candidate.
- **What was tested (as originally written).** Only *disabling COMM_DELAY entirely* was run. Two other directions had been discussed as untested:
  1. Change the Product-mode fault generator so the delay is not toggled mid-run (Product-mode-only; touches neither `collision_engine/` nor `robot_agent/`).
  2. A per-peer last-known-state memory in the movement guard. That lives in `robot_agent/agent.py`, which is Tier A even though it is not `collision_engine/`.
- **Update (2026-09-24, later):** direction 1 was carried out in a different form. Reading `InProcessBus` showed the activation transition cannot be timed away, so the change is a guard on *when* an episode may start (section 3, Defect 3), not a different toggle. Measured: vanilla detector, faults on, **63 to 33 colliding runs out of 120**, with 0 blackout-class first collisions remaining. Direction 2 (agent-side memory) was not run and remains untested. The combination of the guard with the adjacency candidate (V4) was not re-measured. The table above is unchanged: it records the measurements as they were taken, before the guard.

---

## 5. Open decisions awaiting explicit approval (all still open)

- **(a)** Whether to apply the Defect 1 `start_tick` fix (currently an uncommitted working-tree edit; not merged). **Still open, and independent of (b) as of 2026-09-25.**
- **(b)** ~~Whether to apply a Defect 2 fix, and which: V4 / V4h (detector), the newly found V6 / V6b (agent-side physical guard, detection untouched), or none. The trade-off is now better understood (see the Defect 2 addendum in section 3): `d_deadlock`'s audited 12 ticks / 2 activations is a byproduct of the same adjacency gap, so a detector fix removes an artifact rather than a real deadlock capability (that capability is separately supported by a single-file-corridor test and `g_high_load`), but it changes an audited number and fails two tests; V6/V6b leave `d_deadlock` and all 90 benchmark runs byte-identical, cost less throughput (-8.1% / -12.4% versus -20.3%), and live in `robot_agent/agent.py` (Tier A). No variant was applied.~~ **DECIDED and DONE (2026-09-25): V6b was applied** (section 3, "V6b applied"). V4/V4h and V6 were not.
- **(c)** **Moot as of 2026-09-25 (V6b leaves `d_deadlock` unchanged, both tests pass).** Originally: whether to re-point, or accept losing, the two `d_deadlock`-based tests `TestDeadlockCountReflectsRealDetector::test_deadlock_count_is_not_the_old_yield_proxy` and `::test_deadlock_count_matches_detector_activations_when_it_fires`. Nothing has been changed; the standing rule is that no assertion is loosened.
- **(d)** ~~Whether Defect 3 should be handled first, as a Product-mode-only, non-Tier-A change, before revisiting whether Defect 2 is still needed for Product mode's soak numbers to look acceptable.~~ **DECIDED and DONE (2026-09-24):** Defect 3 was handled first, as a Product-mode-only guard (section 3). The residual is now 33 colliding runs out of 120 on the vanilla detector; decisions (a), (b), (c) and (e) remain open.
- **(e)** Whether any of this goes into judge-facing materials (deck/PDF) or stays in internal documentation only.

---

## 6. Corrections to statements made earlier in this investigation

A fresh session should not re-trust these:
1. "`ConflictDetector` has no edge-swap check." Wrong: `_check_crossing` is one. The real gap is that it cannot see exactly adjacent robots.
2. The probe labels "two apart"/"three apart". Both probes were gap 3. The corrected gap table is in section 3 and in CLAUDE.md #11; `docs/COLLISION_DETECTION_ADJACENCY_GAP.md` sections 1 and 4 and two proposed test names were corrected to match.
3. The early soak totals (2,363; 2,448; 2,851). Non-reproducible harnesses; do not compare with section 3.
4. The comment block beside the `start_tick` edit in `agent.py` (see Defect 1): overstates the evidence.

---

## 7. Files touched or added, and working-tree state

**Method.** The list below was produced by finding every repository file modified on or after 2026-09-19 (the start of this effort), then checking each against `git status`. **Nothing under `collision_engine/`, `simulation/referee.py`, `simulation/scenarios/`, `simulation/tests/`, `simulation/benchmarks/`, `planner/`, `edge/`, `robot_agent/tests/` or any test file has a modification time on or after 2026-09-19** (`collision_engine/*` was last modified 2026-09-04).

| File | What | Git state | Kind |
|---|---|---|---|
| `simulation/product/__init__.py`, `envelope.py`, `task_inbox.py`, `world_faults.py`, `session.py` | New Product-mode driver. **Later edit (2026-09-24, approved):** the Defect 3 COMM_DELAY guard in `world_faults.py` (`_adjacent_pair_exists`, `try_apply_comm_delay` gained a `gt_positions` parameter, threshold 2) and one call-site change in `session.py` | untracked (uncommitted) | **Code** |
| `simulation/runner.py` | Added `_product_session`, lock guard, four routes | tracked, modified (file already dirty before this effort) | **Code** |
| `robot_agent/agent.py` | The `start_tick=current_tick - 1` edit and its comment block, **and (2026-09-25) the V6b movement guard: 68 added lines, 0 removed** (`_peer_next_cells`, `_peer_outranks`, `_peer_to_hold_for`, one block at the top of `_advance_one_cell_if_clear`) | tracked, modified (file already dirty before this effort) | **Code (Tier A), uncommitted** |
| `robot_agent/tests/test_agent.py`, `simulation/tests/test_runner.py` | 2026-09-25: 13 new tests for V6b (12 and 1); no existing test or assertion changed | tracked, modified (files already dirty) | **Tests, uncommitted** |
| `docs/MOVEMENT_GUARD_V6B_PROPOSAL.md` | V6b design review (diff, tests, blast radius, `start_tick` 2 x 2) | untracked | Documentation |
| `backend/.../service/ProductSessionService.java`, `controller/ProductController.java`, `model/ProductSessionStatusDto.java` | New Java product classes | untracked (uncommitted) | **Code** |
| `backend/.../service/SimulationClient.java` | Four additive methods | tracked, modified (already dirty before this effort) | **Code** |
| `CLAUDE.md` | Known Bugs #4 status, new #11, and status wording in the Known Limitations and Next Steps lists | **untracked (never committed)** | Documentation |
| `docs/COLLISION_DETECTION_ADJACENCY_GAP.md` | Adjacency design proposal (diff, tests, blast radius) | untracked | Documentation |
| `docs/PRODUCT_MODE_INVESTIGATION_STATUS.md` | This document | untracked | Documentation |
| `.claude/scheduled_tasks.lock` | Tooling artifact from scheduled wake-ups | not part of the work | Tooling |

**Not created, although referred to:** `docs/PRODUCT_MODE.md`.

**The exact `start_tick` hunk** (working tree versus HEAD, from `git diff -U1 robot_agent/agent.py`; the rest of that file's diff is earlier, pre-existing uncommitted work):
```diff
+        # FIXED (was a documented, deliberately-deferred defect — see
+        # CLAUDE.md Known Bugs #4 and the Product-mode Phase 3 soak-test
+        # root-cause finding): ... [comment block; see the correction note in Defect 1]
         if self._needs_replan() and self.planner and self.state.destination:
@@
                     self._known_blocked_cells(),
+                    start_tick=current_tick - 1,
                 )
```

**Scratch artifacts (outside the repo, session-specific, may not survive).** Base directory `C:\Users\pikac\AppData\Local\Temp\claude\g--SIH2026\b7020054-5ef1-45ff-b701-60469bd3934f\scratchpad\`:
- `baseline_benchmark/`: pre-change 270-run output (`raw_results.csv`, SHA-256 `a30616690f...7056d0`). `phase1_benchmark/`: same checksum. `starttick_fix_benchmark/`: 270-run output with the `start_tick` edit.
- `adjacency/`: the variant harness (`variants.py`, `detection_patched*.py` for V3/V4/V5), the deterministic runner (`det_run.py`, env `NO_COMM_DELAY=1` disables COMM_DELAY), trace and classification scripts (`sc_trace.py`, `sc_classify.py`, `sc_scan*.py`, `sc_nomsg.py`, `classify.py`, `dd_diverge.py`), scenario-equivalence runs (`e3_scenarios.py`), the drafted regression tests (`test_adjacency_proposed.py`), the two `.diff` files, and all result logs/JSON.
- Earlier soak and repro scripts (`soak_test*.py`, `repro_*.py`, `smoke_product*.py`, `trace_crossing*.py`, `probe_geometry*.py`) and throw-away test databases.
- The design document holds the diff and all 10 proposed tests verbatim, so the essentials survive without the scratch directory.

**Git state at the time of writing (read-only).** Branch `develop`, HEAD `6d37ccf` (2026-09-04, "merge: integrate edge interface"). Immediately before this file was created: 7 deleted, 43 modified, 61 untracked entries (this document adds one untracked file). **Almost everything done since 2026-09-04, including the audited benchmark itself, is uncommitted**: `simulation/benchmarks/`, `simulation/scenarios/i_parallel_aisles.py`, `simulation/tests/test_benchmark.py`, `simulation/tests/test_scenario_position_validity.py`, `simulation/scenario_validation.py`, `CLAUDE.md`, `report.md`, the `benchmark_results*/` directories and most of the backend and dashboard are untracked. The pre-existing dirt in the files this work edited is large (`git diff --stat` versus HEAD: `robot_agent/agent.py` 267 lines, `simulation/runner.py` 661, `collision_engine/detection.py` 89, `collision_engine/tests/test_detection.py` 132, `SimulationClient.java` 223), none of it from this effort except the hunks listed above.

---

## 8. Reconfirmation

- **No file in `collision_engine/` has been modified as a result of this investigation** (last modification 2026-09-04). `git status` does list `collision_engine/detection.py` and `collision_engine/tests/test_detection.py` as modified versus HEAD: that is earlier sessions' uncommitted work (the stationary-peer occupancy fix and its tests, recorded in CLAUDE.md Known Bugs #4), not part of this investigation.
- **No test file has been modified** (none has a modification time on or after 2026-09-19), and the two `d_deadlock` deadlock-count tests are untouched.
- **`robot_agent/agent.py` contains exactly one change of mine, the `start_tick` edit**, from an earlier, separately approved step. It is validated and **uncommitted**.
- No candidate adjacency fix was applied at any point; all were grafted in scratch processes.
- **Defect 3 guard (added 2026-09-24, later):** the only repository change since this snapshot was first written is the guard in `simulation/product/world_faults.py` plus one call site in `simulation/product/session.py`. No test file, `collision_engine/`, `robot_agent/`, `InProcessBus`/`MessageFaultConfig`, scenario, benchmark harness or benchmark result was touched; full pytest is 286 passed / 27 subtests, unchanged; `simulation.product` is still imported only by `simulation/runner.py` and itself.
- **2026-09-25 (earlier):** only documentation changed (this file and CLAUDE.md Known Bugs #11 plus two short scoping pointers). **2026-09-25 (later): V6b was applied to `robot_agent/agent.py` and 13 tests were added (see section 3, "V6b applied"); the statements in this section that no test or Tier A file changed describe the state before that.** V4, V6 and V6b exist only as in-memory grafts in scratch processes; `robot_agent/agent.py` and `collision_engine/` are unchanged by this investigation, no test was modified, and the audited deck/PDF/report were not touched.
- No git write operation was performed.
- No benchmark number, report, or deck was updated.

---

## 9. Product-mode liveness investigation (opened 2026-09-25, read-only; facts and measurements only, no fix proposed)

Trigger: the V6b clarification trace showed a pair in an 8-cell single-file corridor (seed 57, row 14, x = 3..10) still stuck at tick 384, and a stall metric showed almost every robot in every configuration (vanilla included) stalled for most of a soak. Nothing below was applied; all runs are scratch processes on the deterministic harness (in-thread feeder, cooldown 3, Defect 3 guard in place).

### 9.1 Seed-57 corridor stall: root cause

Sequence for `PR3` (lower priority, task `x_57_3` assigned once at tick 1, destination (5,14)), traced with planner calls, avoid cells and replan flags:

1. t23: the stall counter reaches 5, the stall detector fires (`_force_yield`), and because `PR3` is the lower-priority side it adds its next path cell (7,14) to `_temporary_avoid_cells`.
2. t24: a replan with (7,14) avoided returns a 21-waypoint detour east, (9,14), (10,14), (11,14), (11,13), and so on. That route runs head-on into `PR1` (priority 4, westbound in the same corridor), so the resolver says WAIT (`_waiting_on = PR1`).
3. t28: stall 5 again, `_force_yield` fires again and adds (9,14), the first cell of the detour, to the avoid set.
4. t29 onward: both neighbours of (8,14) are now avoid cells, so the planner returns **zero waypoints (no exception)**. The agent sets status MOVING with `currentPath == []`, `_needs_replan()` is true every tick (no path, not at goal), and every tick returns the same empty result. It is still like that at tick 384.
5. Peers: `PR3` broadcasts MOVING with an empty planned path, which `_collect_peer_held_cells` treats as stationary, so `PR2` (priority 5, path through (8,14)) is held by the existing stationary-peer guard; as the higher-priority robot its own `_force_yield` never steps aside, so it replans the same path forever.

Root cause, in code: `_temporary_avoid_cells` is appended to (in `_apply_action` for YIELD and REROUTE, and in `_avoid_cell()` from `_force_yield`) and is **never cleared or expired anywhere in the repository** (the only read is in `_known_blocked_cells()`); an empty planner result is accepted as a route rather than treated as a failure. This is **agent-level (`robot_agent/agent.py`), not the Product-mode session driver**: the task was assigned once and never touched, and `simulation/product/session.py` contains no reference to `_temporary_avoid_cells` (it neither clears them nor clears them on reassignment). The session's only stall detection is the global "no robot moved and no task completed for 30 ticks" watchdog, which cannot fire while any other robot moves. V6b's holds at t21-t24 only put the two robots adjacent; from t25 neither V6b rule is firing. Vanilla shows the same mechanism (section 9.2).

### 9.2 Partition of every robot-tick (120 seeds; the harness feeder assigns a new task 3 ticks after each completion)

| Share of all robot-ticks | Fault-free, 150 ticks, V6b applied | Fault-free, vanilla | Faults on, 420 ticks, V6b applied | Faults on, vanilla |
|---|---|---|---|---|
| Moved (productive) | 24.9% | 26.0% | 7.8% | 8.6% |
| Stalled with work outstanding | **69.0%** | **67.6%** | **54.8%** | **54.1%** |
| IDLE (no task) | 5.1% | 5.4% | 1.5% | 1.7% |
| Dead (injected ROBOT_OFFLINE, never recovers) | 0 | 0 | **35.6%** | **35.4%** |

With faults on, stalled robot-ticks are 85.0% (V6b) / 83.7% (vanilla) of the robot-ticks of robots that are not dead. **Reconciliation with the earlier "63% / 88%" figures:** those counted robot-ticks inside stalls of 30 or more ticks and, with faults, counted dead robots (64.8% fault-free and 88.5% with faults for V6b; 63.4% and 87.7% for vanilla).

Stalled robot-ticks by cause (evidence at that tick: the blocking-peer chain followed to its terminal robot, the robot's own path, its status):

| Cause (% of stalled / % of all robot-ticks) | Fault-free V6b | Fault-free vanilla | Faults V6b | Faults vanilla |
|---|---|---|---|---|
| Robot has NO ROUTE (MOVING, empty path) | 47.9% / 33.1% | 45.0% / 30.4% | 45.9% / 25.2% | 42.3% / 22.9% |
| Stuck behind a robot with NO ROUTE | 38.6% / 26.7% | 42.8% / 28.9% | 16.7% / 9.2% | 19.7% / 10.7% |
| Stuck behind a DEAD robot | 0 | 0 | 20.2% / 11.1% | 30.2% / 16.3% |
| Held by the V6b guard this tick | 4.4% / 3.0% | n/a | 12.2% / 6.7% (68% of these are for dead robots, section 9.4) | n/a |
| Behind a robot that is itself moving (transient) | 3.4% / 2.4% | 4.1% / 2.8% | 1.1% / 0.6% | 1.3% / 0.7% |
| Mutual-wait cycle | 2.3% / 1.6% | 3.3% / 2.2% | 0.7% / 0.4% | 3.3% / 1.8% |
| BLOCKED status | 1.5% / 1.0% | 1.7% / 1.1% | 1.9% / 1.0% | 2.1% / 1.1% |
| Behind a parked IDLE robot | 1.3% / 0.9% | 1.7% / 1.2% | 0.4% / 0.2% | 0.5% / 0.3% |
| Other / no blocker within +-2 ticks | 0.5% / 0.4% | 1.4% / 1.0% | 0.8% / 0.5% | 0.6% / 0.4% |

Stalled robot-ticks by how the stall ended: **92.8% to 93.6% are in episodes still open at the end of the run and at least 30 ticks long** (51% to 64% of all robot-ticks); episodes that resolve within 10 ticks are **4.6% of stalled fault-free (3.2% of all robot-ticks) and 2.0% with faults (1.1% of all)**; resolved episodes of 11-50 ticks add about 1%.

### 9.3 The avoid-cell mechanism is necessary for the no-route stalls (direct measurement, not a fix trial)

Fault-free, 120 seeds: 518 robots end a run stalled 30 or more ticks with work outstanding; 276 of them have an empty path.
- **All 276 (100%) have a destination that is reachable if the avoid cells are ignored** (a planner query with only genuine map blocks; the same query with the avoid cells returns no route, as expected). In a 10-seed pass, all 2,452 empty-path stalled robot-ticks belonged to robots carrying at least one avoid cell, and none of 2,454 zero-waypoint planner calls was made without avoid or blocked cells.
- Only 72 (26%) are physically walled in by their own avoid cells; **204 (74%) are cut off by avoid cells that are not adjacent** (the seed-57 corridor is the walled-in special case, not the typical one). Avoid cells per empty-path robot: mean 3.06, maximum 11.
- Where they come from (cells added over the 120 runs): 750 from the stall detector's `_force_yield`, 585 from YIELD/REROUTE verdicts.
- A second, smaller pattern: robots stuck WAITING one cell from their destination behind a robot that is itself walled in (seed 8: `PR2` at (11,1) waiting on `PR4`, which sits on `PR2`'s destination (11,0) with avoid cells (11,1), (12,0), (10,0)). The stall detector clears the blocker pointers on the tick it fires (every 5th tick), which made an earlier classification pass label about 10% of stalls "no blocker recorded"; the final classifier looks +-2 ticks for the pointer and that share falls to about 0.5%.

### 9.4 Other measured facts

- **A dead robot's agent status is not sticky.** A REASSIGN_TASK verdict in `_apply_action` (`robot_agent/agent.py`, the `REASSIGN_TASK` branch) sets status BLOCKED on a robot whose sensor is OFFLINE; `_apply_telemetry` sets OFFLINE again next tick and the resolver flips it again. Dead-robot robot-ticks with faults (V6b): 73,629 read OFFLINE, 15,588 BLOCKED, 386 WAITING. A first classifier pass that used status alone undercounted dead robots and inflated BLOCKED; the classifier now takes "dead" from the injected fault.
- **V6b holds for dead robots:** with faults, 12,036 of 17,614 guard hold-ticks (68%) have a dead holder (rule 1: 9,163; rule 2: 2,873); rule 1 is redundant with the stationary-peer guard, rule 2 is a false hold (Known Bugs #11, V6b paragraph).
- **Task cadence in this harness is not a material cause:** the completion-to-next-assignment latency is a constant 3 ticks (the reassignment cooldown); IDLE is 5.1% of robot-ticks fault-free and 1.5% with faults; parked idle robots obstruct another robot on 820 of 4,554 fault-free idle robot-ticks (0.9% of all robot-ticks) and are the terminal of only 1.3% (fault-free) / 0.4% (faults) of stalls. **Limitation:** this harness assigns tasks in-thread; the real Java-driven loop (200 ms poll, allocation on its own cadence) was not measured here and could add idle time.
- **The stall problem is not V6b-specific:** vanilla and V6b differ by about 1.4 points of stalled share and the cause mix is the same.

### 9.5 Attribution (observed cause chains, not a counterfactual)

- **Agent-level recovery (`robot_agent/agent.py`): dominant fault-free.** No-route robots plus robots stuck behind them are 86.5% of stalled robot-ticks (59.8% of all robot-ticks) fault-free with V6b (87.8% vanilla) and 62.6% of stalled (34.4% of all) with faults. The mechanism is the never-expiring avoid cells plus an empty plan accepted as a route; there is also no back-out primitive for a genuine single-file head-on (earlier corridor tests: identical under every variant).
- **Session / fault design: the second contributor, and with faults the largest single block.** Injected ROBOT_OFFLINE is permanent by construction (the agent has no way back from OFFLINE; the `world_faults.py` docstring records this): dead robots are 35.6% of all robot-ticks with faults, robots stalled directly behind them a further 11.1% (and about 4.6% more sit under the guard label). Task-feeding cadence contributes at most about 6% (idle) fault-free and about 2% with faults in this harness.
- **Both, with different weights by regime:** fault-free, the agent-level mechanism accounts for roughly 60% of all robot-ticks and session cadence for at most about 6%; with faults, roughly 34% agent-level and roughly 47% to 51% fault design (dead robots plus the robots stuck behind them), plus a few points of brief coordination.
- **Genuine brief coordination** (episodes resolved within 10 ticks) is 3.2% of robot-ticks fault-free and 1.1% with faults.

### 9.6 Limits of this evidence

Single deterministic harness (120 seeds; 150 and 420 ticks); the partition is by observed state and cause chain, so a stall with several causes is assigned to the first cause found; no fix or counterfactual was run; the real Java task cadence was not measured; the corridor geometry in seed 57 is one instance (section 9.3 gives the general case).

---

## 10. Task-backlog freeze under the real Java cadence, and its fix (2026-09-25 to 09-26; facts and measurements only)

### 10.1 Results of the last agent-level candidate round (scratch grafts; nothing applied; agent-level investigation closed)

- **Hybrid (`fallback:keep` plus a last-resort escape hatch after M stalled ticks, releasing only avoid cells no peer is near):** the 9 scenarios, the 12-cell `d_deadlock` matrix, the corridor cases and the full test suite (299 passed under the graft) were all neutral or identical to `fallback:keep`. In the 120-seed soak it did not keep `fallback:keep`'s property of improving throughput and collisions together: fault-free colliding runs 8 (baseline), 6 (`fallback:keep`), 12 (hybrid M=20; 9 at M=15, 12 at M=25); faults on 4, 4, 3 (5 at M=15 and M=25). Seed 57's corridor case was not resolved (the peer-near safeguard suppressed the release where the blocker sits on the avoid cell). Without the peer-near check (M=20) it was worse: 14 colliding runs fault-free. Of stall episodes reaching 20 ticks, 96.4% never move again in the run (fault-free; 3.5% self-resolve with faults).
- **Real Java cadence differs structurally from the constant-cadence harness** (read from `ProductSessionService`/`TaskAllocationService`: `MAX_BACKLOG = 3`, one task per 8-16 ticks, nearest-idle allocation, completion = IDLE at the drop cell). In a Java-faithful model, throughput ends far earlier than in the harness (median last completed task at tick 59 versus 99; 116 of 120 seeds with no completion after tick 150) and the perturbation effect is much rarer (colliding runs the variant has and the baseline does not, fault-free: `ttl:10` 1 versus 19 at harness cadence; hybrid 1 versus 6; `fallback:keep` 0 versus 0). The seed-14 case did not reproduce under Java timing.
- **Product-only accumulation-rate mitigations** (session level, no Tier A), harness cadence, fault-free colliding runs / tasks: baseline 8 / 1,733; reassignment cooldown 20: 3 / 1,083; cooldown 40: 2 / 1,041; cap of 3 concurrent tasks: 2 / 539; cap of 2: 0 / 195; stuck watchdog: 17 / 3,535; clear-on-assignment: 11 / 1,587. Robots stranded at the end (of 600): 549-596 for the cooldown and clear-on-assignment variants, 498-519 for the watchdog, 240-362 under the caps. Under Java cadence none changed anything material (tasks 411-520 versus 423).

### 10.2 The freeze

Under the real cadence, `ProductSessionService` counts a task against `MAX_BACKLOG` until its robot is IDLE at the drop cell. A robot that strands (section 9) never completes, so three stranded robots stopped all task generation: in the Java-faithful model every one of 120 sessions froze, with no task created after roughly tick 180 (about 90 s of LIVE at 1x). Raising the cap to 6 or 8 only delays it (60 seeds x 2000 ticks, fault-free: 211 / 537 / 556 completed tasks at cap 3 / 6 / 8, all 5 robots stranded at the end for cap 6 and 8, mean 3.0 at cap 3). Abandoning a stalled task without recovering its robot gave the same result (all 5 stranded), because the robot is never IDLE and so never allocatable.

### 10.3 The fix that was applied (Product mode only; Java and `simulation/product/`; `robot_agent/` untouched)

- `ProductSessionService.abandonIfStalled` (Java): a pushed task whose robot has not changed cell in the cache for `STALL_ABANDON_TICKS = 30` ticks is marked `FAILED`, its slot is freed, and `SimulationClient.releaseRobot` (new; `POST /control/release`) asks Python to release the robot. The release request is sent before any DB write; a failed task save aborts the poll and is retried on the next one; a failed event write is only logged. OFFLINE robots are skipped.
- Python: `TaskInbox.submit_release` / `drain_releases`; `ProductSession._apply_release` clears the robot's avoid cells and wait state and sets it IDLE with no destination; it refuses an unknown, OFFLINE or sensor-dead robot (a dead robot's agent status is not sticky), an already-IDLE robot, and a robot no longer on the abandoned task, each with a SYSTEM event saying why.
- Tests: `simulation/tests/test_product_release.py` (8), `ProductSessionServiceStallTest` (8), 2 in `SimulationClientTest`.

### 10.4 Measurements of the fix

- **Java-faithful model, 120 seeds x 2000 ticks**: every session keeps creating and completing tasks to the end. Robots stranded at the end, mean: fault-free 1.1 (was 3.0), faults on 1.5 (was 3.4). Completed / abandoned: fault-free 7,013 / 9,492, faults on 9,573 / 6,899 (was 1,418 completed). Completions per 300 ticks summed over the 120 sessions, fault-free: 1,275, 1,157, 1,116, 1,041, 961, 897. 10 seeds x 3600 ticks: all still completing in the last 600 ticks; 108 falling to 47 per 300 ticks fault-free. Colliding sessions: fault-free 11 (3 are the t=9 start-up collisions seeds 3, 97 and 110 also have without the fix), faults on 11 versus 5 without the fix. Each later collision occurred 0-14 ticks after an assignment was applied to one of the two robots; one of them was also 4 ticks after a release.
- **REAL full stack** [collision counts here cover only about the first 1,440 ticks, see 10.7] (real Java backend, real Python engine, LIVE speed x4, 2000 ticks, seeds 1 / 14 / 57 / 68 / 93, fresh backend and database per seed): created 147 / 146 / 155 / 153 / 114; completed 85 / 64 / 107 / 80 / 56 (392); abandoned 60 / 80 / 47 / 73 / 55 (315); collisions 0 / 0 / 0 / 0 / 1 (seed 93, tick 44, a robot assigned a task at that tick, no release involved). Generation and completion continue to the end of every session; seed 93 has 2, 0 and 3 completions in its last three ~300-tick windows. An earlier real-stack pass (before the release request was moved ahead of the DB writes) produced 51 / 56 / 94 / 81 / 40 completed and 0 collisions.
- **Verification after the fix**: pytest 307 passed / 33 subtests; backend 48 passed (one transient run showed 26 datasource start-up errors and passed on the immediate re-run with nothing changed; not investigated); the 270-run benchmark `raw_results.csv` SHA-256 is `32d492d87ccbf3bb3c1673645fe2e25a32e0c836fcb94abd801cd184274cdb5e`, identical to the post-V6b run; 0/270 collisions.

### 10.5 Limits

- 42.5% (fault-free) to 58.1% (faults on) of resolved tasks in the model complete; the rest are abandoned. The real-stack sessions completed 55% (392 of 707). The stranding itself is untouched.
- Throughput decays over a session and can reach zero in a late window on some seeds (real-stack seed 93). Permanent ROBOT_OFFLINE robots (at most 2 concurrent) sit in aisles.
- The backend's SQLite file is "database is locked" under telemetry load: 375-450 SQLITE_BUSY errors and 43-54 failed poll cycles (about 2-3%) per real-stack session. Pre-existing; unchanged.
- Pre-existing, unchanged: task rows persist across backend restarts and a leftover `ASSIGNED` row keeps a robot busy in a later session; `RobotCacheService.lastTick()` never resets within one backend process.
- The events endpoint returns at most 2,000 events, so per-window event counts read from it undercount; the real-stack figures above are from the session status counters.
- 30 ticks was compared with 20 and 45 (60-seed model, colliding sessions 4 for 30, 12 for 20, 6 for 45) and not tuned further. The model is a Python re-implementation of Java's logic; each real-stack seed ran once.

### 10.6 Calm-configuration test (2026-09-26; Java-faithful model, 60 seeds x 2000 ticks, abandon threshold 30 unless stated; nothing applied)

Question tested: does lower traffic intensity (backlog cap 1-2, longer task interval, wider reassignment cooldown) bring the abandonment rate down to about 15-20%? Abandonment rate = abandoned / (abandoned + completed). Values are fault-free / faults on (the session's own generator).

- **Lower traffic did not reduce abandonment.** Cap x interval (min ticks + jitter 8/8, 16/8, 30/10): cap 3 57.3/41.0, 57.0/42.4, 62.1/42.4; cap 2 56.7/40.6, 57.7/40.2, 62.0/42.4; cap 1 57.1/42.7, 58.9/44.7, 62.2/43.7. Cooldown 10: cap 2 57.3/41.8, cap 3 57.2/39.2. **Dead stretches got worse** with calmer settings (sessions with a gap over 150 ticks between completions, of 60, fault-free/faults on: cap 3 interval 8: 27/19; cap 2: 46/31; cap 1: 60/49). Collisions fell with traffic (colliding sessions, cap 1: 0/0; cap 3 interval 8: 4/2).
- **Abandon threshold 15 instead of 30** (cap 2 / cap 3, interval 8): abandonment 57.7/44.1 and 58.9/47.0 (no reduction); completions per session +5% to +13%; dead-stretch sessions 21/12 and 19/17; colliding sessions 2/6 and 3/10 (cap 3 at threshold 30: 4/2).
- **Where the abandoned tasks stall** (cap 1, 30 seeds, fault-free): of 500 abandonments that were waiting on an IDLE robot, 331 (66%) had that robot parked ON a drop cell, 67 on a pickup cell, 102 elsewhere. Cap 1 leaves one moving robot among four parked ones, so parked idle robots and the destination cell itself being occupied, not traffic, are the dominant blockers. (The task generator picks a drop cell at random and a robot that finished a task stays on its drop cell.)
- **Diagnostic variant, not applied: task generation never picks a drop cell that a robot currently occupies or that is already an open task's drop.** Cap 3 interval 8, threshold 30: abandonment 37.0/22.5%, completions per session 100.4/124.5 (from 58.6/81.3), dead-stretch sessions 5/0 of 60 (from 27/19), median longest gap 102/77 ticks, mean robots stranded at the end 0.10/0.60, negotiations (WAIT/YIELD/REROUTE) 45/65 per session, colliding sessions 11/10 of 60 (4/2 without it). Cap 2: 37.3/25.7, dead 17/5, colliding 9/6; cap 1: 39.5/26.4, dead 52/28, colliding 0/0; cap 2 interval 16: 37.3/23.4, dead 21/4, colliding 4/8. With threshold 15: cap 3 40.3/26.7, dead 3/3, colliding 10/14; cap 2 40.3/29.5, dead 2/3, colliding 6/7.
- Remaining cause mix for cap 3 with that variant, fault-free (3,539 abandonments): no route (empty plan, from accumulated avoid cells) 1,796, waiting on an IDLE robot 750, no blocker recorded 597, waiting on a WAITING robot 233, on a MOVING robot 163.
- Limits: model only (a Python re-implementation of Java's logic; earlier real-stack runs showed the model over-states late-session throughput for some seeds); colliding-session counts are single digits per cell; no real-stack run of any configuration in this subsection was made.

### 10.7 Applied mitigation: never assign an occupied or already-targeted drop cell (2026-09-27; NOT a full fix)

- **Change (Java only):** `ProductSessionService.unoccupiedDropPoints()`, called from `maybeGenerateTask`, picks a new task's drop cell only among cells that no robot of the session stands on (per `RobotCacheService`) and that are not the drop cell of an open task; if every drop cell is taken it uses the full list. Unconditional, so it is the default. Four unit tests in `ProductSessionServiceDropCellTest`.
- **Real full stack, seeds 1 / 14 / 57 / 68 / 93, LIVE x4, 2000 ticks each, fresh backend and database per seed, same counting for both sets:**

| | with the rule | without the rule |
|---|---|---|
| Created / completed / abandoned | 795 / 612 / 174 | 764 / 443 / 309 |
| Abandonment | **22.1%** (per seed 26, 26, 21, 18, 19%) | **41.1%** (43, 59, 49, 28, 27%) |
| Gaps over 150 ticks between completions | **0** | 3 (seeds 14, 57) |
| Longest gap | 79-113 ticks | up to 194 |
| Collisions | 2 (both in seed 57, ticks 720 and 1348) | 0 |

- **Against the model's prediction** (cap 3, faults on: abandonment 22.5%, 0 of 60 sessions with a dead stretch, completions per session about 1.5x): real 22.1%, 0 of 5, 1.4x (122 against 89 per session). Real-stack results are in line with the model, so the rule is the default.
- **Collisions.** The rule adds traffic. Model, colliding sessions per 1000 completed tasks without / with the rule: fault-free 1.1 / 1.8 (4 of 60 sessions against 11 of 60); faults on 0.4 / 1.3 (2 against 10 of 60). So the per-task rate is roughly flat fault-free and is NOT flat with faults on. Real stack: 2 collisions in 612 completed tasks with the rule (3.3 per 1000, one session of five) against 0 in 443 without; too few events to resolve a rate difference. The mechanism the model runs without the rule pointed to (later-onset collisions 0-14 ticks after an assignment was applied to one of the two robots) is not touched by the rule; the with-rule collisions were not classified (model or real stack), so "same known class" is an inference, not a measurement.
- **Correction:** the real-stack collision counts in 10.4 (and the "releases applied" figures) came from an event list the API caps at 2,000 events, which ended near tick 1,440, so they cover only about the first 1,440 of 2,000 ticks. The sets above use the API's type filter (`TASK_STATUS_CHANGED`, `CONFLICT_DETECTED`), which is complete.
- **Verification:** pytest 307 passed / 33 subtests (no Python file changed); backend 52 passed; a fresh 270-run benchmark `raw_results.csv` SHA-256 `32d492d87ccbf3bb3c1673645fe2e25a32e0c836fcb94abd801cd184274cdb5e`, identical to the post-V6b run, 0/270 collisions. The benchmark cannot see this change: the code is in a Java service used only by `ProductController`; no file in `simulation/scenarios/`, `simulation/benchmarks/` or `simulation/runner.py` references task generation or the service (`runner.py`'s only `dropPoints` reference serializes the map for the backend push); the benchmark has no Java in the loop.
- **Still open, unchanged:** abandonment 22.1% is above the 15-20% target; the largest remaining cause is robots with no route left from accumulated avoid cells (`robot_agent/agent.py`, Tier A, not touched), then idle robots as blockers; permanent ROBOT_OFFLINE robots; SQLite locking.
- **Scope decision (2026-09-27):** this is the accepted, documented end state for the backend; no further backend or Defect-4 investigation regardless of the exact abandonment percentage.

---

## 11. "Broken down" overlay and manual "Mark as fixed" (2026-09-27; Product mode only; approved as scoped)

### 11.1 Read-only investigation: why a Java-only status flip cannot work

Probe (scratch, repo unchanged): kill a robot with ROBOT_OFFLINE at tick 5, then at tick 15 give it a fresh assignment. Findings from the code and the probe:
- ROBOT_OFFLINE sets the sensor's `offline_after_tick`; every later sensor read returns OFFLINE, which re-marks the agent OFFLINE every tick. `agent.py` never clears OFFLINE (`_apply_telemetry` only sets it). The end-of-tick status can read BLOCKED/WAITING (a REASSIGN_TASK verdict), so Java sees a flickering label.
- `ProductSession._apply_assignment` rejects an OFFLINE robot, `_apply_release` refuses a sensor-dead robot, and the robot holds one of the fault generator's `max_concurrent` slots forever.
- Variant A (Java-side re-assignment only): Python rejected it ("PR1 is OFFLINE"); the robot stayed OFFLINE at the same cell to tick 45 with its old task and destination. Variant B (clear the sensor fault and reset the agent to idle, position untouched, then assign): PR1 left OFFLINE and accepted the task on all 5 seeds tried (MOVING with a fresh path on seeds 5, 8, 21, 33; WAITING on seed 3); every one then ended waiting behind a parked idle robot in a one-wide aisle, the pre-existing parked-robot problem, not a recovery defect.
- Heartbeat is not an issue: the first healthy read resets the miss count.

### 11.2 What was implemented

- **Python (`simulation/product/` only, plus the route in `simulation/runner.py`):** `POST /control/recover` -> `TaskInbox.submit_recover/drain_recoveries` -> `ProductSession._apply_recover`. It refuses (robot untouched, SYSTEM event says why) unless the robot is fault-dead (sensor `offline_after_tick` reached, or status OFFLINE) or unknown. Otherwise it clears the sensor fault, removes the robot from `WorldFaultGenerator.active_offline_robots` (the session now keeps `self._world_faults`), and resets the agent exactly as `_apply_release` does (new shared `_reset_agent_to_idle`: IDLE, no task/destination/path, avoid-cell and wait state cleared). **The robot's position is never touched**; it stays where it stopped. `robot_agent/`, `collision_engine/` and ground-truth handling are untouched.
- **Java:** `ProductSessionService` keeps a "broken down" overlay, `brokenDownRobots` on `GET /api/product/session` (new field on `ProductSessionStatusDto`): a live robot is latched the first time the cache reports it OFFLINE (`latchBrokenDownRobots`, run each poll) and stays latched through Python's OFFLINE/BLOCKED flicker until fixed. NOT a new `RobotState.status` value, so no Tier A contract changed. Reassigning the broken robot's task reuses the existing `TaskAllocationService.handleRobotOffline` (called by `TelemetryIngestController` on every OFFLINE report); nothing new there. `POST /api/product/robot/{robotId}/fix` -> `ProductSessionService.fixRobot` -> `SimulationClient.recoverRobot` (`POST /control/recover`): 200 on success, 400 if there is no session, the robot is not this session's, or it is not broken down, 502/503 if Python fails (label kept). On success it removes the label and ignores OFFLINE reports for that robot for `RELATCH_IGNORE_TICKS = 10` ticks so a stale batch cannot re-latch it; if Python ignored the fix the robot re-latches after the window. The robot becomes selectable by the existing allocator once its telemetry reads IDLE. New events `ROBOT_BROKEN_DOWN` / `ROBOT_FIXED` (event writes are wrapped so a locked database cannot break latching or fixing).
- **Frontend:** not built here (Phase 4). The roster row "Broken down - needs attention" with a "Mark as fixed" button will be built with the Product tab, against `brokenDownRobots` and the fix endpoint above.

### 11.3 Tests and verification

- New tests: Python `simulation/tests/test_product_recover.py` (8: inbox queue; recovers a dead robot in place with position untouched; recovers a dead robot whose status shows BLOCKED; leaves a not-broken robot untouched; a future-scheduled fault is not yet a breakdown; unknown robot; two end-to-end runs showing that WITHOUT the recovery a fresh assignment is rejected and the robot stays OFFLINE, and WITH it the robot leaves OFFLINE and accepts the assignment); Java `ProductSessionServiceBrokenDownTest` (8), `ProductControllerFixTest` (3: 200, 400, 503), `SimulationClientTest` +1.
- `pytest` **315 passed / 33 subtests** (was 307); backend JUnit **64 passed** (was 52); a fresh 270-run benchmark `raw_results.csv` SHA-256 `32d492d87ccbf3bb3c1673645fe2e25a32e0c836fcb94abd801cd184274cdb5e`, **byte-identical** to the post-V6b run, 0/270 collisions, `i_parallel_aisles` 23/19/18. Confirmed by grep that nothing in `simulation/scenarios/`, `simulation/benchmarks/`, `simulation/referee.py`, `planner/`, `robot_agent/`, `collision_engine/`, `edge/` or `shared/` references the new endpoint, overlay or recover action; the only hit in `simulation/runner.py` is the `/control/recover` FastAPI route in the Product-routes block (like `/control/release`), which the benchmark (it drives `SimulationRunner` directly) never calls.
- **Real full stack (real Java + real Python, LIVE x4):**
  - *Manual ROBOT_OFFLINE injection on PR1 (idle at (1,0)):* `brokenDownRobots` contained PR1; `POST .../fix` returned 200 and a second fix returned 400 ("not broken down"); PR1 reported IDLE at the same cell; it was assigned a new task 14 ticks later; the session's own fault generator killed it again before that task finished, so the completion of THIS run was not observed. (The tick numbers in this run were offset by a stale cache tick from the previous session in the same backend process, a known limitation.)
  - *Fix-everything loop, seed 14, 2,500 ticks (fresh backend), session's own ROBOT_OFFLINE generator on, every broken-down robot fixed as soon as it showed up:* 56 fixes (all HTTP 200); 55 robots reported IDLE (the 56th was fixed within 16 ticks of the end); 55 received a new task; **19 completed that new task** (e.g. PR5 fixed at tick 107, new task at 117, COMPLETED at 134), most of the rest were abandoned by the 30-tick stall rule or broken again first; 2 collisions (ticks 2180 and 2361, not classified). This is a stress pattern: each fix frees a fault slot, so the generator killed robots 56 times instead of at most twice.
- **Limits:** the label is latched from the poll (5 per second) and Python's OFFLINE reads as OFFLINE only about a quarter of the ticks, so it can appear a second or two after the breakdown; a fixed robot stays where it died, may block an aisle, and can be killed again; `brokenDownRobots` is in memory, not persisted, and is cleared when a session starts; no frontend yet.

---

## 12. Phase 4: the PRODUCT tab (2026-09-27)

### 12.1 What was built (dashboard only, plus two small backend fixes it needed)

- **New PRODUCT tab** beside LIVE SIMULATION and BENCHMARK & PROOF (`ViewSwitcher.tsx`: `AppView` gained `'product'`; `App.tsx` renders `ProductView` for it and hides the scenario side panel there; `Header.tsx` hides the Live view's scenario run info, START/STOP and playback controls on this tab so they cannot start a scenario by accident). The Live and Benchmark views and the Presentation Mode toggle are otherwise unchanged (their components were not edited; a run of the browser check confirmed they still render).
- **Honesty banner** (`HonestyBanner.tsx`, persistent, not dismissible): live, exploratory demo mode; random seed, random tasks, random injected faults; the audited 0/270 referee-verified collisions and the 21.74% improvement (on `i_parallel_aisles`) apply only to the offline benchmark, not to this view; collisions here are still counted by the referee and shown as measured.
- **RANDOMIZE & START** (`useProductSession.ts` -> `POST /api/product/session/start` with a random seed, LIVE speed, 1x/2x/4x selector; becomes RANDOMIZE & RESTART while a session runs, stopping the old one first and retrying while Python finishes it) and STOP.
- **Live map**: the existing `WarehouseCanvas` with the real map from `GET /api/warehouse` (fetched once the first robot frame of a session arrives, because Python pushes the map at session start). Robot positions come from the existing `useLiveFeed` (`/ws/live`), reset per session. A broken-down robot is drawn with the existing OFFLINE marker.
- **Fleet roster** (`FleetRoster.tsx`): status pill per robot, position, task, destination and path length, last coordination verdict; a robot the backend has latched as broken down shows "Broken down — needs attention" with a "Mark as fixed" button wired to `POST /api/product/robot/{id}/fix`.
- **KPI strip** (`KpiStrip.tsx`): tasks completed / active / pending, abandoned, active conflicts, referee collisions (red when above zero), robots broken down. Definitions in `productDerive.ts` (active = created - completed - abandoned - pending; active conflicts = robots waiting/blocked right now whose latest coordination verdict is not CONTINUE; collisions = `CONFLICT_DETECTED` events with `collision=true`, each counted once).
- **Negotiation and event feed** (`ProductEventFeed.tsx`): same line styling as the Live view's `CommunicationFeed`, newest first, chips ALL / NEGOTIATION / TASKS / FAULTS / COLLISIONS with counts; real events only (per-tick `COMM_FLOW` and duplicate task lines are hidden).
- **Files:** `dashboard/src/types/product.ts`, `api/productApi.ts` (own small fetch helper, so the existing `api/client.ts` is untouched), `hooks/useProductSession.ts`, `components/product/{ProductView,HonestyBanner,KpiStrip,FleetRoster,ProductEventFeed,productDerive}.ts(x)`, `dashboard/tests/productDerive.test.ts`, and a `test:unit` script in `package.json`. `contracts.ts` (a Tier A mirror) is untouched; `shared/`, `robot_agent/`, `collision_engine/` and every Python file are untouched.
- **Two backend fixes the tab needed (both Product-mode only, unit-tested):** (1) starting a second session in the same backend process misbehaved: `RobotCacheService.lastTick()` never decreased, so the new session's tick-driven Java logic ran on the previous session's stale tick and generated no tasks until the new ticks caught up, and product tasks left open by the previous session kept their robots "busy". `ProductSessionService.prepareNewSession()` (called by `ProductController` before Python starts a session) now resets the robot cache and tick counter and marks leftover `task_product_*` tasks FAILED (manually created tasks are never touched). (2) Java-emitted events (`TASK_CREATED`, `ROBOT_BROKEN_DOWN`, `ROBOT_FIXED`, ...) were lost from the live feed when the SQLite history write failed ("database is locked"): `emitEvent` now logs the failed write and still broadcasts. The locking itself is unchanged.

### 12.2 Verification

- **Real end to end** (real Java backend + real Python engine + Vite dev server + headless Chrome driven over the DevTools protocol; script kept out of the repo): 23 of 23 checks passed on the final run. The checks: the existing tabs are still there; the banner names 0/270 and 21.74% as offline-benchmark only; the Live view's START/playback controls are hidden on the Product tab; RANDOMIZE & START starts a real session (status poll says running, seed shown); the roster lists the fleet from real frames; the map renders the real 20x15 map with 5 robot markers; robots visibly moved (roster positions changed within 15 s, then map marker coordinates changed); real events showed in the feed (task, negotiation, fault and system lines); the KPI strip showed completed tasks; a broken-down robot showed "Broken down — needs attention" with "Mark as fixed" and the OFFLINE ring on the map; clicking the button cleared the backend overlay, put the robot back to a normal status, added a FIXED line to the feed, and the robot was assigned a new task about 3 s later; a second RANDOMIZE & RESTART in the same backend started a fresh session (new seed, tick restarted, 14 tasks created in the first 172 ticks, no stale-tick stall); STOP stopped it; the Benchmark and Live views still rendered; no uncaught page errors. Screenshots of each step were taken and inspected.
- **Earlier runs of the same script:** the first run passed 22/22; the second passed 22/23 (the fix line was missing from the feed because the backend's history write hit "database is locked" and the event was not broadcast: fix (2) above); the header-controls check was added after the first screenshot showed the Live view's START button on the Product tab.
- **Not observed live:** a real referee collision in the UI (0 occurred in the runs, so the red collision tile was verified only by rendering the component with a collision count of 2 and checking its styles, not with a real collision); the fixed robot COMPLETING its new task in the browser run (completion after a fix was observed in the earlier 2,500-tick real-stack run, section 11).
- **Other checks:** frontend unit tests 14/14 (`npm run test:unit`), `tsc` clean, `vite build` succeeds; `pytest` **315 passed / 33 subtests** (unchanged; no Python file changed, confirmed by file modification times against the last verified benchmark run, whose `raw_results.csv` SHA-256 `32d492d8...cdb5e` therefore still stands); backend JUnit **68 passed** (was 64; +3 `ProductSessionServicePrepareTest`, +1 broadcast-despite-locked-database test).
- **Limits:** the tab has no scrubbing or history (live only); the event feed keeps the events received while the page is open (a page reload starts an empty feed, the counters and roster resume from the backend); the "broken down" label can lag the breakdown by a second or two (Java poll); one session at a time.

---

## 13. One broken-down robot at a time, and what a "stuck" robot looks like live (2026-09-27, late)

### 13.1 Breakdown cap (Product mode only; a guard/parameter, no logic change)

- `WorldFaultGenerator` (`simulation/product/world_faults.py`) gained `max_concurrent_offline: int = 1`. `try_apply_robot_offline` rejects a ROBOT_OFFLINE while that many robots are already broken down (message "max concurrent broken-down robots reached (1) - fix the broken robot first"), for auto-generated and manual injections alike; the auto generator stays silent (no "fault skipped" line) when the cap is reached. "Mark as fixed" already discards the robot from `active_offline_robots`, so a fix frees the slot. The existing cooldown and combined `max_concurrent` limits are unchanged and are still checked first.
- Tests: `simulation/tests/test_product_fault_cap.py` (5); `pytest` **320 passed / 33 subtests** (was 315). Only `world_faults.py` and the new test changed; the benchmark path does not import it (`grep` finds no other reference), so the audited benchmark hash `32d492d8...cdb5e` still stands.
- **Real full stack** (isolated second stack on ports 8081/8002 so a running demo on 8080/8001 was not disturbed; real backend, real engine): (a) a 1,197-tick session at 2x (361 s): the generator broke `PR2` at tick 8 and never a second robot; maximum broken down at once, by the backend overlay and by the engine's own sensor state, was 1 for the whole session. (b) With one robot broken, a manual second ROBOT_OFFLINE was refused with the cap message (a SYSTEM event) and the second robot kept working; after "Mark as fixed" a new breakdown was accepted again. Maximum at once over that run: 1. (Two earlier manual attempts in the same run were refused by the 15-tick cooldown instead, because the auto generator's other faults kept resetting it; the cap message appeared once the cooldown had passed.)
- **A running engine keeps the old code:** an engine started before this change has no cap until it is restarted.

### 13.2 "Robots stuck even when the aisle looks clear": matches the known avoid-cell limitation

No fix was attempted (every earlier attempt reintroduced collision risk; see section 9 and Known Bugs #11).
- **Live snapshot of the demo session the user had just stopped** (read-only, `GET /api/robots`, tick 358): `PR1` MOVING with an empty path (`pathLen 0`) and a destination; `PR2` and `PR3` WAITING with paths, in the one-wide column x=11, next to `PR4` and `PR5` parked IDLE at (11,12) and (11,14). That is the two documented signatures: an empty path from accumulated avoid cells, and robots waiting behind parked idle robots. The avoid cells themselves are not in telemetry, so they were not read on that engine.
- **Instrumented real session** (a read-only debug route added in a scratch launcher only, same engine code; 1,197 ticks): 41 stall episodes of 10 or more ticks. Signatures: empty path (no route) 21, **all 21 carrying at least one avoid cell (median 2)**; waiting on another robot 13; path present with no blocker recorded 7. Of the 40 episodes lasting 20 or more ticks, 24 carried at least one avoid cell.
- **What recovers them:** the 30-tick stall-abandon (Java) plus release (Python). Outcomes of the 41 episodes: 19 released to IDLE, 18 released and given a new task (task changed) within a poll, 4 moved again on their own, none still stuck at the end. **Time from the robot stopping to the release: median 31 ticks (range 21-40, n=19). An abandoned task's life from being handed to the robot to FAILED: 30-31 ticks in 22 of 35 cases (median 31), up to 67.** In wall-clock that is about 15 s at 1x, 8 s at 2x and 4 s at 4x per stuck episode (0.5 s / speed per tick), plus up to 0.2 s of Java poll delay. A completed task is typically short (median 7 ticks from hand-off, 90th percentile 40).
- **Cost in that session:** with one robot broken for the whole session (never fixed) the run completed 55 tasks and abandoned 36 (39.6%), above the 22.1% measured with all robots available; so a robot left broken raises abandonment.
