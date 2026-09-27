# Product Mode — Final State (read this first)

**Status: SNAPSHOT, documentation only. Written 2026-09-27, end of the multi-day Product-mode effort.**
This file supersedes `CLAUDE.md`'s Product-mode sections and `docs/PRODUCT_MODE_INVESTIGATION_STATUS.md`
as the single point of entry for orienting on this work. It is a state snapshot, not a narrative — for
the full evidence trail (every measurement, every rejected candidate, every scratch experiment), see
`docs/PRODUCT_MODE_INVESTIGATION_STATUS.md` (13 sections) and CLAUDE.md's Product-mode entries. Nothing
here contradicts those documents; it only compresses them.

---

## 1. What was built

A live PRODUCT tab now exists in the dashboard, alongside the existing Presentation/Explanation and
Benchmark & Proof views. Pressing RANDOMIZE & START on it runs a real, seeded session through the
actual pipeline — the same Java task lifecycle, Python `RobotAgent` coordination, real
`ConflictDetector`/`ConflictResolver`/`DeadlockDetector`, and real events that the audited benchmark
uses — not a simulation of a simulation. The tab shows a live warehouse map (robots moving in real
time), a fleet roster (status, position, task, and a "Broken down — needs attention" state with a
"Mark as fixed" button), a KPI strip (tasks completed/active/pending/abandoned, active conflicts,
referee collisions in red when nonzero, robots broken down), and a negotiation/event feed of real
coordination and task events. A persistent honesty banner states this is a live, exploratory demo mode.

**The audited 270-run benchmark (0/270 collisions, 21.74% improvement on `i_parallel_aisles`) is
completely unaffected and remains the authoritative result.** The Product tab is a separate,
exploratory, clearly-labeled live mode — its own numbers (task abandonment, its own collision counts)
must never be presented as or confused with the benchmark's audited figures.

---

## 2. Defects found and their final status

