# Collision detection: the exact-adjacency gap — design proposal

**Status: PROPOSAL ONLY. Nothing described here has been applied.** No file under `collision_engine/`, `robot_agent/`, or any test was modified while producing this document. All measurements below were taken by grafting candidate methods onto the unmodified `ConflictDetector` class in a scratch process.

Date: 2026-09-23. Owner of the affected code: Member 3 (`collision_engine/`, Tier A).

---

## 1. The defect, in plain language

The robots decide whether two of them are about to collide by comparing the routes each one announces to its neighbours. An announced route lists the cells a robot *will* visit, never the cell it is standing on right now. When two robots stand side by side, facing each other, each about to step into the other's cell, the only two cells that matter are the two they are standing on, and neither announcement mentions its own. The software has nothing to compare, reports no danger, and the robots swap places, passing through each other. Robots facing each other with two or more empty cells between them are caught; with exactly one empty cell between them they are caught only if both robots' route timing happens to line up (it does not once one of them has been waiting); and when they are exactly adjacent, with no empty cell between them, they are never caught. That is why the nine standard scenarios never showed it: there, robots that meet face to face are stopped while still apart, or one of them is already stationary, so "adjacent, facing, both moving" never occurred. It surfaced in the Product-mode soak test, where robots are constantly handed new destinations and re-route far more often. A second, separate weakness makes it worse: a robot that is waiting keeps announcing a route whose timing has gone stale, which blinds the timing-based checks. The independent referee, which watches real positions rather than announcements, is what caught it. This is a latent defect in the core decentralized coordination system, independent of Product mode. The 0/270 benchmark result remains a true statement about the scenarios measured; it is not evidence about this situation.

## 2. Evidence (seed 57, deterministic trace)

`PR2` finishes at (5,14) and is reassigned; `PR3` is waiting at (8,14) behind it. At tick 21 `PR2` replans (correctly stamped path `[(6,14,21),(7,14,22),…]`). `PR3` receives that fresh path in the same tick but its own waiting path is still stamped `[(7,14,18),(6,14,19),(5,14,20)]`. Its SAME_CELL and CROSSING checks are keyed on tick numbers and share no tick with `PR2`'s path; its HEADON check cannot see `PR2`'s leg `(6,14)→(7,14)` because `PR2`'s current cell is not in its list. `detect()` returns `None`, `PR3` resumes, and at tick 22 the two swap `(6,14)↔(7,14)`.

Two independent causes were identified:

- **(a) Stale tick stamps on a waiting robot's own path.** A stalled robot's path is never re-stamped (`detection.py:169-171` already notes this for the occupancy case).
- **(b) Structural blindness at exact adjacency.** `_check_crossing` accepts `own_pos` / `peer_pos_raw` but never uses them; both path lists exclude each robot's current cell. Hand-built probe: adjacent face-to-face with perfectly aligned ticks returns `None` from both sides.

For contrast, `planner/centralized_baseline.py::_astar_reserved` keeps every robot's current cell in its reservation table at the current tick (the start cell is kept in the path, `:221-222`), so its swap check (`:246-248`) cannot have this hole. The two swap checks are independent implementations; there is no shared code.

## 3. Proposed change

### 3.1 What was asked, and what it does

The requested change was to use the unused `own_pos` / `peer_pos_raw` parameters in `_check_crossing`, adding each current cell as an implicit waypoint at `first_waypoint_tick - 1`. Measured (variant **V1**): it detects the adjacent swap **only when both paths are stamped on a common clock**. It does **not** detect the stale-stamp cases, and it **did not prevent the seed-57 collision** (1 collision with the cooldown, 2 without). The reason is that a tick-keyed check needs both robots' ticks to line up, and cause (a) prevents that.

The check that fixes the actual failure is the **tick-independent** `_check_headon` with each robot's current cell prepended to its coordinate list.

### 3.2 Recommended diff ("V4": current cell added, for MOVING peers only)

