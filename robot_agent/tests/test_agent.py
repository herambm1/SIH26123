"""Integration tests for RobotAgent orchestration loop.
Owner: Member 3
"""

import unittest
from unittest import mock
from shared.python.models import Position, RobotPath, RobotState, Telemetry
from collision_engine.deadlock import DeadlockDetector
from collision_engine.detection import ConflictDetector
from collision_engine.resolution import ConflictResolver
from robot_agent.agent import RobotAgent


class MockPlanner:
    def __init__(self, waypoints=None):
        self.waypoints = waypoints or [Position(x=1, y=0, tick=1), Position(x=2, y=0, tick=2)]

    def plan(self, start, goal, blocked_cells=None, avoid_intervals=None, start_tick=0):
        return RobotPath(
            robotId="R1",
            waypoints=list(self.waypoints),
            generatedAtTick=start_tick,
            version=1,
        )


class MockTransport:
    def __init__(self):
        self.broadcasted = []
        self.incoming = []

    def broadcast(self, msg):
        self.broadcasted.append(msg)

    def send(self, to, msg):
        pass

    def receive(self, robot_id):
        return list(self.incoming)


class MockSensor:
    def __init__(self, pos=None, health="OK"):
        self.pos = pos or Position(x=0, y=0)
        self.health = health

    def read(self, robot_id, current_tick):
        return Telemetry(
            robotId=robot_id,
            position=self.pos,
            battery=95.0,
            obstacleDetected=False,
            sensorHealth=self.health,
            tick=current_tick,
        )


class TestRobotAgent(unittest.TestCase):
    def setUp(self):
        self.planner = MockPlanner()
        self.transport = MockTransport()
        self.sensor = MockSensor()
        self.detector = ConflictDetector()
        self.resolver = ConflictResolver()
        self.deadlock = DeadlockDetector(stall_threshold=5)

        self.agent = RobotAgent(
            robot_id="R1",
            planner=self.planner,
            transport=self.transport,
            sensor=self.sensor,
            detector=self.detector,
            resolver=self.resolver,
            deadlock=self.deadlock,
        )

    def test_tick_advances_robot_state(self):
        self.agent.state = RobotState(
            robotId="R1",
            position=Position(x=0, y=0),
            velocity=1.0,
            battery=100.0,
            currentTaskId="task1",
            destination=Position(x=2, y=0),
            currentPath=[Position(x=1, y=0, tick=1), Position(x=2, y=0, tick=2)],
            status="MOVING",
            timestamp=0,
        )

        state = self.agent.tick(1)
        self.assertEqual(state.timestamp, 1)
        self.assertEqual(state.position.x, 1)
        self.assertEqual(state.position.y, 0)
        self.assertEqual(len(self.transport.broadcasted), 1)

    def test_tick_reaches_goal_becomes_idle(self):
        self.agent.state = RobotState(
            robotId="R1",
            position=Position(x=1, y=0),
            velocity=1.0,
            battery=100.0,
            currentTaskId="task1",
            destination=Position(x=2, y=0),
            currentPath=[Position(x=2, y=0, tick=2)],
            status="MOVING",
            timestamp=1,
        )

        state = self.agent.tick(2)
        self.assertEqual(state.position.x, 2)
        self.assertEqual(state.position.y, 0)
        self.assertEqual(state.status, "IDLE")
        self.assertEqual(state.velocity, 0.0)

    def test_tick_waiting_on_conflict(self):
        self.agent.state = RobotState(
            robotId="R1",
            position=Position(x=0, y=0),
            velocity=1.0,
            battery=100.0,
            currentTaskId="task1",
            destination=Position(x=2, y=0),
            currentPath=[Position(x=1, y=0, tick=1), Position(x=2, y=0, tick=2)],
            status="MOVING",
            timestamp=0,
        )
        setattr(self.agent.state, "task_priority", 1)

        # Peer R2 with higher priority claiming (1, 0) at tick 1
        self.transport.incoming = [
            {
                "robotId": "R2",
                "priority": 5,
                "plannedPath": [Position(x=1, y=0, tick=1)],
                "status": "MOVING",
                "timestamp": 0,
            }
        ]

        state = self.agent.tick(1)
        self.assertEqual(state.status, "WAITING")
        self.assertEqual(state.position.x, 0)  # Did not advance into contested cell
        self.assertEqual(self.agent._waiting_on, "R2")

    def test_sensor_offline_marks_robot_offline(self):
        self.sensor.health = "OFFLINE"
        self.agent.state = RobotState(
            robotId="R1",
            position=Position(x=0, y=0),
            velocity=1.0,
            battery=100.0,
            currentTaskId="task1",
            destination=Position(x=2, y=0),
            currentPath=[Position(x=1, y=0, tick=1)],
            status="MOVING",
            timestamp=0,
        )

        state = self.agent.tick(1)
        self.assertEqual(state.status, "OFFLINE")
        self.assertEqual(state.velocity, 0.0)