| # | Defect | Root cause | Final status | Key evidence |
|---|---|---|---|---|
| 1 | Replan tick misalignment (`start_tick`) | `RobotAgent.tick()`'s replan call never passed `start_tick`, so a replanned path's waypoints were stamped 1,2,3… instead of the real simulation clock, making `ConflictDetector`'s space-time checks compare incomparable ticks after any replan. | Written and validated, but **left as an uncommitted working-tree edit in `robot_agent/agent.py`** — never merged, never reverted. Confirmed **independent of Defect 2/V6b**: a 2×2 (with/without V6b × with/without this edit) showed the same order-of-magnitude collision reduction in both states and 0/90 benchmark scenario runs differing either way. Decided separately; this edit's own decision is still open. | Full pytest unaffected; benchmark unaffected except `g_high_load` DECENTRALIZED_PROPOSED 28→37 ticks (0 collisions either way — a measured cost, not a defect). |
| 2 | `ConflictDetector` exact-adjacency blind spot — two robots exactly adjacent, both moving, face to face never appear as a conflicting pair in either robot's own broadcast path (both lists hold only future waypoints), so `detect()` returns `None` for both and they can swap cells in one tick. | **Mitigated, not fixed at the detector.** `V6b`, an agent-level movement guard (`RobotAgent._peer_to_hold_for`), was applied instead of the detector-level candidate `V4`. V6b was chosen because it is additive (68 lines added, 0 removed), leaves the detector/resolver/`DeadlockDetector` untouched, and is **benchmark-byte-identical** (`raw_results.csv` hash unchanged with and without it) while V4 would have changed `d_deadlock`'s own numbers (8 ticks/0 activations vs. the audited 12 ticks/2 activations) and broken two tests that treat `d_deadlock` as the scenario that must make the detector fire. V6b's own known limitation: it doesn't check a peer's status, so 68% of its hold-ticks under faults are for a robot that is already dead. **CLAUDE.md scoping correction, carried forward here:** `d_deadlock`'s audited 12-tick/2-activation result is a byproduct of this same adjacency gap, not evidence of the deadlock detector recovering from a genuinely unresolvable structure — that correctness rests on separate evidence (`g_high_load`, a scratch single-file-corridor test), not on `d_deadlock` itself. | Soak (120 seeds, faults on): 33→4 colliding runs. Benchmark: byte-identical, `raw_results.csv` SHA-256 `32d492d8…cdb5e` with `start_tick` present. |
| 3 | COMM_DELAY message blackout — Product mode's own fault generator toggled the bus-wide message delay mid-run, and a robot forgot a stationary neighbour for exactly one tick when that toggle landed on the same tick as its next message. | **Fixed, applied, verified.** A guard in `simulation/product/world_faults.py` (`_adjacent_pair_exists`) refuses to start a COMM_DELAY episode while any two robots are within 2 cells — Product-mode only, ground-truth positions only, no change to `InProcessBus`/`MessageFaultConfig` or any scenario. | Soak: 63→33 colliding runs; message-blackout first collisions 34→0; the guard rejects 172 of 230 attempts (74.8%), disclosed as a real constraint on how often that fault fires. |
| 4 | `RobotAgent._temporary_avoid_cells` never expires or clears anywhere in the repository, so a robot that yields/reroutes enough times ends up with an empty planner result (no route), sits in MOVING with `currentPath == []`, and its peers treat it as a permanent wall. | **NOT fixed at the root cause — an open, documented, Tier A limitation.** Every tested detector- or agent-level fix (TTL expiry at several thresholds, revalidation against peer proximity, a "hybrid" fallback-plus-escape-hatch combining both) *increased* collisions through a second-order mechanism: freeing one stuck robot re-exposes it — and the fleet's task-completion timing it perturbs — to *other*, independent, already-known collision classes (chiefly stale-stamp converging paths). No candidate was both a genuine liveness improvement and collision-neutral under stress. This is not a partial fix awaiting tuning; it is a dead end that was investigated thoroughly and closed. | Model comparisons across TTL 5/10/20/50, reval variants, and the hybrid candidate all showed the same pattern: throughput up, collisions up, in the same soak. See `docs/PRODUCT_MODE_INVESTIGATION_STATUS.md` sections 9–10.1 for the full candidate table. |
| — | Task-backlog freeze (Java, separate from Defect 4) — `ProductSessionService` held a backlog slot per task until its robot was IDLE at the drop cell; a robot stranded by Defect 4 never freed its slot, and 3 stranded robots stopped all task generation for the rest of the session. | **Fixed, applied, verified on the real stack.** `STALL_ABANDON_TICKS = 30`: a task whose robot hasn't moved for 30 ticks is marked FAILED (freeing its slot) and Python is asked to release the robot (`POST /control/release` → `ProductSession._apply_release`, position never touched). | Real stack, 5 seeds × 2000 ticks: 392 tasks completed (was ~0 after the freeze), generation and completion continuing to the end of every session. |
| — | Occupied-drop-cell task-generation bug — the task generator picked a random drop cell even when a robot (having just finished a task) was already parked on it or another open task already targeted it, so the new task stalled until abandoned. | **Fixed, applied, is now the default.** `ProductSessionService.unoccupiedDropPoints()` excludes cells any live robot occupies or that an open task already targets (falls back to the full list only if every cell is taken). Java-only, unconditional. | Real stack, same 5 seeds: abandonment 41.1%→22.1%, gaps over 150 ticks between completions 3→0. |
| — | Robot-breakdown recovery feature — ROBOT_OFFLINE has no live recovery anywhere in the codebase (the sensor fault re-marks the agent OFFLINE every tick, and a dead robot holds its fault-generator slot forever), so a Java-only "un-break" flip could not work. | **Built, applied, verified end-to-end, including in a real browser session.** `POST /control/recover` (Python, clears the sensor fault and resets the agent to IDLE with no task/destination/path, position never touched) + `POST /api/product/robot/{id}/fix` (Java, a "broken down" overlay — not a new `RobotState.status` value) + a one-robot-at-a-time breakdown cap (`WorldFaultGenerator.max_concurrent_offline = 1`). | Headless-Chrome end-to-end run: 23/23 checks passed (session started, robots visibly moving, a broken-down robot shown and fixed from the UI, reassigned a new task). Real-stack cap check: max 1 robot broken down at once over a 1,197-tick session; a manual second breakdown refused with a SYSTEM event; a new one accepted after a fix. |