Both hunks below were measured together as V4. The `_check_crossing` hunk looks **droppable**: variant V4h (head-on hunk only) was indistinguishable from V4 on the measures below (same seed-57 result, same 80/90 scenario runs unchanged, same two failing tests, same 45/120 colliding soak runs; soak means differ by about 0.2 tasks per run), so the smaller change appears sufficient. It is included because it uses the parameters the request pointed at.

The change is restricted to MOVING peers on purpose. Without that restriction (variant V3) the new checks also fire against WAITING/BLOCKED/IDLE peers whose stale paths point at us; that only changes which conflict *type* is reported (SAME_CELL becomes NARROW_AISLE_HEADON, so the resolver picks YIELD instead of WAIT), fails an existing test, and changes `g_high_load`, without closing any safety gap. Stationary peers are already owned by `_check_stationary_occupancy`.

```diff
--- a/collision_engine/detection.py
+++ b/collision_engine/detection.py
@@ -85,16 +85,27 @@
             if same_cell_conflict:
                 candidates.append(same_cell_conflict)
 
+            # Current cells are added as implicit waypoints ONLY against a
+            # MOVING peer. A stationary peer (WAITING/BLOCKED/IDLE/CHARGING,
+            # or one with no path) is already handled by
+            # _check_stationary_occupancy above, and its stale path must not
+            # be paired with our current cell — that would only change which
+            # conflict TYPE is reported for it (and so which resolution
+            # action the resolver picks), not close any safety gap.
+            peer_moving = peer.get("status") not in self._STATIONARY_STATUSES
+            own_cur = own_state.position if peer_moving else None
+            peer_cur = peer.get("position") if peer_moving else None
+
             # 2. Check for CROSSING conflict (edge swap between t and t+1)
             crossing_conflict = self._check_crossing(
-                own_state.robotId, peer_id, own_wps, peer_wps, own_state.position, peer.get("position")
+                own_state.robotId, peer_id, own_wps, peer_wps, own_cur, peer_cur
             )
             if crossing_conflict:
                 candidates.append(crossing_conflict)
 
             # 3. Check for NARROW_AISLE_HEADON conflict (approaching each other along an aisle)
             headon_conflict = self._check_headon(
-                own_state.robotId, peer_id, own_wps, peer_wps
+                own_state.robotId, peer_id, own_wps, peer_wps, own_cur, peer_cur
             )
             if headon_conflict:
                 candidates.append(headon_conflict)
@@ -233,7 +244,21 @@
         own_by_tick = {t: (x, y) for (x, y, t) in own_wps}
         peer_by_tick = {t: (x, y) for (x, y, t) in peer_wps}
 
-        # Include current positions at t_start if known
+        # Include current positions at t_start if known.
+        # A robot's planned-waypoint list never contains the cell it is
+        # standing in (RobotAgent pops each waypoint on entering it), so the
+        # very first step of a swap between two ADJACENT robots has no
+        # representation in either list. Treat each robot's current cell as
+        # an implicit waypoint one tick before its first planned waypoint —
+        # the same way planner/centralized_baseline.py's reservation table
+        # already holds every robot's current cell at the current tick.
+        own_cell = self._coords_of(own_pos)
+        if own_cell is not None and own_by_tick:
+            own_by_tick.setdefault(min(own_by_tick) - 1, own_cell)
+        peer_cell = self._coords_of(peer_pos_raw)
+        if peer_cell is not None and peer_by_tick:
+            peer_by_tick.setdefault(min(peer_by_tick) - 1, peer_cell)
+
         all_ticks = sorted(set(own_by_tick.keys()) & set(peer_by_tick.keys()))
         for t in all_ticks:
             next_t = t + 1
@@ -262,11 +287,29 @@
         peer_id: str,
         own_wps: list[tuple[int, int, int]],
         peer_wps: list[tuple[int, int, int]],
+        own_pos: Position | None = None,
+        peer_pos_raw=None,
     ) -> Conflict | None:
         """Detect robots moving toward each other head-on along an aisle."""
         # Check if consecutive waypoint pairs move in opposite directions along same collinear cells
         own_coords = [(x, y) for (x, y, t) in own_wps]
         peer_coords = [(x, y) for (x, y, t) in peer_wps]
+        own_ticks = [t for (_, _, t) in own_wps]
+        peer_ticks = [t for (_, _, t) in peer_wps]
+
+        # Prepend each robot's CURRENT cell (see _check_crossing): without it
+        # the leg between two adjacent, face-to-face robots' own cells is in
+        # neither list, so the pair is invisible exactly when they touch.
+        # This check is tick-independent, so it also holds when a waiting
+        # robot's remaining path carries stale tick stamps.
+        own_cell = self._coords_of(own_pos)
+        if own_cell is not None and own_wps:
+            own_coords.insert(0, own_cell)
+            own_ticks.insert(0, own_ticks[0] - 1)
+        peer_cell = self._coords_of(peer_pos_raw)
+        if peer_cell is not None and peer_wps:
+            peer_coords.insert(0, peer_cell)
+            peer_ticks.insert(0, peer_ticks[0] - 1)
 
         for i in range(len(own_coords) - 1):
             u, v = own_coords[i], own_coords[i + 1]
@@ -274,8 +317,8 @@
                 p_u, p_v = peer_coords[j], peer_coords[j + 1]
                 # Opposite movement on the same corridor segment: u->v vs v->u
                 if u == p_v and v == p_u:
-                    t_own = own_wps[i + 1][2]
-                    t_peer = peer_wps[j + 1][2]
+                    t_own = own_ticks[i + 1]
+                    t_peer = peer_ticks[j + 1]
                     meeting_tick = max(t_own, t_peer)
                     return Conflict(
                         conflictId=f"conf_headon_{own_id}_{peer_id}_{meeting_tick}",
```

