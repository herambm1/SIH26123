# Movement guard "V6b": design review (APPLIED 2026-09-25)

**Status: APPLIED 2026-09-25, after written approval.** The diff in section 3 was applied to `robot_agent/agent.py` and the tests in section 7 were added (12 in `robot_agent/tests/test_agent.py`, 1 in `simulation/tests/test_runner.py`); results are in `docs/PRODUCT_MODE_INVESTIGATION_STATUS.md` ("V6b applied") and CLAUDE.md Known Bugs #11. **The text below is the original review as written before application** and says "proposal" and "not applied" in several places for that reason. One limitation was found only after applying it: the guard does not check the peer's status (68% of hold-ticks with faults on are for dead robots); see the status document. `robot_agent/agent.py` is Tier A: it needs explicit written approval before any edit. Same review format as `docs/COLLISION_DETECTION_ADJACENCY_GAP.md` (the V4 detector proposal). Context: `docs/PRODUCT_MODE_INVESTIGATION_STATUS.md`, section 3 (Defect 2 and its 2026-09-25 addendum), and CLAUDE.md Known Bugs #11.

## 1. What it is, in plain language

`ConflictDetector` cannot see two robots that are exactly adjacent and face to face, nor a waiting robot whose stale path stamps hide a shared next cell (Known Bugs #11). V6b does not touch detection. It adds one **physical movement check** to the agent: before a robot steps, it looks at the peers' intents it has already received this tick and refuses to step in front of a peer in either of two situations.

1. **Exact face-to-face.** A peer's reported position is my next cell AND that peer's own next waypoint is the cell I am standing on. (Both robots hold; the existing stall detector then recovers the pair, exactly as `d_deadlock` does today.)
2. **Shared next cell, loser only.** A **higher-priority** peer's reported next waypoint is my next cell. Only the loser holds, in the resolver's own priority order (higher task priority wins; ties go to the lexicographically lower robot id, as in `_should_step_aside()`).

Rule 2 deliberately uses the peer's reported **next waypoint**, not its reported position. Under a 1-tick message delay the earlier-ticking peer has already moved this tick, so its reported position is a cell behind reality while its reported next waypoint is where it actually is. That is why "check the peer's current position more" cannot close the delay cases and this rule can.

Lineage: V6 = rule 1 only; V6b = rule 1 + rule 2. Both were first measured as in-memory grafts; **every V6b number in this document was re-measured on the real patched file shown in section 3** and matches the earlier graft exactly (8/120 fault-free, 4/120 with faults, identical event, activation and task totals).

## 2. Evidence: the two original collisions, traced

Both are deterministic Product-mode replays (`PR` robots, fault-free, cooldown 3). "Vanilla" = the current agent. Decisive-tick inputs were captured from the vanilla runs and are used verbatim by the tests in section 7.

| Seed | Window | Vanilla | V6 (rule 1) | V6b (rules 1 + 2) |
|---|---|---|---|---|
| 57 | 60 ticks | 1 collision (tick 22, `PR2`/`PR3`, edge swap), 8 tasks | 0 collisions, 7 tasks | 0 collisions, 3 tasks |
| 14 | 40 ticks | 1 collision (tick 3, `PR1`/`PR4`, same cell), 8 tasks | 0 collisions, 9 tasks | 0 collisions, 9 tasks |

**Seed 57 (edge swap), tick by tick.**
- Vanilla, tick 21: `PR3` is WAITING at (8,14) with a path stamped `(7,14,18),(6,14,19),(5,14,20)` and `_waiting_on = PR2`. It hears `PR2` (priority 5, it has 1) at (6,14) with a fresh path whose first cell is (7,14). `detect()` returns `None` (no shared tick). Resume-on-clear passes (`PR2`'s reported position (6,14) is not `PR3`'s next cell (7,14)), so `PR3` steps to (7,14). Tick 22: `PR2` (6,14)->(7,14) and `PR3` (7,14)->(6,14). Referee: swap.
- V6b, tick 21: `PR3` hears the same message; **rule 2** fires (a higher-priority peer's next waypoint (7,14) is `PR3`'s next cell), so `PR3` stays at (8,14). `PR2` advances to (7,14); at tick 23 the pair is adjacent and face to face, **rule 1** holds both, and the stall detector resolves it. So this seed is fixed by rule 2 one tick before the swap could form. V6 alone (rule 1 only) also avoids the collision (0 collisions in the same window); I did not trace at which tick its rule 1 holds.
- **Cost, stated plainly:** in this 60-tick window V6b completes 3 tasks against vanilla's 8 (V6: 7). The hold plus the facing-pair stall is real; a single seed is not a throughput estimate (see section 6 for the 120-seed figure).

**Seed 14 (same cell), tick by tick.**
- Vanilla, tick 3: `PR1` (priority 5) has stepped to (10,0), heading into `PR4`'s cell (11,0). `PR4` (priority 2) is WAITING, but its `_waiting_on` names **`PR2`**, an unrelated peer from an earlier conflict, so the resume check watches the wrong robot: `PR2`'s position is not `PR4`'s next cell, resume passes, and `PR4` steps into (10,0), where `PR1` is standing. Referee: both in (10,0).
- V6b: tick 2, **rule 2** holds `PR4` (its next cell (10,0) is `PR1`'s next waypoint); tick 3, `PR1` steps to (10,0) and the pair is now face to face, **rule 1** holds `PR4` (and, symmetrically, `PR1` at tick 4). No collision in 40 ticks.
- **Side finding:** the existing resume-on-clear check (`_waiting_condition_cleared`, check 3) inspects only the peer named in `_waiting_on`. When that name is stale, it cannot see the real blocker. V6b does not change that method; its checks are independent of `_waiting_on` and run before it.

## 3. Proposed diff

Against the current working-tree `robot_agent/agent.py` (which already contains the uncommitted `start_tick=current_tick - 1` edit and pre-existing uncommitted work from earlier sessions; the hunks below touch neither). Generated with `difflib` from a scratch copy; the repository file is unchanged.

```diff
--- a/robot_agent/agent.py
+++ b/robot_agent/agent.py
@@ -79,6 +79,10 @@
         # but whose actual position still coincides with our next cell —
         # see _waiting_condition_cleared().
         self._peer_raw_positions: dict = {}
+        # First planned waypoint (x, y) per peer, rebuilt fresh every tick from
+        # this tick's received intents: {peerRobotId: (x, y)}. Used only by
+        # _peer_to_hold_for().
+        self._peer_next_cells: dict = {}
 
     def tick(self, current_tick: int) -> RobotState:
         """Execute one simulation tick for this robot.
@@ -275,6 +279,7 @@
         held: dict = {}
         self._peer_priorities = {}
         self._peer_raw_positions = {}
+        self._peer_next_cells = {}
         for peer in peer_intents or []:
             peer_id = peer.get("robotId") if isinstance(peer, dict) else None
             if not peer_id or peer_id == self.robot_id:
@@ -288,6 +293,10 @@
                 self._peer_raw_positions[peer_id] = cell
             status = peer.get("status")
             planned = peer.get("plannedPath") or []
+            if planned:
+                next_cell = self._peer_cell(planned[0])
+                if next_cell is not None:
+                    self._peer_next_cells[peer_id] = next_cell
             if status not in self._PEER_STATIONARY_STATUSES and planned:
                 continue  # peer is moving and has somewhere to go — it will vacate
             if cell is not None:
@@ -403,6 +412,55 @@
         if not any(c.x == cell.x and c.y == cell.y for c in self._temporary_avoid_cells):
             self._temporary_avoid_cells.append(Position(x=cell.x, y=cell.y))
 
+    def _peer_outranks(self, peer_id: str) -> bool:
+        """True if `peer_id` wins a priority argument against THIS robot.
+
+        Same order as ConflictResolver and _should_step_aside(): higher task
+        priority wins; ties go to the lexicographically lower robotId.
+        """
+        own_priority = int(getattr(self.state, "task_priority", 1) or 1)
+        peer_priority = int(self._peer_priorities.get(peer_id, 1))
+        if own_priority != peer_priority:
+            return peer_priority > own_priority
+        return peer_id < self.robot_id
+
+    def _peer_to_hold_for(self) -> str | None:
+        """Peer this robot must NOT step in front of this tick, or None.
+
+        Two situations, both decided from this tick's received intents only:
+
+          1. Exact face-to-face: a peer's reported position is our next cell
+             AND that peer's own next waypoint is the cell we are standing on.
+             We would swap, or one of us would step into the other. The
+             detector cannot see this pair (a robot's plannedPath never holds
+             the cell it stands on), and _peer_held_cells deliberately trusts
+             a MOVING peer to vacate.
+          2. Shared next cell: a HIGHER-priority peer's reported next waypoint
+             is our next cell. Only the loser holds, exactly as the resolver
+             would have told it to; the winner is never held by this check.
+             This uses the peer's next waypoint, not its reported position:
+             under a 1-tick message delay a peer's reported position is a
+             cell behind reality (the earlier-ticking peer has already moved
+             this tick), while its reported next waypoint is where it
+             actually is now.
+
+        Everything else (a peer merely on our next cell but leaving, a peer
+        behind us, a lower-priority peer sharing our next cell) returns None
+        and follows the existing code path unchanged.
+        """
+        if not self.state or not self.state.currentPath:
+            return None
+        next_wp = self.state.currentPath[0]
+        next_cell = (next_wp.x, next_wp.y)
+        here = (self.state.position.x, self.state.position.y)
+        for peer_id, peer_cell in self._peer_raw_positions.items():
+            if peer_cell == next_cell and self._peer_next_cells.get(peer_id) == here:
+                return peer_id
+        for peer_id, peer_next in self._peer_next_cells.items():
+            if peer_next == next_cell and self._peer_outranks(peer_id):
+                return peer_id
+        return None
+
     def _waiting_condition_cleared(self, conflict_this_tick) -> bool:
         """True if the specific reason THIS robot is WAITING has genuinely
         gone away, per this tick's own fresh information — never a bare
@@ -497,6 +555,16 @@
         SAME already-computed detection result, never a second/bypassing
         call into the detector.
         """
+        if self.state and self.state.status not in ("OFFLINE", "BLOCKED"):
+            holder = self._peer_to_hold_for()
+            if holder is not None:
+                self.state.status = "WAITING"
+                self.state.velocity = 0.0
+                self._waiting_on = holder
+                self._blocked_by_peer = holder
+                self._stall_ticks += 1
+                return
+
         if self.state and self.state.status == "WAITING" and self._waiting_condition_cleared(conflict_this_tick):
             # Resume-on-clear: fall through to the normal movement checks
             # below instead of returning early — they independently verify
```

**Is it additive? Yes, by construction, with the exceptions listed.**
- One new attribute (`_peer_next_cells`), rebuilt each tick inside a method that already walks the peer intents. Two new private methods (`_peer_outranks`, `_peer_to_hold_for`). One new block at the top of `_advance_one_cell_if_clear`. **No existing statement is changed or removed.** `_should_step_aside()`, `_waiting_condition_cleared()`, `_collect_peer_held_cells()`'s existing logic, the detector, the resolver and the deadlock detector are untouched.
- For any robot for which `_peer_to_hold_for()` returns `None`, execution is exactly the pre-existing path. **Measured, not just argued:** across 9 scenarios x 10 seeds (DECENTRALIZED_PROPOSED) the guard **never fires in 7 of the 9 scenarios**, and in `d_deadlock` (12 times) and `g_high_load` (11 times) it fires only on a robot that was **already** WAITING or already blocked by a held cell, so it restates the existing hold. All 90 runs are byte-identical on every metric (section 5).
- **What does change, precisely (the exceptions to "additive"):**
  1. Robots in situations 1 and 2 above now hold where the old code stepped. That is the point, but it includes cases where the old code was correct: with message delay 0 the `d_deadlock`-style pair at separations 5 and 6 resolved cleanly in 9 and 11 ticks and now takes 13 and 14 (one stall-detector activation instead of none), because the loser now waits while the winner passes.
  2. A guard hold **overwrites `_waiting_on`** with the holder and sets `_blocked_by_peer`, exactly as the existing stationary-peer branch already does. That feeds `_should_step_aside()` (which reads `_blocked_by_peer or _waiting_on`) and the deadlock check (`waiting_on = _waiting_on or _blocked_by_peer`), so a held robot now trips the stall detector and, if it is the lower-priority side, reroutes. That is the intended recovery path, and it is the same one `d_deadlock` uses today.
  3. A face-to-face hold applies to **both** robots, including the priority winner (the winner is only exempt from rule 2). Both then stall for the detector threshold (5 ticks) before the loser reroutes.
  4. NEGOTIATION-event labelling: `simulation/runner.py` (around line 411) and `simulation/product/session.py:580` (`_emit_negotiation_if_changed`) read `_waiting_on`/`_blocked_by_peer` to name the peer, and `simulation/diagnostics/tick_loss_profiler.py:216` reads them too. A guard hold now sets them without a resolver verdict, so those events can name a peer for a hold that no conflict object produced. Labelling only, no decision reads it. The event stream was not diffed in the equivalence runs (only metrics were).

## 4. Which cause does it fix?

| | (a) stale stamps on a waiting robot's path | (b) exact-adjacency blindness | 1-tick message staleness |
|---|---|---|---|
| V4 (detector) | Worked around: the head-on check is tick-free; the waiter's path stays stale | **Yes** | **Yes** (all delay cells except separations 2 and 3) |
| V6 (rule 1) | Not addressed | **Yes** (exact pairs) | **No** (its position test reads the stale field) |
| **V6b (rules 1 + 2)** | **Worked around** for a shared next cell against a higher-priority peer (tick-free); path stays stale | **Yes** | **Yes** (all delay cells except separation 2) |

`d_deadlock`-style geometry matrix (benchmark map, seed 1, robots at (8,9) and (8+separation,9), collisions out of 12 cells of separation 2-8 x delay 0/1): vanilla **7**, V4 **2**, V6 **3**, **V6b 1**. The one V6b cell that still collides is separation 2 with delay 1: on tick 1 neither robot has received anything (the first broadcasts are held), so no agent-side guard has any information to act on; Product mode is unlikely to produce it (sessions start with delay 0 at distinct pickup points and the Defect 3 guard refuses COMM_DELAY starts within 2 cells), but that was not proven impossible.

## 5. Blast radius

**Call sites.** One production caller: `RobotAgent.tick()` reaches the guard only through `_advance_one_cell_if_clear()` (one call site, `robot_agent/agent.py:175`). `_peer_to_hold_for` and `_peer_outranks` are private and called only from that block. `simulation/product/session.py` and `simulation/runner.py` construct `RobotAgent` unchanged.

**Existing tests that touch this path (all pass with the patch).** 29 tests were run explicitly, by name, against the patched file, 29 passed:
- `robot_agent/tests/test_agent.py::TestStationaryPeerMovementGuard` (6): `test_does_not_drive_into_stationary_peer_despite_winning_priority`, `test_does_not_drive_into_offline_peer`, `test_still_advances_when_peer_is_moving_away` (the follower/convoy guarantee the new check must not break), `test_blocked_winner_still_trips_the_deadlock_escape`, `test_lower_priority_robot_is_the_one_that_steps_aside` and `test_equal_priority_standoff_breaks_on_robot_id` (the two `_should_step_aside()` tests).
- `robot_agent/tests/test_agent.py::TestResumeOnClear` (7): `test_A_resumes_promptly_once_peer_no_longer_conflicts`, `test_B_stays_waiting_while_peer_genuinely_still_conflicts`, `test_C_genuine_deadlock_still_reaches_the_real_detector`, the three `test_D_helper_*` tests that call `_waiting_condition_cleared()` directly, and `test_E_delayed_departure_message_keeps_robot_waiting_until_it_actually_arrives`. The direct-call tests set `_peer_held_cells` by hand and never run `tick()`; they are unaffected because `_peer_next_cells` is initialised in `__init__` and the guard is consulted only from `_advance_one_cell_if_clear`.
- `robot_agent/tests/test_agent.py::TestRobotAgent` (4): basic tick, goal, waiting-on-conflict, offline.
- `simulation/tests/test_runner.py::TestDeadlockCountReflectsRealDetector` (3): includes the two tests that use `d_deadlock` as the scenario that must make the detector fire. **Unlike V4, these still pass**, because `d_deadlock` is unchanged (12 ticks, 2 activations).
- `simulation/tests/test_runner.py::TestTaskReassignment` (7) and `simulation/tests/test_scenarios.py` (2: all scenarios execute; negative control has zero collisions).
- **Full suite: 286 passed, 27 subtests, with the patch, both with and without the `start_tick` edit** (baseline 286).

**Existing scenarios** (DECENTRALIZED_PROPOSED, 9 scenarios x seeds 1-10, benchmark `run_one`, every recorded metric compared): **0 of 90 runs differ**, with the `start_tick` edit present and, separately, with it removed. Collisions stay 0. `d_deadlock` 12 ticks / 2 activations, `b_intersection` 11, `i_parallel_aisles` 18 and `g_high_load` (37 ticks / 9 activations with the edit; 28 / 4 without) are all identical to the unmodified agent. STOP_AND_WAIT and CENTRALIZED_RESERVATION do not call `RobotAgent.tick()` (established earlier; not re-run here). **Unlike V4, the audited `d_deadlock` figures, the two `d_deadlock`-based tests and the deadlock-recovery evidence in CLAUDE.md do not move.**

## 6. What this change does NOT do, and what it costs

Deterministic Product-mode soak, 120 seeds, Defect 3 guard in place, cooldown 3, in-thread task feeder:

| | Vanilla | V4 (detector) | V6 | **V6b** |
|---|---|---|---|---|
| Colliding runs, fault-free, 150 ticks | 47 | 8 | 10 | **8** |
| Colliding runs, faults on, 420 ticks | 33 | 6 | 11 | **4** |
| Tasks completed, faults on, 420 ticks | 1,427 | 1,138 (-20.3%) | 1,311 (-8.1%) | **1,250 (-12.4%)** |
| Tasks completed, fault-free, 150 ticks | 1,625 | not measured | 1,549 (-4.7%) | **1,521 (-6.4%)** |
| First-collision residual, faults on (runs whose first event was a swap, plus first same-cell event by class; 3 runs appear in both) | 12 swaps; 11 face-to-face, 8 converge, 5 stopped-MOVING | 2 converge, 4 stopped-MOVING | 9 converge, 2 stopped-MOVING | **3 converge, 1 stopped-MOVING** |
| Deadlock-detector activations, faults on | 14,818 | 15,074 | 15,139 | **14,549** |

- **It does not zero the soak.** 4 of 120 runs still collide, and the residual is exactly the two classes the state document lists as independent (stale-stamp converging paths, 3 runs; a MOVING-labelled peer that stops, 1 run). A causal test (same seed under V4, first tick of any positional difference) found seeds 9, 55 and 98 remain byte-identical and collide identically under a detector fix, so a residual of that kind survives either candidate.
- **It does not fix the Defect 3 message blackout.** It reads the same messages; on a tick where none arrive it has nothing to act on. The Product-mode COMM_DELAY guard is still needed.
- **It does not fix the start-up blind window** (separation 2, delay 1, section 4).
- **Only a 1-tick delay was tested.** Delays of 2 or more ticks, and message drop, were not.
- **Throughput cost is real: -12.4% on the soak (with the `start_tick` edit present), -6.7% without it (section 8).** It is smaller than V4's -20.3% but not small. It comes from held face-to-face pairs waiting for the stall detector and from losers holding while winners pass.
- **Every prototype number is a single deterministic run.** Per-seed task counts (seed 57: 3 versus 8) are chaotic and are not throughput estimates.

## 7. Verification plan

### 7.1 Draft regression tests for `robot_agent/tests/test_agent.py`

Drafted and run against both the unmodified agent and the patched file. **13 tests: 8 fail on the unmodified agent (5 unit, 1 scenario matrix with 6 subtests, 2 seed replays); all pass on the patched file; the other 5 are must-not-change guards that pass on both.** (The two scenario-level classes and the unit class live in one draft file; the class docstrings say which is which.)

| Test | Unmodified | Patched |
|---|---|---|
| `TestPeerHoldGuard::test_seed57_tick21_waiter_holds_for_higher_priority_peer_sharing_its_next_cell` | FAIL | pass |
| `...::test_seed57_tick22_winner_holds_when_face_to_face_with_a_moving_peer` | FAIL | pass |
| `...::test_seed14_tick3_yielder_holds_even_when_waiting_on_points_at_a_different_peer` | FAIL | pass |
| `...::test_equal_priority_tie_breaks_on_robot_id_like_the_resolver` | FAIL | pass |
| `...::test_held_pair_still_reaches_the_deadlock_escape_and_only_the_loser_reroutes` | FAIL | pass |
| `...::test_seed14_tick2_yielder_already_holds` (guard) | pass | pass |
| `...::test_higher_priority_robot_sharing_a_next_cell_is_never_held_by_this_guard` (guard) | pass | pass |
| `...::test_follower_directly_behind_a_leader_is_not_held` (guard) | pass | pass |
| `...::test_perpendicular_peer_not_sharing_a_next_cell_is_not_held` (guard) | pass | pass |
| `TestDeadlockGeometryEndToEnd::test_face_to_face_pairs_that_collided_before_are_now_collision_free` (6 cells) | FAIL (all 6) | pass |
| `...::test_d_deadlock_original_behaviour_is_preserved` (12 ticks, 2 activations, 2 reroutes, 16 idle ticks, 0 collisions) (guard) | pass | pass |
| `TestProductSeedReplays::test_seed57_edge_swap_no_longer_occurs` | FAIL | pass |
| `...::test_seed14_same_cell_collision_no_longer_occurs` | FAIL | pass |

Coverage of what was asked for: **(a)** the geometry-matrix cells that collide on vanilla (separations 3, 5, 6 with delay 1; 2, 3, 4 with delay 0); **(b)** seed 57 and seed 14 both as exact decisive-tick unit views and as end-to-end replays; **(c)** `d_deadlock`'s original behaviour, asserted as the five audited values. Separation 2 with delay 1 is deliberately excluded (section 4). The two scenario-level classes use lazy imports of `simulation.runner` / `simulation.product`; if a robot_agent test should not depend on `simulation`, they belong in `simulation/tests/test_runner.py` instead and would run unchanged.

```python
"""DRAFT regression tests for the V6b movement guard (proposed for robot_agent/tests/test_agent.py).

Class 1 (TestPeerHoldGuard): agent-level tests built from the EXACT decisive-tick inputs captured from
deterministic vanilla runs (seed 57 tick 21/22, seed 14 tick 3), plus must-not-change guards.
Class 2 (TestDeadlockGeometryEndToEnd): scenario-level, through SimulationRunner (lazy imports).
Class 3 (TestProductSeedReplays): end-to-end Product-mode seed replays (lazy imports).
"""

import unittest
from unittest import mock

from shared.python.models import Position, RobotState
from collision_engine.deadlock import DeadlockDetector
from collision_engine.detection import ConflictDetector
from collision_engine.resolution import ConflictResolver
from robot_agent.agent import RobotAgent
from robot_agent.tests.test_agent import MockPlanner, MockSensor, MockTransport


def _msg(rid, pos, status, priority, planned):
    return {
        "robotId": rid,
        "position": {"x": pos[0], "y": pos[1], "tick": None},
        "plannedPath": [{"x": x, "y": y, "tick": t} for (x, y, t) in planned],
        "status": status,
        "priority": priority,
        "battery": 100.0,
        "timestamp": 0,
    }


class TestPeerHoldGuard(unittest.TestCase):
    """A robot must not step in front of a peer it is about to meet: an exact face-to-face pair, or a
    HIGHER-priority peer whose next waypoint is our next cell. Only the movement guard changes; the
    detector and resolver are the real ones and (for these inputs) return no conflict.
    """

    def _agent(self, rid, pos, path, priority, status="MOVING", waiting_on=None, stall=0, dest=None):
        transport = MockTransport()
        agent = RobotAgent(
            robot_id=rid, planner=MockPlanner(), transport=transport, sensor=MockSensor(pos=Position(x=pos[0], y=pos[1])),
            detector=ConflictDetector(), resolver=ConflictResolver(), deadlock=DeadlockDetector(stall_threshold=5),
        )
        agent.state = RobotState(
            robotId=rid, position=Position(x=pos[0], y=pos[1]), velocity=0.0 if status == "WAITING" else 1.0, battery=100.0,
            currentTaskId="task", destination=Position(x=dest[0], y=dest[1]) if dest else Position(x=path[-1][0], y=path[-1][1]),
            currentPath=[Position(x=x, y=y, tick=t) for (x, y, t) in path], status=status, timestamp=0,
        )
        setattr(agent.state, "task_priority", priority)
        agent._waiting_on = waiting_on
        agent._stall_ticks = stall
        return agent, transport

    @staticmethod
    def _pos(state):
        return (state.position.x, state.position.y)

    # -- defects: must FAIL on the current code, PASS with the guard -----------------------------

    def test_seed57_tick21_waiter_holds_for_higher_priority_peer_sharing_its_next_cell(self):
        """PR3's exact tick-21 view. Waiting at (8,14) with a path stamped 18..20 (stale), it hears PR2
        (priority 5 vs its own 1) one cell short of the shared cell (7,14) with a fresh path. The
        detector sees no common tick and returns None; the old code resumed into (7,14), and the next
        tick PR2 and PR3 swapped cells (referee-verified)."""
        agent, transport = self._agent("PR3", (8, 14), [(7, 14, 18), (6, 14, 19), (5, 14, 20)], 1,
                                       status="WAITING", waiting_on="PR2", stall=3, dest=(5, 14))
        transport.incoming = [
            _msg("PR2", (6, 14), "MOVING", 5, [(7, 14, 22), (8, 14, 23), (9, 14, 24), (10, 14, 25), (11, 14, 26), (11, 13, 27), (11, 12, 28), (11, 11, 29)]),
            _msg("PR1", (11, 13), "MOVING", 4, [(11, 14, 22), (10, 14, 23), (9, 14, 24), (8, 14, 25), (7, 14, 26), (6, 14, 27), (5, 14, 28)]),
        ]
        state = agent.tick(21)
        self.assertEqual(self._pos(state), (8, 14), "PR3 must not step into the cell PR2 is entering")
        self.assertEqual(state.status, "WAITING")
        self.assertEqual(agent._blocked_by_peer, "PR2")

    def test_seed57_tick22_winner_holds_when_face_to_face_with_a_moving_peer(self):
        """PR2's exact tick-22 view: adjacent to PR3 at (7,14), each heading into the other's cell."""
        agent, transport = self._agent("PR2", (6, 14), [(7, 14, 22), (8, 14, 23), (9, 14, 24), (10, 14, 25), (11, 14, 26), (11, 13, 27), (11, 12, 28), (11, 11, 29)], 5, dest=(11, 11))
        transport.incoming = [_msg("PR3", (7, 14), "MOVING", 1, [(6, 14, 19), (5, 14, 20)])]
        state = agent.tick(22)
        self.assertEqual(self._pos(state), (6, 14), "an exact face-to-face pair must not swap")
        self.assertEqual(state.status, "WAITING")

    def test_seed14_tick3_yielder_holds_even_when_waiting_on_points_at_a_different_peer(self):
        """PR4's exact tick-3 view. PR1 (priority 5) has stepped to (10,0) heading into PR4's cell;
        PR4 (priority 2) is WAITING, but its `_waiting_on` still names PR2, so the resume check looked at
        the wrong peer and PR4 stepped into (10,0): both robots in one cell (referee-verified)."""
        agent, transport = self._agent("PR4", (11, 0), [(10, 0, 1), (9, 0, 2), (8, 0, 3), (7, 0, 4), (6, 0, 5), (5, 0, 6), (4, 0, 7), (3, 0, 8), (2, 0, 9), (1, 0, 10), (1, 1, 11), (1, 2, 12), (1, 3, 13), (1, 4, 14)], 2,
                                       status="WAITING", waiting_on="PR2", stall=2, dest=(1, 4))
        transport.incoming = [
            _msg("PR1", (10, 0), "MOVING", 5, [(11, 0, 4), (11, 1, 5), (11, 2, 6), (11, 3, 7), (11, 4, 8), (11, 5, 9), (11, 6, 10), (11, 7, 11), (11, 8, 12), (11, 9, 13), (11, 10, 14), (11, 11, 15), (11, 12, 16), (11, 13, 17), (11, 14, 18)]),
            _msg("PR2", (1, 1), "MOVING", 5, [(1, 0, 4)]),
        ]
        state = agent.tick(3)
        self.assertEqual(self._pos(state), (11, 0), "PR4 must not step into the cell PR1 is standing in")
        self.assertEqual(state.status, "WAITING")

    # -- guards: must PASS both before and after ------------------------------------------------
    # (test_equal_priority_... and test_held_pair_... further down are DEFECT tests: they fail on the current code)

    def test_seed14_tick2_yielder_already_holds(self):
        """PR4's exact tick-2 view (before PR1 steps adjacent): the unmodified code already held here."""
        pr4_path = [(10, 0, 1), (9, 0, 2), (8, 0, 3), (7, 0, 4), (6, 0, 5), (5, 0, 6), (4, 0, 7), (3, 0, 8), (2, 0, 9), (1, 0, 10), (1, 1, 11), (1, 2, 12), (1, 3, 13), (1, 4, 14)]
        agent, transport = self._agent("PR4", (11, 0), pr4_path, 2, status="WAITING", waiting_on="PR1", stall=1, dest=(1, 4))
        transport.incoming = [
            _msg("PR5", (17, 0), "WAITING", 2, [(16, 0, 1), (15, 0, 2), (14, 0, 3), (13, 0, 4), (12, 0, 5), (11, 0, 6), (10, 0, 7), (9, 0, 8)]),
            _msg("PR1", (9, 0), "MOVING", 5, [(10, 0, 3), (11, 0, 4), (11, 1, 5), (11, 2, 6), (11, 3, 7), (11, 4, 8)]),
            _msg("PR2", (1, 2), "MOVING", 5, [(1, 1, 3), (1, 0, 4)]),
            _msg("PR3", (9, 4), "MOVING", 5, [(8, 4, 3), (7, 4, 4), (6, 4, 5), (5, 4, 6)]),
        ]
        state = agent.tick(2)
        self.assertEqual(self._pos(state), (11, 0))
        self.assertEqual(state.status, "WAITING")

    def test_higher_priority_robot_sharing_a_next_cell_is_never_held_by_this_guard(self):
        """Only the LOSER holds. PR2 (priority 5) with PR3 (priority 1) also heading into (7,14)."""
        agent, transport = self._agent("PR2", (6, 14), [(7, 14, 22), (8, 14, 23)], 5, dest=(8, 14))
        transport.incoming = [_msg("PR3", (8, 14), "WAITING", 1, [(7, 14, 18), (6, 14, 19)])]
        self.assertEqual(self._pos(agent.tick(21)), (7, 14))

    def test_follower_directly_behind_a_leader_is_not_held(self):
        """The leader stands on our next cell but is heading away: convoys keep moving."""
        agent, transport = self._agent("PR2", (5, 0), [(6, 0, 3), (7, 0, 4)], 1, dest=(7, 0))
        transport.incoming = [_msg("PR1", (6, 0), "MOVING", 5, [(7, 0, 3), (8, 0, 4)])]
        self.assertEqual(self._pos(agent.tick(2)), (6, 0))

    def test_perpendicular_peer_not_sharing_a_next_cell_is_not_held(self):
        agent, transport = self._agent("PR2", (5, 5), [(6, 5, 3), (7, 5, 4)], 1, dest=(7, 5))
        transport.incoming = [_msg("PR1", (6, 4), "MOVING", 5, [(6, 3, 3), (6, 2, 4)])]
        self.assertEqual(self._pos(agent.tick(2)), (6, 5))

    def test_equal_priority_tie_breaks_on_robot_id_like_the_resolver(self):
        """PR3 outranks PR4 on equal priority (lexicographically lower id wins), never the reverse. The
        agent's own path is stamped stale (ticks 1-2 against the peer's 5-6) so the tick-keyed detector is
        blind and only the movement guard decides."""
        for own, peer, expected in (("PR4", "PR3", (11, 0)), ("PR3", "PR4", (10, 0))):
            agent, transport = self._agent(own, (11, 0), [(10, 0, 1), (9, 0, 2)], 3, dest=(9, 0))
            transport.incoming = [_msg(peer, (9, 0), "MOVING", 3, [(10, 0, 5), (11, 0, 6)])]
            state = agent.tick(4)
            self.assertEqual(self._pos(state), expected, f"{own} vs {peer}")

    def test_held_pair_still_reaches_the_deadlock_escape_and_only_the_loser_reroutes(self):
        """The guard must not create a livelock: a face-to-face hold keeps counting stall ticks, the real
        DeadlockDetector fires, and only the lower-priority robot steps aside."""
        results = {}
        for rid, prio, peer, peer_prio in (("PR4", 2, "PR1", 5), ("PR1", 5, "PR4", 2)):
            agent, transport = self._agent(rid, (11, 0) if rid == "PR4" else (10, 0), [(10, 0, 1)] if rid == "PR4" else [(11, 0, 1)], prio, dest=(9, 0) if rid == "PR4" else (12, 0))
            stalls = []
            for tick in range(3, 3 + 8):
                transport.incoming = [_msg(peer, (10, 0) if rid == "PR4" else (11, 0), "MOVING", peer_prio, [(11, 0, tick)] if rid == "PR4" else [(10, 0, tick)])]
                agent.tick(tick)
                stalls.append(agent._stall_ticks)
            results[rid] = (max(stalls[-3:]) < max(stalls), list(agent._temporary_avoid_cells))
        self.assertTrue(results["PR4"][0] and results["PR1"][0], f"stall never reset: {results}")
        self.assertNotEqual(results["PR4"][1], [], "the lower-priority robot must step aside")
        self.assertEqual(results["PR1"][1], [], "the higher-priority robot must hold its ground")


class TestDeadlockGeometryEndToEnd(unittest.TestCase):
    """Scenario-level: the d_deadlock pair on the benchmark map, varying robot separation and message delay."""

    @staticmethod
    def _run(separation, delay, scenario_patch=True):
        from simulation.benchmarks.benchmark import build_benchmark_warehouse_map
        import simulation.runner as runner

        real_get = runner.get_scenario

        def patched(sid, seed=42, warehouse_map=None):
            sc = real_get(sid, seed, warehouse_map=warehouse_map)
            a, b = Position(x=8, y=9), Position(x=8 + separation, y=9)
            sc.robots[0]["start"], sc.robots[0]["goal"] = a, b
            sc.robots[1]["start"], sc.robots[1]["goal"] = b, a
            sc.fault_config = {"delay_ticks": delay} if delay else {}
            return sc

        with mock.patch.object(runner, "get_scenario", patched), mock.patch.object(runner.SimulationRunner, "_push_to_backend", lambda *a, **k: None):
            r = runner.SimulationRunner(backend_url="http://127.0.0.1:1")
            return r.run("d_deadlock", mode="DECENTRALIZED_PROPOSED", seed=1, speed="BATCH", warehouse_map=build_benchmark_warehouse_map())

    def test_face_to_face_pairs_that_collided_before_are_now_collision_free(self):
        """(separation, delay) cells where the unmodified agent collides (referee-verified).
        Separation 2 with delay 1 is deliberately NOT here: with a constant 1-tick delay neither robot has
        received anything on tick 1, so no movement guard can act (start-up blind window)."""
        for separation, delay in ((3, 1), (5, 1), (6, 1), (2, 0), (3, 0), (4, 0)):
            with self.subTest(separation=separation, delay=delay):
                metric = self._run(separation, delay)
                self.assertEqual(metric.collisionCount, 0)

    def test_d_deadlock_original_behaviour_is_preserved(self):
        """d_deadlock as registered (separation 4, delay 1): identical to the audited run."""
        import simulation.runner as runner
        from simulation.benchmarks.benchmark import build_benchmark_warehouse_map

        with mock.patch.object(runner.SimulationRunner, "_push_to_backend", lambda *a, **k: None):
            r = runner.SimulationRunner(backend_url="http://127.0.0.1:1")
            m = r.run("d_deadlock", mode="DECENTRALIZED_PROPOSED", seed=1, speed="BATCH", warehouse_map=build_benchmark_warehouse_map())
        self.assertEqual(
            (m.totalCompletionTicks, m.deadlockCount, m.rerouteCount, m.idleTicksTotal, m.collisionCount),
            (12, 2, 2, 16, 0),
        )


class TestProductSeedReplays(unittest.TestCase):
    """The two collisions the Product-mode soak found, replayed end to end (fault-free, deterministic)."""

    @staticmethod
    def _replay(seed, max_ticks):
        import random
        import time

        from simulation.product import session as sess_mod
        from simulation.product.session import ProductSession

        rng = random.Random(f"soak_task_source:{seed}")
        state = {"first": True, "seen": 0, "seq": 0, "drops": None}
        with mock.patch.object(ProductSession, "_push_to_backend", lambda self, *a, **k: None), \
                mock.patch.object(sess_mod, "_REASSIGNMENT_COOLDOWN_TICKS", 3):
            s = ProductSession(backend_url="http://127.0.0.1:1")

            def assign(rid):
                state["seq"] += 1
                d = rng.choice(state["drops"])
                return {"robotId": rid, "taskId": f"x_{seed}_{state['seq']}", "dropPosition": {"x": d.x, "y": d.y}, "priority": 1 + rng.randrange(5)}

            def drain_assign():
                out = []
                if state["drops"] is None:
                    wm = next(iter(s.agents.values())).planner.warehouse_map
                    state["drops"] = list(wm.pickupPoints) + list(wm.dropPoints)
                if state["first"]:
                    state["first"] = False
                    out += [assign(rid) for rid in list(s.agents.keys())]
                for e in s.events[state["seen"]:]:
                    if e.type == "TASK_COMPLETED":
                        out.append(assign(e.payload["robotId"]))
                state["seen"] = len(s.events)
                return out

            s.task_inbox.drain_assignments = drain_assign
            s.task_inbox.drain_injections = lambda: []
            with mock.patch("simulation.product.world_faults.WorldFaultGenerator.maybe_generate", lambda self, *a, **k: None):
                s.start(seed=seed, speed="BATCH", config={"robotCount": 5, "maxTicks": max_ticks})
                while s.running:
                    time.sleep(0.005)
            return s.collision_count

    def test_seed57_edge_swap_no_longer_occurs(self):
        self.assertEqual(self._replay(57, 60), 0)

    def test_seed14_same_cell_collision_no_longer_occurs(self):
        self.assertEqual(self._replay(14, 40), 0)


if __name__ == "__main__":
    unittest.main()
```

### 7.2 Gates when the change is actually applied (each is a stop condition)

1. Add the 13 tests first and show the 8 failing on the unmodified agent.
2. Apply the diff to `robot_agent/agent.py` only; the 13 tests pass.
3. Full `pytest`: expected 286 + 13 passed, no failures anywhere (unlike V4, no existing test is expected to fail). Any failure is a stop.
4. Full 270-run benchmark to a fresh `--out-dir`, diffed against the current baseline. **Expected: byte-identical.** Hard stops as before: `i_parallel_aisles` DECENTRALIZED != 18, `b_intersection` != 9/10/11, or any collision anywhere; additionally, **any changed metric at all is a stop** (the prototype changed none of the 90 runs).
5. Deterministic 120-seed soak, before and after, reporting colliding runs, first-collision type and tasks completed. Expected: 33 to about 4 colliding, about -12% tasks.
6. A Product-mode ROBOT_OFFLINE run and the NEGOTIATION event stream are inspected for the labelling effect in section 3 (exception 4).

## 8. Interaction with Defect 1 (`start_tick`) and independence

V6b reads only peer positions and each peer's **first waypoint's (x, y)**; it never reads a tick stamp, so it neither needs nor conflicts with the `start_tick` edit. That was tested, not only argued: a 2 x 2 on the real patched file, with the `start_tick` edit emulated as absent by making the planner ignore its `start_tick` argument (validated: with it absent and no patch, the benchmark reproduces the audited `g_high_load` 28 ticks / 4 activations exactly).

| Agent | `start_tick` | Colliding, fault-free 150 | Tasks, fault-free | Colliding, faults on 420 | Tasks, faults on | Benchmark (90 runs) vs unmodified agent in the same `start_tick` state |
|---|---|---|---|---|---|---|
| unmodified | present (current repo) | 47 | 1,625 | 33 | 1,427 | (baseline) |
| unmodified | absent | 47 | 1,553 | 32 | 1,346 | (baseline) |
| **V6b** | present | **8** | **1,521** | **4** | **1,250** | 0 of 90 differ |
| **V6b** | absent | **10** | **1,447** | **4** | **1,256** | 0 of 90 differ |

- **Safety does not depend on `start_tick`:** the guard cuts collisions by the same order of magnitude in both states (fault-free 47 to 8 or 10; soak 33 or 32 to 4).
- **Throughput is not additive.** `start_tick` alone adds about +6% tasks in the soak (1,346 to 1,427). With V6b present it adds nothing in the soak (1,256 versus 1,250) and about +5% fault-free (1,447 versus 1,521). V6b's cost is -12.4% against the current repo state (1,427 to 1,250) but -6.7% against a `start_tick`-free agent (1,346 to 1,256); the combined state is -7.1% against the pre-edit baseline.
- **Consequence for the decisions.** The joint soak that was the open question has been run: no adverse interaction was found, so decision (a) (apply `start_tick`) and decision (b) (apply V6b) **can be made independently on safety grounds**. They are still linked on throughput and on the `g_high_load` figure (28 ticks / 4 activations without the edit, 37 / 9 with it, identical under V6b either way). Known Bugs #4's statement that the two are held together was written when the adjacency fix was a detector change; that coupling no longer applies to V6b.

## 9. Decisions needed

1. **Apply V6b, V6, V4, or none** (this document supports the V6b column; V4 remains documented in `docs/COLLISION_DETECTION_ADJACENCY_GAP.md`).
2. **Written approval to edit `robot_agent/agent.py`** (Tier A) with the diff in section 3 and the 13 tests in section 7.1.
3. **Placement of the two scenario-level test classes** (`robot_agent/tests/test_agent.py` with lazy imports, or `simulation/tests/test_runner.py`).
4. **Documentation.** If applied: CLAUDE.md Known Bugs #11 changes from "OPEN, UNFIXED" to a partial fix with the soak numbers above; the `d_deadlock` scoping note added on 2026-09-25 stays as it is (V6b leaves `d_deadlock` untouched); Known Bugs #4's "held together" wording is updated per section 8.
5. **Whether to accept the throughput cost** (-12.4% soak with `start_tick` present; -6.7% without) in return for 33 to 4 colliding runs.

## 10. Method and caveats

- The V6b patch was applied to a **scratch copy** of `robot_agent/agent.py` and loaded in place of `robot_agent.agent` only inside each scratch process (`sys.modules` replacement); the repository is unchanged. The diff in section 3 is that copy versus the real file. V4 and V6 numbers are from earlier in-memory grafts; V6b's were re-measured on the patched file and equal the graft's.
- The soak harness feeds tasks and faults from inside the tick thread, so runs differ only by code. Scenario equivalence used seeds 1-10, DECENTRALIZED_PROPOSED only, backend pushes disabled; only recorded metrics were compared, not the event stream.
- The guard-firing counts (section 3) are single-seed (all benchmark seeds are identical). "Already waiting" is a state observation at the time of the hold, consistent with, and confirmed by, the byte-identical metrics.
- The seed 57 / seed 14 explanations are read from the traced messages and states above; the resume check's dependence on `_waiting_on` is read from `_waiting_condition_cleared()`, and its effect on seed 14 is visible in the captured `waiting_on = PR2`.
- The claim that rule 2 still holds when the loser ticks first is reasoned (the rule depends on the winner's reported next waypoint, not on tick order), not isolated by a dedicated test; the soak mixes tick orders and gave 4 colliding runs of 120.