class TestStationaryPeerMovementGuard(unittest.TestCase):
    """Regression tests for the referee-verified collisions the benchmark
    found in d_deadlock and g_high_load.

    Detection alone is not enough: in d_deadlock the resolver correctly told
    the HIGHER-priority robot to CONTINUE, and it then drove into a peer that
    was physically parked in the contested cell. "Advance if clear" has to
    mean actually clear.
    """

    def setUp(self):
        self.planner = MockPlanner()
        self.transport = MockTransport()
        self.sensor = MockSensor(pos=Position(x=10, y=9))
        self.agent = RobotAgent(
            robot_id="R1",
            planner=self.planner,
            transport=self.transport,
            sensor=self.sensor,
            detector=ConflictDetector(),
            resolver=ConflictResolver(),
            deadlock=DeadlockDetector(stall_threshold=5),
        )
        self.agent.state = RobotState(
            robotId="R1",
            position=Position(x=10, y=9),
            velocity=1.0,
            battery=100.0,
            currentTaskId="task1",
            destination=Position(x=12, y=9),
            currentPath=[Position(x=11, y=9, tick=3), Position(x=12, y=9, tick=4)],
            status="MOVING",
            timestamp=2,
        )
        # R1 outranks R2, so the resolver will tell R1 to CONTINUE.
        setattr(self.agent.state, "task_priority", 2)

    def _waiting_peer_at(self, x, y, status="WAITING"):
        return [{
            "robotId": "R2",
            "position": {"x": x, "y": y, "tick": None},
            "plannedPath": [{"x": 10, "y": 9, "tick": 2}],  # stale, excludes its own cell
            "status": status,
            "priority": 1,
            "battery": 100.0,
            "timestamp": 2,
        }]

    def test_does_not_drive_into_stationary_peer_despite_winning_priority(self):
        self.transport.incoming = self._waiting_peer_at(11, 9)

        state = self.agent.tick(3)

        self.assertEqual((state.position.x, state.position.y), (10, 9),
                         "R1 must not enter the cell R2 is standing in")
        self.assertEqual(state.status, "WAITING")
        self.assertEqual(state.velocity, 0.0)
        self.assertEqual(self.agent._waiting_on, "R2")

    def test_does_not_drive_into_offline_peer(self):
        """A dead robot is the most immovable obstacle on the floor."""
        self.transport.incoming = self._waiting_peer_at(11, 9, status="OFFLINE")

        state = self.agent.tick(3)

        self.assertEqual((state.position.x, state.position.y), (10, 9))

    def test_still_advances_when_peer_is_moving_away(self):
        """The guard must not degrade throughput into stop-and-wait: a MOVING
        peer will vacate, so following it down a corridor stays legal."""
        self.transport.incoming = [{
            "robotId": "R2",
            "position": {"x": 11, "y": 9, "tick": None},
            "plannedPath": [{"x": 11, "y": 8, "tick": 3}],
            "status": "MOVING",
            "priority": 1,
            "timestamp": 2,
        }]

        state = self.agent.tick(3)

        self.assertEqual((state.position.x, state.position.y), (11, 9))

    def test_blocked_winner_still_trips_the_deadlock_escape(self):
        """A robot that keeps winning the priority argument but cannot move is
        stalled just the same. CONTINUE clears _waiting_on, so without
        _blocked_by_peer the deadlock detector never fired and the run
        livelocked until timeout."""
        stalls = []
        for tick in range(3, 3 + 8):
            self.transport.incoming = self._waiting_peer_at(11, 9)
            self.agent.tick(tick)
            stalls.append(self.agent._stall_ticks)

        # The escape fired: the stall counter was reset instead of climbing
        # forever. Before _blocked_by_peer existed this ran 1,2,3,4,5,6,7,8.
        self.assertLess(max(stalls[-3:]), max(stalls),
                        f"stall never reset — deadlock escape never fired: {stalls}")
        # And R1, the higher-priority robot, held its ground rather than
        # rerouting: only the lower-priority side steps aside. (Non-entry into
        # the occupied cell is asserted by the dedicated guard test above;
        # MockPlanner returns a fixed canned path after any replan, so final
        # position here reflects the mock's geometry, not the guard's.)
        self.assertEqual(self.agent._temporary_avoid_cells, [])

    def test_lower_priority_robot_is_the_one_that_steps_aside(self):
        """Both sides rerouting at once just relocates the collision — only
        the lower-priority robot may reroute out of a standoff."""
        setattr(self.agent.state, "task_priority", 1)  # now R1 is the lower one
        self.agent._blocked_by_peer = "R2"
        self.agent._peer_priorities = {"R2": 3}

        self.assertTrue(self.agent._should_step_aside())

        setattr(self.agent.state, "task_priority", 5)  # now R1 outranks R2
        self.assertFalse(self.agent._should_step_aside())

    def test_equal_priority_standoff_breaks_on_robot_id(self):
        setattr(self.agent.state, "task_priority", 2)
        self.agent._blocked_by_peer = "R0"      # lexicographically lower -> R0 holds
        self.agent._peer_priorities = {"R0": 2}
        self.assertTrue(self.agent._should_step_aside())

        self.agent._blocked_by_peer = "R9"      # lexicographically higher -> R1 holds
        self.agent._peer_priorities = {"R9": 2}
        self.assertFalse(self.agent._should_step_aside())