The diff is against the current working-tree `detection.py`, which already carries uncommitted changes from earlier sessions.

## 4. Which cause does the change fix?

| | (a) stale stamps on a waiting robot's path | (b) exact-adjacency blindness |
|---|---|---|
| Literal request (V1, `_check_crossing` only) | **No.** Tick-keyed; needs a shared clock | **Yes, only with aligned stamps** |
| Recommended (V4 / V4h) | **Worked around, not fixed.** The head-on check is tick-independent, so a face-to-face pair is found regardless of stamps. The waiting robot's path is still stale, and the tick-keyed SAME_CELL / CROSSING checks stay blind to it | **Yes** |

Measured on hand-built cases through the real detector (each cell shows the result from A's side / B's side; X = CROSSING, H = NARROW_AISLE_HEADON, S = SAME_CELL):

| case | current code | V1 | V4 |
|---|---|---|---|
| A1 adjacent face-to-face, aligned ticks | None / None | X / X | X / X |
| A3 adjacent face-to-face, one path stale | None / None | None / None | H / H |
| S1 seed-57 tick-21 view (waiter vs fresh mover) | None / None | None / None | H / H |
| A2 gap 3 (two empty cells between them), aligned | X / X | X / X | X / X |
| A4 gap 3 (two empty cells between them), one path stale | H / H | H / H | H / H |
| N1 adjacent, same direction | None | None | None |
| N2 adjacent, perpendicular | None | None | None |
| N4 adjacent, peer moving away | None | None | None |
| W1 adjacent, peer WAITING (A's view) | S | X | **S (unchanged)** |

**Detection by distance, measured on the unmodified detector.** Two robots on one row facing each other; "gap" is the difference between their positions, so adjacent robots have gap 1. **Gap 1: undetected from both sides**, whether or not the tick stamps line up (the exact-adjacency blindness, cause b). **Gap 2 (one empty cell between them): `SAME_CELL` only when both routes' tick stamps line up; undetected when either route is stale-stamped** (causes a and b together; this is the seed-57 tick-21 situation, case S1 above). **Gap 3 or more: detected** (`CROSSING`/`SAME_CELL` with aligned stamps, `NARROW_AISLE_HEADON` with a stale-stamped waiter), because a reversed pair then lies strictly between the two robots and appears in both routes. Cases A2 and A4 above are both gap 3; they were originally labelled "two apart" and "three apart", which was wrong.

For A4 the reported cell/tick shifts under V4 (`(7,14)@t23` becomes `(6,14)@t22` from A's side) because the pair is now found one step earlier. That is a change in an already-detected case; it affects `predictedCell`, which the resolver's rule 3 and the agent's temporary avoid-cell use.

End-to-end, seed 57 (deterministic, 60 ticks, no faults): current code 1 collision (2 with the cooldown off); V1 the same; V4 and V4h **0** in both settings.

## 5. Blast radius

**Call sites.** One production caller: `robot_agent/agent.py:161` (`self.detector.detect(...)`). `simulation/product/session.py:156` delegates to it unchanged. `_check_headon` / `_check_crossing` are private and called only from `detect()`. `simulation/diagnostics/tick_loss_profiler.py` mentions `detect()` in a docstring only.

**Existing tests that touch this path.**

- `collision_engine/tests/test_detection.py`: 10 `detect()` calls across its 10 tests (5 in `TestConflictDetector`, 5 in `TestStationaryPeerOccupancy`). `test_resolution.py` does not call the detector. `robot_agent/tests`, `simulation/tests/test_runner.py` and `test_scenarios.py` exercise it indirectly.
- Full existing suite with the change grafted in (baseline 286 passed):

| variant | result | failing tests |
|---|---|---|
| V3 (no moving-peer restriction) | 283 pass, **3 fail** | `TestStationaryPeerOccupancy::test_waiting_peer_standing_on_our_next_cell_is_detected` (expects `SAME_CELL`, gets `NARROW_AISLE_HEADON`) plus the two below |
| **V4 / V4h** | 284 pass, **2 fail** | `TestDeadlockCountReflectsRealDetector::test_deadlock_count_is_not_the_old_yield_proxy` and `::test_deadlock_count_matches_detector_activations_when_it_fires` |

The two remaining failures are not detection assertions. Both use `d_deadlock` as the scenario that must make `DeadlockDetector` fire; under the change it no longer does (0 activations), so `assertGreater(real_activations, 0)` fails. **Making them pass requires editing the tests (for example pointing them at `g_high_load`, which still fires the detector: 9 activations, unchanged), which conflicts with the standing rule that no assertion is loosened.** Changing the scenario is not loosening the assertion, but it needs explicit approval.

**Existing scenarios** (DECENTRALIZED_PROPOSED, 9 scenarios × seeds 1–10, benchmark `run_one`, every metric compared):

| variant | runs byte-identical to current code | scenarios that change |
|---|---|---|
| V3 | 70 / 90 | `d_deadlock` (12→8 ticks, deadlocks 2→0), `g_high_load` (37→33, deadlocks 9→6) |
| **V4 / V4h** | **80 / 90** | **`d_deadlock` only** (12→8 ticks, deadlocks 2→0, reroutes 2→1, idle 16→8) |

Collisions stay 0 in every scenario. `b_intersection` (11), `i_parallel_aisles` (18) and every other scenario are identical, so the Category-1 headline numbers are unaffected. STOP_AND_WAIT and CENTRALIZED_RESERVATION never call the detector (established earlier; not re-run here).

Why `d_deadlock` changes even for moving peers only: at tick 3, `R2` (WAITING at (11,9)) receives an intent from `R1` labelled `MOVING`, but `R1` has in fact just stalled and the label lags by one tick. The new check treats `R1` as a moving face-to-face peer and reports a head-on conflict where the current code reported nothing. The loser then YIELDs and replans instead of both robots waiting into a genuine deadlock. That is arguably a better outcome, but it removes the scenario's deadlock trigger.

**Things to watch**

- **Documentation claims move.** The published `d_deadlock` numbers (12 ticks, 2 deadlock activations per run) and the statement that `d_deadlock` demonstrates deadlock recovery would need re-basing; `g_high_load` remains a working demonstration.
- **Any `predictedCell` consumer.** Conflicts already detected can now report an earlier pair.
- **An OFFLINE robot's own `detect()` call.** `RobotAgent.tick()` calls the detector regardless of its own status, so a dead robot can now see more conflicts. The existing mechanisms that keep its status OFFLINE are unchanged, but this is where a surprise would come from (affects `f_task_reassignment`, and Product-mode ROBOT_OFFLINE).

## 6. What this change does NOT do

Deterministic Product-mode soak, 120 seeds × 420 ticks, faults enabled, cooldown 3, a fixed task-feeder that runs inside the tick thread (so runs differ only by detector code):

| | runs with ≥1 collision | first collision was an edge swap | first collision was same-cell | mean tasks completed / run | mean deadlock activations / run |
|---|---|---|---|---|---|
| current code | **63 / 120** | 12 | 51 | 13.1 | 113 |
| V3 | 44 / 120 | 0 | 44 | 11.9 | 104 |
| **V4** | **45 / 120** | **0** | **45** | **11.1** | **110** |
| V4h | 45 / 120 | not classified | not classified | 10.9 | 109 |

(V3 with the cooldown disabled: 47 / 120, so the change largely stands on its own; current-code-without-cooldown was not measured.)

- **It removes the edge-swap class** in this data (12 first-collisions to 0) and **cuts colliding runs by 29%**. It does **not** bring the soak to zero: 45 of 120 runs still collide.
- **Every residual first-collision is a same-cell (vertex) collision**, a class this change does not touch. The typical pair is one MOVING robot and one WAITING / BLOCKED / IDLE / OFFLINE robot; a few are MOVING/MOVING. That class has **not been diagnosed** here and needs its own investigation.
- **Total collision counts are not a reliable metric and got worse**: 1625 (current) versus 2633 (V4). A single stuck pair generates one event per tick, so a few sustained events (seeds 82, 115, 67: 396 / 380 / 365 events) dominate the sum. Seed 82 is identical before and after. Use runs-affected and first-collision type.
- **There is a throughput cost**: mean completed tasks per 420-tick run fell from 13.1 to 11.1 (about 15%).

So this change is worth making for what it closes, but it is **not sufficient to declare Product mode collision-free**, and it must not be presented as such.

## 7. Verification plan

### 7.1 New regression tests, added to `collision_engine/tests/test_detection.py` BEFORE the fix

Drafted and run against both the current code and the candidate: **4 fail on current code, all 10 pass on V4** (V3, V4 and V4h all pass all 10).

```python
class TestAdjacentFaceToFaceSwap(unittest.TestCase):
    """Two robots on ADJACENT cells, each about to step into the other's cell.

    A robot's plannedPath never contains the cell it is standing in, so the
    leg between the two robots' own cells is in neither list. These tests lock
    in that such a swap is detected, both with correctly aligned tick stamps
    and with the stale stamps a WAITING robot keeps on its remaining path
    (found in the Product-mode Phase 3 soak test, seed=57).
    """

    def setUp(self):
        self.detector = ConflictDetector()

    @staticmethod
    def _state(rid, pos, ts=21, status="MOVING"):
        return RobotState(robotId=rid, position=Position(*pos), velocity=1.0, battery=100.0, currentTaskId="t",
                          destination=None, currentPath=[], status=status, timestamp=ts)

    @staticmethod
    def _intent(rid, pos, path, ts=21, status="MOVING", priority=1):
        return {"robotId": rid, "position": {"x": pos[0], "y": pos[1], "tick": None},
                "plannedPath": [{"x": x, "y": y, "tick": t} for (x, y, t) in path],
                "status": status, "priority": priority, "timestamp": ts}

    def _detect(self, own_id, own_pos, own_path, peer_id, peer_pos, peer_path, peer_status="MOVING", ts=21):
        own_state = self._state(own_id, own_pos, ts)
        rp = RobotPath(own_id, [Position(x, y, t) for (x, y, t) in own_path], ts, 1)
        return self.detector.detect(own_state, rp, [self._intent(peer_id, peer_pos, peer_path, ts, peer_status)])

    # -- defect: must FAIL on current code, PASS after the fix --------------

    def test_adjacent_face_to_face_aligned_ticks_detected_from_both_sides(self):
        a = ((6, 14), [(7, 14, 22), (8, 14, 23), (9, 14, 24)])
        b = ((7, 14), [(6, 14, 22), (5, 14, 23), (4, 14, 24)])
        self.assertIsNotNone(self._detect("A", *a, "B", *b), "A must see the swap")
        self.assertIsNotNone(self._detect("B", *b, "A", *a), "B must see the swap")

    def test_adjacent_face_to_face_with_stale_peer_stamps_detected_from_both_sides(self):
        a = ((6, 14), [(7, 14, 22), (8, 14, 23), (9, 14, 24)])
        b = ((7, 14), [(6, 14, 19), (5, 14, 20)])          # stale: 2-3 ticks in the past
        self.assertIsNotNone(self._detect("A", *a, "B", *b))
        self.assertIsNotNone(self._detect("B", *b, "A", *a))

    def test_seed57_tick21_yielder_view_detects_incoming_headon(self):
        """PR3's exact tick-21 view: waiting at (8,14) with a path stamped 18..20,
        PR2 (fresh, correctly stamped) at (6,14) heading through PR3's path."""
        pr3 = ((8, 14), [(7, 14, 18), (6, 14, 19), (5, 14, 20)])
        pr2 = ((6, 14), [(7, 14, 22), (8, 14, 23), (9, 14, 24), (10, 14, 25)])
        conflict = self._detect("PR3", *pr3, "PR2", *pr2, ts=20)
        self.assertIsNotNone(conflict, "the yielding robot must see PR2 coming")
        self.assertCountEqual(conflict.robotIds, ["PR2", "PR3"])

    def test_seed57_tick22_winner_view_detects_face_to_face(self):
        pr2 = ((6, 14), [(7, 14, 22), (8, 14, 23), (9, 14, 24), (10, 14, 25)])
        pr3 = ((7, 14), [(6, 14, 19), (5, 14, 20)])
        self.assertIsNotNone(self._detect("PR2", *pr2, "PR3", *pr3, ts=21))

    # -- regression guards: must PASS both before and after -----------------

    def test_gap_3_face_to_face_with_aligned_stamps_still_detected_as_crossing(self):
        a = ((5, 14), [(6, 14, 22), (7, 14, 23), (8, 14, 24)])
        b = ((8, 14), [(7, 14, 22), (6, 14, 23), (5, 14, 24)])
        for own, peer in ((("A", a), ("B", b)), (("B", b), ("A", a))):
            c = self._detect(own[0], *own[1], peer[0], *peer[1])
            self.assertIsNotNone(c)
            self.assertEqual(c.type, "CROSSING")

    def test_gap_3_face_to_face_with_stale_stamps_still_detected(self):
        a = ((5, 14), [(6, 14, 22), (7, 14, 23), (8, 14, 24)])
        b = ((8, 14), [(7, 14, 18), (6, 14, 19), (5, 14, 20)])
        self.assertIsNotNone(self._detect("A", *a, "B", *b))
        self.assertIsNotNone(self._detect("B", *b, "A", *a))

    def test_adjacent_same_direction_follower_not_flagged(self):
        a = ((6, 14), [(7, 14, 22), (8, 14, 23)])
        b = ((7, 14), [(8, 14, 22), (9, 14, 23)])
        self.assertIsNone(self._detect("A", *a, "B", *b))
        self.assertIsNone(self._detect("B", *b, "A", *a))

    def test_adjacent_perpendicular_not_flagged(self):
        a = ((6, 14), [(7, 14, 22), (8, 14, 23)])
        b = ((7, 13), [(7, 12, 22), (7, 11, 23)])
        self.assertIsNone(self._detect("A", *a, "B", *b))
        self.assertIsNone(self._detect("B", *b, "A", *a))

    def test_adjacent_peer_moving_away_not_flagged(self):
        a = ((6, 14), [(7, 14, 22), (8, 14, 23)])
        b = ((7, 14), [(7, 13, 22), (7, 12, 23)])
        self.assertIsNone(self._detect("A", *a, "B", *b))

    def test_offline_peer_face_to_face_still_ignored(self):
        a = ((6, 14), [(7, 14, 22), (8, 14, 23)])
        b = ((7, 14), [(6, 14, 22)])
        self.assertIsNone(self._detect("A", *a, "B", *b, peer_status="OFFLINE"))
```

### 7.2 Gates when the change is actually applied (each is a stop condition)

1. The 10 tests are added first and shown **failing** on the unmodified code (4 failures expected: the two "must FAIL" aligned/stale tests plus the two seed-57 tests).
2. Apply the diff; the 10 tests pass.
3. Full `pytest`. Expected outcome per the prototype: everything passes **except** the two `TestDeadlockCountReflectsRealDetector` tests. Any other failure is a stop.
4. Full 270-run benchmark to a fresh `--out-dir`, diffed against the current baseline (checksum `a30616690f...7056d0` is the pre-`start_tick` baseline; the post-`start_tick` run is the immediate comparator). **Hard stops as before**: `i_parallel_aisles` DECENTRALIZED ≠ 18, `b_intersection` ≠ 9/10/11, or any collision anywhere. Expected and reported, not a stop: `d_deadlock` DECENTRALIZED 12→8 with 0 deadlock activations.
5. Deterministic 120-seed soak, before and after, reporting **runs with a collision and first-collision type** (not total events). Success for *this* change is: edge-swap first-collisions go to 0 and colliding runs drop materially. It is **not** "zero collisions".
6. `f_task_reassignment` and a Product-mode ROBOT_OFFLINE run are inspected for the own-OFFLINE `detect()` effect noted in section 5.

## 8. Decisions needed

1. **Apply V4, V4h, or neither.** I would take V4h (one hunk) since the `_check_crossing` hunk adds no measured benefit; V4 keeps the hunk you specified.
2. **The two `d_deadlock`-based tests.** Approve re-pointing them at a scenario that still fires the detector (`g_high_load`, to be confirmed on the unit-test map), or reject the change.
3. **Documentation.** `d_deadlock`'s published numbers and the deadlock-recovery evidence in CLAUDE.md, the benchmark report and the deck change; approve the re-benchmark and update.
4. **Scope.** Whether to proceed before Phase 4 given this does not zero the soak, and whether to open a separate investigation into the same-cell class (45 of 120 runs).
5. **Disclosure.** Section 1 is written to be lifted into the project's honesty-first documentation; confirm whether it should be disclosed independent of the Product-mode decision.

## 9. Known, deferred, low priority (Product mode only, not Tier A)

`simulation/product/session.py::_emit_negotiation_if_changed` records `peerRobotId: None` (and therefore no `peerPriority`) on CONTINUE verdicts, because it reads `agent._waiting_on or agent._blocked_by_peer` and CONTINUE clears both. Seen at tick 21 in the seed-57 trace. The `Conflict` object already captured by `_ObservingConflictDetector` carries the peer in `robotIds`; the fix is to take the peer from there. Cosmetic (affects the Negotiation Console's labelling, not any decision). Deferred.

## 10. Method and caveats

- Candidate methods were loaded from a scratch copy of `detection.py` and grafted onto the unmodified class by in-process monkeypatch; the repository was not changed.
- The soak harness feeds tasks and manual faults from inside the tick thread, so it is deterministic. The earlier soak numbers (2448 / 2851 collisions) came from a harness with wall-clock-dependent nondeterminism and are not comparable to the table in section 6.
- Scenario equivalence used seeds 1–10 in DECENTRALIZED_PROPOSED only, with backend pushes disabled.
- Section 6's first-collision classification uses the first referee event per run and compares consecutive-tick positions of the reported pair.
- The "inference" in the earlier trace (aligned stamps would let SAME_CELL fire for `PR3`) is a reading of `_check_same_cell`, not a measurement.