---

## 3. Current known limitations

- **Task abandonment is about 22% in a typical session** (18–26% per seed measured), above the informal 15–20% target discussed during the investigation.
- **Throughput decays over long sessions** — completions per 300-tick window fall as a session runs on, in some seeds reaching zero in a late window.
- **A low but nonzero real-stack collision rate exists under sustained load.** Measured: 2 collisions in 612 completed tasks in one 5-seed real-stack set (about 3.3 per 1,000 completed tasks, one session of five affected); in model soaks, faults-on colliding sessions ranged from 2 to 10 of 60 depending on configuration. These are not classified as a new defect class — the evidence (indirect, from model runs) points to the same pre-existing assignment-timing collision mechanism, not something this work introduced.
- **Stuck-robot episodes self-resolve within roughly 15–30 seconds of real time** via the 30-tick stall-abandon mechanism (median 31 ticks from the robot stopping to its release, at 0.5s/speed-multiplier per tick). **This is expected behavior, not a bug** — it is Defect 4's symptom being contained downstream, not fixed at the root.
- **A fixed or recovered robot stays wherever it stopped** — it is never relocated or teleported; it simply becomes eligible for a new task from its current position.
- **The Product tab has no history or scrubbing.** A page reload clears the event feed and roster view, but not the underlying session state — the backend keeps running and a fresh poll repopulates the tab.
- **The backend's SQLite file is routinely "database is locked" under telemetry load** (roughly 2–3% of poll cycles in a 2000-tick real-stack session). This is pre-existing, not caused by any Product-mode work, and was worked around (not fixed) by sending recovery/release requests before database writes and by making event broadcasts survive a failed write.

---

## 4. Verified safe