class TestResumeOnClear(unittest.TestCase):
    """Regression tests for Solution 1 — 'resume-on-clear'.

    Root cause: a robot that enters WAITING via a resolved conflict verdict
    (or the physical peer-occupancy guard) had no way to notice its blocker
    had moved on — _apply_action(), the only code that could clear WAITING,
    only ran when detect() found a fresh conflict. Once the peer's broadcast
    path no longer contained the contested cell, nothing looked again, and
    the robot sat idle until DeadlockDetector's stall_threshold fired a
    (usually unnecessary) forced replan/detour. This is what made
    b_intersection take ~16 ticks against STOP_AND_WAIT's ~9 for a single,
    cleanly-prioritized crossing.
    """

    def setUp(self):
        self.planner = MockPlanner()
        self.transport = MockTransport()
        self.sensor = MockSensor(pos=Position(x=0, y=0))
        self.agent = RobotAgent(
            robot_id="R1",
            planner=self.planner,
            transport=self.transport,
            sensor=self.sensor,
            detector=ConflictDetector(),
            resolver=ConflictResolver(),
            deadlock=DeadlockDetector(stall_threshold=5),
        )
        self.agent.state = RobotState(
            robotId="R1",
            position=Position(x=0, y=0),
            velocity=1.0,
            battery=100.0,
            currentTaskId="task1",
            destination=Position(x=2, y=0),
            currentPath=[Position(x=1, y=0, tick=1), Position(x=2, y=0, tick=2)],
            status="MOVING",
            timestamp=0,
        )
        setattr(self.agent.state, "task_priority", 1)  # R1 is the lower-priority side

    def _peer_claims_cell(self, x, y, tick, status="MOVING"):
        return [{
            "robotId": "R2",
            "priority": 5,
            "position": {"x": x, "y": y, "tick": None},
            "plannedPath": [{"x": x, "y": y, "tick": tick}],
            "status": status,
            "timestamp": tick - 1,
        }]

    def test_A_resumes_promptly_once_peer_no_longer_conflicts(self):
        """Peer claims (1,0) at tick 1 -> R1 correctly waits. Peer then moves
        well away and stops conflicting -> R1 must resume within the very
        next tick, not wait out DeadlockDetector's 5-tick stall_threshold."""
        self.transport.incoming = self._peer_claims_cell(1, 0, tick=1)
        state = self.agent.tick(1)
        self.assertEqual(state.status, "WAITING")
        self.assertEqual(self.agent._waiting_on, "R2")
        self.assertEqual(self.agent._stall_ticks, 1)

        # Tick 2: peer has moved far away and no longer conflicts at all.
        self.transport.incoming = [{
            "robotId": "R2",
            "priority": 5,
            "position": {"x": 8, "y": 8, "tick": None},
            "plannedPath": [{"x": 8, "y": 9, "tick": 2}],
            "status": "MOVING",
            "timestamp": 1,
        }]
        state = self.agent.tick(2)

        self.assertIsNone(self.agent._waiting_on, "must not still be waiting on a peer that has left")
        self.assertEqual((state.position.x, state.position.y), (1, 0),
                          "must actually resume moving on its original path, not just flip status")
        self.assertIn(state.status, ("MOVING", "IDLE"))
        # Never touched the stall/deadlock timeout — resumed on the very
        # next tick, not after stall_threshold=5 ticks.
        self.assertLess(self.agent._stall_ticks, 5)

    def test_B_stays_waiting_while_peer_genuinely_still_conflicts(self):
        """The peer never leaves — R1 must keep waiting, tick after tick,
        exactly as before this fix (no premature resume)."""
        for tick in range(1, 4):
            self.transport.incoming = self._peer_claims_cell(1, 0, tick=1, status="WAITING")
            state = self.agent.tick(tick)
            self.assertEqual(state.status, "WAITING")
            self.assertEqual((state.position.x, state.position.y), (0, 0))
            self.assertEqual(self.agent._waiting_on, "R2")

    def test_C_genuine_deadlock_still_reaches_the_real_detector(self):
        """A peer that never clears (mutual/genuine stall) must still trip
        DeadlockDetector's real stall-threshold recovery — resume-on-clear
        must never substitute for or suppress that path."""
        activations = {"count": 0}
        real_check = self.agent.deadlock.check

        def counting_check(robot_id, stall_ticks, waiting_on):
            fired = real_check(robot_id, stall_ticks, waiting_on)
            if fired:
                activations["count"] += 1
            return fired

        self.agent.deadlock.check = counting_check

        for tick in range(1, 8):
            self.transport.incoming = self._peer_claims_cell(1, 0, tick=1, status="WAITING")
            self.agent.tick(tick)

        self.assertGreaterEqual(activations["count"], 1,
                                 "the real DeadlockDetector must still activate for a genuine, never-clearing stall")
        # _force_yield() resets _stall_ticks — confirms the escape actually ran,
        # not that the robot silently gave up counting.
        self.assertLess(self.agent._stall_ticks, 7)

    def test_D_helper_refuses_to_clear_when_peer_still_physically_holds_next_cell(self):
        """Direct unit test of the safety property: even with no conflict
        object this tick, physical occupancy of the very next cell must
        still block a resume. This is the final safety guard, independent
        of whatever the conflict detector concluded."""
        self.agent.state.status = "WAITING"
        self.agent._waiting_on = "R2"
        self.agent._peer_held_cells = {(1, 0): "R2"}  # peer still sitting on our next cell

        self.assertFalse(self.agent._waiting_condition_cleared(conflict_this_tick=None))

    def test_D_helper_refuses_to_clear_when_a_conflict_object_is_still_present(self):
        """Even if _peer_held_cells looks clear, a non-None conflict this
        tick (e.g. a predicted future collision, not a physical occupancy)
        must still block a resume."""
        from shared.python.models import Conflict

        self.agent.state.status = "WAITING"
        self.agent._waiting_on = "R2"
        self.agent._peer_held_cells = {}
        fake_conflict = Conflict(
            conflictId="c1", robotIds=["R1", "R2"], type="SAME_CELL",
            predictedCell=Position(x=1, y=0, tick=1), predictedTick=1,
            severity="HIGH", resolutionAction=None,
        )

        self.assertFalse(self.agent._waiting_condition_cleared(conflict_this_tick=fake_conflict))

    def test_D_helper_never_clears_a_forced_yield_pending_replan(self):
        """_force_yield() deliberately clears _waiting_on to None while still
        WAITING (a replan is already pending) — resume-on-clear must not
        interfere with that separate recovery path."""
        self.agent.state.status = "WAITING"
        self.agent._waiting_on = None   # exactly what _force_yield() leaves behind
        self.agent._peer_held_cells = {}

        self.assertFalse(self.agent._waiting_condition_cleared(conflict_this_tick=None))

    def test_E_delayed_departure_message_keeps_robot_waiting_until_it_actually_arrives(self):
        """A delayed transport (MessageFaultConfig.delay_ticks) doesn't drop
        the peer's departure — it just arrives late. Until it does, this
        tick's intents still show the peer's last-known, still-blocking
        report, so resume-on-clear must not act early on stale information."""
        self.transport.incoming = self._peer_claims_cell(1, 0, tick=1, status="WAITING")
        self.agent.tick(1)
        self.assertEqual(self.agent.state.status, "WAITING")

        # Tick 2: the peer has actually moved on by now, but its update is
        # delayed — this tick still only delivers its stale, still-blocking
        # report (modeling InProcessBus's delay_ticks holding the real
        # "I've moved" message back).
        self.transport.incoming = self._peer_claims_cell(1, 0, tick=1, status="WAITING")
        state = self.agent.tick(2)
        self.assertEqual(state.status, "WAITING",
                          "must not resume on stale/delayed info that still shows a block")
        self.assertEqual((state.position.x, state.position.y), (0, 0))

        # Tick 3: the delayed "I've moved on" message finally arrives —
        # NOW it's safe to resume, and it does, on the very tick it learns.
        self.transport.incoming = [{
            "robotId": "R2", "priority": 5,
            "position": {"x": 8, "y": 8, "tick": None},
            "plannedPath": [{"x": 8, "y": 9, "tick": 3}],
            "status": "MOVING", "timestamp": 2,
        }]
        state = self.agent.tick(3)
        self.assertIsNone(self.agent._waiting_on)
        self.assertEqual((state.position.x, state.position.y), (1, 0))

        # Note on total message loss (drop, not delay): if a tick delivers
        # NO messages at all, ConflictDetector's own top-level guard
        # (`not peer_intents`) returns None regardless of what's true on
        # the ground, and _peer_held_cells is empty too — this is a
        # pre-existing characteristic of the physical safety net EVERY
        # robot's movement decision already relies on each tick (a normally
        # MOVING robot gets no extra protection against a dropped message
        # either), not a new hole this fix introduces. This fix only lets a
        # WAITING robot reach the same check a MOVING robot already trusts.