- **Benchmark hash unchanged.** `raw_results.csv` from the most recent 270-run benchmark (run after the robot-breakdown-recovery feature, the last Product-mode change made) has SHA-256 `32d492d87ccbf3bb3c1673645fe2e25a32e0c836fcb94abd801cd184274cdb5e`. This is byte-identical to every benchmark run since V6b was applied (Defect 2's mitigation) — the backlog-freeze fix, the occupied-drop-cell fix, the recover feature, and the one-robot breakdown cap each individually reproduced this exact hash. With the `start_tick` edit (Defect 1) emulated absent, the hash is `a3061669…7056d0`, identical to the original audited pre-V6b baseline. **0/270 collisions in every one of these runs.**
- **pytest: 320 passed, 33 subtests** — the final count as of this snapshot (was 286/27 before V6b; the growth since is Product-mode and breakdown-cap test additions only).
- **Backend (Java) JUnit: 68 passed** — the final count as of this snapshot (was 38 before any Product-mode work).
- **Grep-confirmed isolation:** no file under `simulation/scenarios/`, `simulation/benchmarks/`, `simulation/referee.py`, `planner/`, `robot_agent/`, `collision_engine/`, `edge/`, or `shared/` references any Product-mode file, the `/control/release` or `/control/recover` endpoints, `ProductSessionService`, the breakdown cap (`max_concurrent_offline`), or V6b's guard in any way that touches the benchmark's execution path. `simulation/runner.py`'s only Product-mode surface is the FastAPI route registrations themselves (`/control/product/*`, `/control/release`, `/control/recover`), which the benchmark — which drives `SimulationRunner` directly, no Java, no HTTP — never calls.

---

## 5. How to run and demo it

**Startup order** (each in its own terminal):
```powershell
# 1. Python engine
cd G:\SIH2026
python -m uvicorn simulation.runner:app --port 8001

# 2. Java backend, fresh database
cd G:\SIH2026\backend
Remove-Item .\sih26123.db -ErrorAction SilentlyContinue
& "C:\Program Files\Eclipse Adoptium\jdk-17.0.12.7-hotspot\bin\java.exe" -jar .\target\backend-0.0.1-SNAPSHOT.jar

# 3. Dashboard
cd G:\SIH2026\dashboard
npm run dev
```
Open `http://localhost:5173`, click the **PRODUCT** tab, set speed to 2x, click **RANDOMIZE & START**.

**Manually trigger a robot breakdown** (no UI button for this — call the API directly, in a fourth
terminal, while a session is running):
```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8080/api/product/inject `
  -ContentType "application/json" -Body '{"kind":"ROBOT_OFFLINE","robotId":"PR1"}'
```
The targeted robot's roster row shows "Broken down — needs attention" within a second or two, with a
**Mark as fixed** button.

**Recommended demo cadence:** fix the broken robot within **30–60 seconds** of breaking it — do not
leave it broken for the whole session. A robot left broken for an entire session measurably raised
abandonment (22.1%→39.6% in testing); fixing it promptly keeps the KPI strip and event feed looking
active rather than accumulating abandoned tasks and a visible dead stretch.

**One-sentence honesty framing for a judge:** the PRODUCT tab shows the real system operating under
real, randomly injected faults — task abandonment, occasional collisions, and recovery all included —
while the audited safety and speed claims (0/270 collisions, 21.74% improvement) live only in the
BENCHMARK & PROOF view and are not what this tab is measuring.

---

## 6. What was deliberately not pursued, and why

A proper fix for **Defect 4's root cause** (the never-expiring avoid-cell list) was investigated at
length — TTL expiry, peer-proximity revalidation, and a "hybrid" candidate combining a fallback route
with a rare last-resort escape hatch — and **rejected**, because no candidate was simultaneously a real
liveness improvement and collision-neutral under stress; every one of them traded a stuck robot for a
higher collision rate elsewhere in the same soak, via the same second-order scheduling-perturbation
mechanism (see Defect 4's row above).

A **Product-mode-only mitigation** (tuning the reassignment cooldown, capping concurrently active
tasks) was also tested as an alternative to touching agent-level code, and was found **ineffective
under real Java task-generation cadence** — the calmer configurations tested did not meaningfully
change abandonment and, in some cases, made dead stretches worse, because the real cadence generates
far less traffic than the harness used for earlier candidate testing.

The fix that actually worked — the task-backlog freeze and the occupied-drop-cell bug — addressed two
**different, shallower** causes than Defect 4 itself: the freeze was a Java bookkeeping problem (a
stranded robot's task never freeing its backlog slot), and the drop-cell bug was a task-generation
oversight (assigning a destination a robot was already standing on). Neither required touching the
avoid-cell mechanism, and both were verified safe on the real stack. **A future session should not
re-derive or re-attempt a Defect 4 fix without new information** — this ground has been covered.

---

## 7. Git state

- **Branch:** `develop`
- **HEAD commit:** `6d37ccfc3e06ec2ac9e8406c8f2c34cacf741d2b` (`merge: integrate edge interface`)
- **As of this snapshot:** 44 modified paths, 7 deleted paths, 73 untracked paths.
- **Nothing from this entire multi-day effort — the benchmark work, the Product-mode investigation, or
  tonight's fixes and features — has been committed.** This is per the user's explicit, standing
  instruction that git operations (commit/push/merge/rebase/reset/checkout) are never performed by
  Claude in this repository; the user controls git exclusively.