class TestPeerHoldGuard(unittest.TestCase):
    """A robot must not step in front of a peer it is about to meet: an exact face-to-face pair, or a
    HIGHER-priority peer whose next waypoint is our next cell. Only the movement guard changes; the
    detector and resolver are the real ones and (for these inputs) return no conflict.
    """

    @staticmethod
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
            self._msg("PR2", (6, 14), "MOVING", 5, [(7, 14, 22), (8, 14, 23), (9, 14, 24), (10, 14, 25), (11, 14, 26), (11, 13, 27), (11, 12, 28), (11, 11, 29)]),
            self._msg("PR1", (11, 13), "MOVING", 4, [(11, 14, 22), (10, 14, 23), (9, 14, 24), (8, 14, 25), (7, 14, 26), (6, 14, 27), (5, 14, 28)]),
        ]
        state = agent.tick(21)
        self.assertEqual(self._pos(state), (8, 14), "PR3 must not step into the cell PR2 is entering")
        self.assertEqual(state.status, "WAITING")
        self.assertEqual(agent._blocked_by_peer, "PR2")

    def test_seed57_tick22_winner_holds_when_face_to_face_with_a_moving_peer(self):
        """PR2's exact tick-22 view: adjacent to PR3 at (7,14), each heading into the other's cell."""
        agent, transport = self._agent("PR2", (6, 14), [(7, 14, 22), (8, 14, 23), (9, 14, 24), (10, 14, 25), (11, 14, 26), (11, 13, 27), (11, 12, 28), (11, 11, 29)], 5, dest=(11, 11))
        transport.incoming = [self._msg("PR3", (7, 14), "MOVING", 1, [(6, 14, 19), (5, 14, 20)])]
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
            self._msg("PR1", (10, 0), "MOVING", 5, [(11, 0, 4), (11, 1, 5), (11, 2, 6), (11, 3, 7), (11, 4, 8), (11, 5, 9), (11, 6, 10), (11, 7, 11), (11, 8, 12), (11, 9, 13), (11, 10, 14), (11, 11, 15), (11, 12, 16), (11, 13, 17), (11, 14, 18)]),
            self._msg("PR2", (1, 1), "MOVING", 5, [(1, 0, 4)]),
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
            self._msg("PR5", (17, 0), "WAITING", 2, [(16, 0, 1), (15, 0, 2), (14, 0, 3), (13, 0, 4), (12, 0, 5), (11, 0, 6), (10, 0, 7), (9, 0, 8)]),
            self._msg("PR1", (9, 0), "MOVING", 5, [(10, 0, 3), (11, 0, 4), (11, 1, 5), (11, 2, 6), (11, 3, 7), (11, 4, 8)]),
            self._msg("PR2", (1, 2), "MOVING", 5, [(1, 1, 3), (1, 0, 4)]),
            self._msg("PR3", (9, 4), "MOVING", 5, [(8, 4, 3), (7, 4, 4), (6, 4, 5), (5, 4, 6)]),
        ]
        state = agent.tick(2)
        self.assertEqual(self._pos(state), (11, 0))
        self.assertEqual(state.status, "WAITING")

    def test_higher_priority_robot_sharing_a_next_cell_is_never_held_by_this_guard(self):
        """Only the LOSER holds. PR2 (priority 5) with PR3 (priority 1) also heading into (7,14)."""
        agent, transport = self._agent("PR2", (6, 14), [(7, 14, 22), (8, 14, 23)], 5, dest=(8, 14))
        transport.incoming = [self._msg("PR3", (8, 14), "WAITING", 1, [(7, 14, 18), (6, 14, 19)])]
        self.assertEqual(self._pos(agent.tick(21)), (7, 14))

    def test_follower_directly_behind_a_leader_is_not_held(self):
        """The leader stands on our next cell but is heading away: convoys keep moving."""
        agent, transport = self._agent("PR2", (5, 0), [(6, 0, 3), (7, 0, 4)], 1, dest=(7, 0))
        transport.incoming = [self._msg("PR1", (6, 0), "MOVING", 5, [(7, 0, 3), (8, 0, 4)])]
        self.assertEqual(self._pos(agent.tick(2)), (6, 0))

    def test_perpendicular_peer_not_sharing_a_next_cell_is_not_held(self):
        agent, transport = self._agent("PR2", (5, 5), [(6, 5, 3), (7, 5, 4)], 1, dest=(7, 5))
        transport.incoming = [self._msg("PR1", (6, 4), "MOVING", 5, [(6, 3, 3), (6, 2, 4)])]
        self.assertEqual(self._pos(agent.tick(2)), (6, 5))

    def test_equal_priority_tie_breaks_on_robot_id_like_the_resolver(self):
        """PR3 outranks PR4 on equal priority (lexicographically lower id wins), never the reverse. The
        agent's own path is stamped stale (ticks 1-2 against the peer's 5-6) so the tick-keyed detector is
        blind and only the movement guard decides."""
        for own, peer, expected in (("PR4", "PR3", (11, 0)), ("PR3", "PR4", (10, 0))):
            agent, transport = self._agent(own, (11, 0), [(10, 0, 1), (9, 0, 2)], 3, dest=(9, 0))
            transport.incoming = [self._msg(peer, (9, 0), "MOVING", 3, [(10, 0, 5), (11, 0, 6)])]
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
                transport.incoming = [self._msg(peer, (10, 0) if rid == "PR4" else (11, 0), "MOVING", peer_prio, [(11, 0, tick)] if rid == "PR4" else [(10, 0, tick)])]
                agent.tick(tick)
                stalls.append(agent._stall_ticks)
            results[rid] = (max(stalls[-3:]) < max(stalls), list(agent._temporary_avoid_cells))
        self.assertTrue(results["PR4"][0] and results["PR1"][0], f"stall never reset: {results}")
        self.assertNotEqual(results["PR4"][1], [], "the lower-priority robot must step aside")
        self.assertEqual(results["PR1"][1], [], "the higher-priority robot must hold its ground")


class TestDeadlockGeometryEndToEnd(unittest.TestCase):
    """Scenario-level: the d_deadlock pair on the benchmark map, varying robot separation and message delay."""

    @staticmethod
    def _run(separation, delay):
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
