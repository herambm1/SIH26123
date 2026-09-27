"""Integration tests for SimulationRunner and multi-mode benchmarking.
Owner: Member 3
"""

import unittest
from simulation.runner import SimulationRunner
from shared.python.models import PerformanceMetric, Position, RobotState, WarehouseMap


def _create_test_warehouse_map(width: int = 20, height: int = 20) -> WarehouseMap:
    """Isolated test fixture mock map for Member 3 runner tests."""
    obstacles = []
    for x in range(width):
        obstacles.append(Position(x=x, y=0))
        obstacles.append(Position(x=x, y=height - 1))
    for y in range(height):
        obstacles.append(Position(x=0, y=y))
        obstacles.append(Position(x=width - 1, y=y))
    for rack_x in [4, 7, 12, 15]:
        for y in range(3, 17):
            if y not in (9, 10):
                obstacles.append(Position(x=rack_x, y=y))
    return WarehouseMap(
        gridWidth=width,
        gridHeight=height,
        obstacles=obstacles,
        chokePoints=[Position(x=10, y=9)],
    )


class TestSimulationRunner(unittest.TestCase):
    def setUp(self):
        # Point to unreachable port to verify resilient offline behavior
        self.runner = SimulationRunner(backend_url="http://127.0.0.1:59999")
        self.test_map = _create_test_warehouse_map()

    def test_run_decentralized_proposed_mode(self):
        metric = self.runner.run(
            "a_normal",
            mode="DECENTRALIZED_PROPOSED",
            speed="BATCH",
            max_ticks=20,
            warehouse_map=self.test_map,
        )
        self.assertIsInstance(metric, PerformanceMetric)
        self.assertEqual(metric.scenarioId, "a_normal")
        self.assertEqual(metric.mode, "DECENTRALIZED_PROPOSED")
        self.assertEqual(metric.collisionCount, 0)
        self.assertGreater(metric.totalCompletionTicks, 0)

    def test_run_stop_and_wait_mode(self):
        metric = self.runner.run(
            "a_normal",
            mode="STOP_AND_WAIT",
            speed="BATCH",
            max_ticks=20,
            warehouse_map=self.test_map,
        )
        self.assertIsInstance(metric, PerformanceMetric)
        self.assertEqual(metric.mode, "STOP_AND_WAIT")
        self.assertEqual(metric.collisionCount, 0)

    def test_run_centralized_reservation_mode(self):
        metric = self.runner.run(
            "a_normal",
            mode="CENTRALIZED_RESERVATION",
            speed="BATCH",
            max_ticks=20,
            warehouse_map=self.test_map,
        )
        self.assertIsInstance(metric, PerformanceMetric)
        self.assertEqual(metric.mode, "CENTRALIZED_RESERVATION")
        self.assertEqual(metric.collisionCount, 0)

    def test_stop_control(self):
        self.runner.stop()
        self.assertFalse(self.runner.running)

    # ── TaskAssignment → Python integration ─────────────────────────────────

    def test_no_task_assignment_preserves_scenario_hardcoded_goal(self):
        """Regression guard: existing no-assignment scenarios must behave
        exactly as before this session's TaskAssignment wiring."""
        metric = self.runner.run(
            "a_normal",
            mode="DECENTRALIZED_PROPOSED",
            speed="BATCH",
            max_ticks=20,
            warehouse_map=self.test_map,
            task_assignments=None,
        )
        # a_normal's scenario-defined goal for R1 is (8, 2) — unchanged.
        self.assertEqual(metric.scenarioId, "a_normal")
        self.assertEqual(metric.collisionCount, 0)

    def test_task_assignment_overrides_robot_destination_and_task_id(self):
        """A Java-originated TaskAssignment (robotId, taskId, dropPosition,
        priority) must actually move the correct robot's real destination —
        not merely be accepted and ignored. Proven by inspecting the real
        telemetry batches pushed to the backend each tick (the same channel
        the dashboard/backend actually consume), not an internal shortcut."""
        assignment = [{
            "robotId": "R1",
            "taskId": "task_from_java_42",
            "pickupPosition": {"x": 3, "y": 1},
            "dropPosition": {"x": 10, "y": 15},
            "priority": 5,
        }]

        pushed_batches: list[list[dict]] = []
        original = SimulationRunner._push_to_backend

        def _spy(self_, endpoint, data):
            if endpoint == "/api/telemetry/batch":
                pushed_batches.append(data)
            original(self_, endpoint, data)

        SimulationRunner._push_to_backend = _spy
        try:
            metric = self.runner.run(
                "a_normal",
                mode="DECENTRALIZED_PROPOSED",
                speed="BATCH",
                max_ticks=40,
                warehouse_map=self.test_map,
                task_assignments=assignment,
            )
        finally:
            SimulationRunner._push_to_backend = original

        self.assertEqual(metric.collisionCount, 0)
        last_batch = pushed_batches[-1]
        r1_state = next(s for s in last_batch if s["robotId"] == "R1")
        # R1's real destination (as pushed in its actual RobotState telemetry)
        # must reflect the assigned dropPosition (10, 15), not a_normal's
        # hardcoded goal (8, 2) — and its currentTaskId must be the assigned one.
        self.assertEqual((r1_state["destination"]["x"], r1_state["destination"]["y"]), (10, 15))
        r1_first_state = next(s for s in pushed_batches[0] if s["robotId"] == "R1")
        self.assertEqual(r1_first_state["currentTaskId"], "task_from_java_42")

    def test_task_assignment_for_unknown_robot_is_ignored_safely(self):
        """An assignment for a robotId that isn't in the scenario must not
        crash the run — it's simply unmatched."""
        assignment = [{"robotId": "R99", "taskId": "t1", "dropPosition": {"x": 5, "y": 5}, "priority": 1}]
        metric = self.runner.run(
            "a_normal", mode="DECENTRALIZED_PROPOSED", speed="BATCH",
            max_ticks=20, warehouse_map=self.test_map, task_assignments=assignment,
        )
        self.assertEqual(metric.scenarioId, "a_normal")

    # ── WarehouseMap → Backend push ─────────────────────────────────────────

    def test_run_pushes_the_actual_scenario_warehouse_map_to_backend(self):
        """The map pushed to /api/warehouse must be the real map this run
        executes against (self.test_map), not fabricated/duplicate data."""
        pushed: list[tuple] = []
        original = SimulationRunner._push_to_backend

        def _spy(self_, endpoint, data):
            pushed.append((endpoint, data))
            original(self_, endpoint, data)

        SimulationRunner._push_to_backend = _spy
        try:
            self.runner.run(
                "a_normal", mode="DECENTRALIZED_PROPOSED", speed="BATCH",
                max_ticks=5, warehouse_map=self.test_map,
            )
        finally:
            SimulationRunner._push_to_backend = original

        warehouse_pushes = [d for (ep, d) in pushed if ep == "/api/warehouse"]
        self.assertEqual(len(warehouse_pushes), 1)
        self.assertEqual(warehouse_pushes[0]["gridWidth"], self.test_map.gridWidth)
        self.assertEqual(warehouse_pushes[0]["gridHeight"], self.test_map.gridHeight)
        self.assertEqual(len(warehouse_pushes[0]["obstacles"]), len(self.test_map.obstacles))


class TestDeadlockCountReflectsRealDetector(unittest.TestCase):
    """PerformanceMetric.deadlockCount must equal the number of genuine
    DeadlockDetector.check() activations.

    It previously did not: the count was inferred from the ConflictResolver's
    YIELD action plus a stall threshold, and _force_yield() zeroes _stall_ticks
    the moment the real detector fires — so a real activation was unobservable
    and d_deadlock reported 0 while the detector had fired twice.
    """

    def setUp(self):
        self.runner = SimulationRunner(backend_url="http://127.0.0.1:59999")
        self.test_map = _create_test_warehouse_map()

    def _run_counting_real_activations(self, scenario_id, mode="DECENTRALIZED_PROPOSED", max_ticks=50):
        """Run a scenario while independently counting real detector firings."""
        from collision_engine.deadlock import DeadlockDetector

        original_check = DeadlockDetector.check
        fired = {"count": 0}

        def counting_check(inner_self, robot_id, stall_ticks, waiting_on):
            result = original_check(inner_self, robot_id, stall_ticks, waiting_on)
            if result:
                fired["count"] += 1
            return result

        DeadlockDetector.check = counting_check
        try:
            metric = self.runner.run(
                scenario_id, mode=mode, speed="BATCH",
                max_ticks=max_ticks, warehouse_map=self.test_map,
            )
        finally:
            DeadlockDetector.check = original_check
        return metric, fired["count"]

    def test_deadlock_count_matches_detector_activations_when_it_fires(self):
        metric, real_activations = self._run_counting_real_activations("d_deadlock")
        self.assertGreater(real_activations, 0,
                           "d_deadlock should genuinely trigger the deadlock detector")
        self.assertEqual(metric.deadlockCount, real_activations)

    def test_deadlock_count_is_zero_when_detector_never_fires(self):
        metric, real_activations = self._run_counting_real_activations("a_normal", max_ticks=20)
        self.assertEqual(real_activations, 0)
        self.assertEqual(metric.deadlockCount, 0)

    def test_deadlock_count_is_not_the_old_yield_proxy(self):
        """Guard against regressing to the resolver-action heuristic: the metric
        must track the detector, so a scenario that fires it reports non-zero."""
        metric, _ = self._run_counting_real_activations("d_deadlock")
        self.assertGreater(metric.deadlockCount, 0)


class TestDeadlockScenarioInvariance(unittest.TestCase):
    """d_deadlock's audited behaviour must not move when the agent's physical
    movement guard changes. The peer-hold guard (face-to-face pair, or a
    higher-priority peer whose next waypoint is our next cell) only ever fires
    in this scenario on a robot that is ALREADY waiting, so every metric of the
    audited run must be identical: 12 ticks, 2 real detector activations,
    2 reroutes, 16 idle robot-ticks, 0 collisions."""

    def test_d_deadlock_metrics_are_identical_to_the_audited_run(self):
        runner = SimulationRunner(backend_url="http://127.0.0.1:59999")
        metric = runner.run(
            "d_deadlock", mode="DECENTRALIZED_PROPOSED", seed=1, speed="BATCH",
            warehouse_map=_create_test_warehouse_map(),
        )
        self.assertEqual(
            (metric.totalCompletionTicks, metric.deadlockCount, metric.rerouteCount,
             metric.idleTicksTotal, metric.collisionCount),
            (12, 2, 2, 16, 0),
        )


class TestSeedPropagation(unittest.TestCase):
    """The run's seed must reach every existing randomness source. No new
    randomness is introduced — these three RNGs already existed and were simply
    left unseeded (InProcessBus, SimulationSensorSource) or hardcoded to 42
    (centralized planning order)."""

    def setUp(self):
        self.runner = SimulationRunner(backend_url="http://127.0.0.1:59999")
        self.test_map = _create_test_warehouse_map()

    def test_seed_reaches_centralized_planner(self):
        """plan_centralized() must receive the run's seed, not a hardcoded 42."""
        import planner.centralized_baseline as cb

        original = cb.plan_centralized
        seen_seeds = []

        def spy(start_goals, warehouse_map, seed):
            seen_seeds.append(seed)
            return original(start_goals, warehouse_map, seed)

        cb.plan_centralized = spy
        try:
            self.runner.run("b_intersection", mode="CENTRALIZED_RESERVATION", seed=1234,
                            speed="BATCH", max_ticks=20, warehouse_map=self.test_map)
        finally:
            cb.plan_centralized = original

        self.assertEqual(seen_seeds, [1234])

    def test_seed_reaches_in_process_bus(self):
        """InProcessBus must be constructed with an RNG derived from the seed."""
        import simulation.runner as runner_module

        original = runner_module.InProcessBus
        captured = {}

        def spy(robot_ids, fault_config=None, *, rng=None):
            captured["rng"] = rng
            return original(robot_ids, fault_config=fault_config, rng=rng)

        runner_module.InProcessBus = spy
        try:
            self.runner.run("a_normal", mode="DECENTRALIZED_PROPOSED", seed=99,
                            speed="BATCH", max_ticks=10, warehouse_map=self.test_map)
        finally:
            runner_module.InProcessBus = original

        self.assertIsNotNone(captured.get("rng"), "InProcessBus was constructed without a seeded rng")
        # Same seed must produce the same stream.
        import random
        self.assertEqual(captured["rng"].random(), random.Random(99).random())

    def test_seed_reaches_sensor_sources(self):
        """Every SimulationSensorSource must get a seed-derived, per-robot RNG."""
        import simulation.runner as runner_module

        original = runner_module.SimulationSensorSource
        rngs = []

        def spy(ground_truth, fault_config=None, **kwargs):
            rngs.append(kwargs.get("rng"))
            return original(ground_truth, fault_config, **kwargs)

        runner_module.SimulationSensorSource = spy
        try:
            self.runner.run("a_normal", mode="DECENTRALIZED_PROPOSED", seed=99,
                            speed="BATCH", max_ticks=10, warehouse_map=self.test_map)
        finally:
            runner_module.SimulationSensorSource = original

        self.assertEqual(len(rngs), 2)  # one per robot in a_normal
        self.assertTrue(all(r is not None for r in rngs),
                        "a sensor source was constructed without a seeded rng")
        # Per-robot streams must differ, or every robot would share noise.
        self.assertNotEqual(rngs[0].random(), rngs[1].random())

    def test_same_seed_is_reproducible_across_runs(self):
        """Reproducibility must survive seed propagation."""
        a = self.runner.run("g_high_load", mode="CENTRALIZED_RESERVATION", seed=5,
                            speed="BATCH", max_ticks=60, warehouse_map=self.test_map)
        b = SimulationRunner(backend_url="http://127.0.0.1:59999").run(
            "g_high_load", mode="CENTRALIZED_RESERVATION", seed=5,
            speed="BATCH", max_ticks=60, warehouse_map=self.test_map)
        self.assertEqual(a.totalCompletionTicks, b.totalCompletionTicks)
        self.assertEqual(a.collisionCount, b.collisionCount)


class TestCentralizedSchedulerFallbackSafety(unittest.TestCase):
    """A genuine plan_centralized() planning failure must propagate, not be
    silently swallowed into the weaker vertex-only fallback table in
    _build_centralized_schedules(). That fallback has no edge/swap-conflict
    protection (only plan_centralized's _astar_reserved() does — see Known
    Bugs #5 in CLAUDE.md), so silently substituting it for a real planning
    failure would mean a CENTRALIZED_RESERVATION run could report success
    while actually being collision-unsafe by construction (Known Bugs #9).
    """

    def setUp(self):
        self.runner = SimulationRunner(backend_url="http://127.0.0.1:59999")
        self.test_map = _create_test_warehouse_map()

    def test_planning_failed_error_propagates_not_swallowed(self):
        import planner.centralized_baseline as cb
        from planner.astar import PlanningFailedError

        original = cb.plan_centralized

        def raiser(start_goals, warehouse_map, seed):
            raise PlanningFailedError(
                Position(x=0, y=0), Position(x=1, y=1), "synthetic failure for test"
            )

        cb.plan_centralized = raiser
        try:
            with self.assertRaises(PlanningFailedError):
                self.runner.run(
                    "a_normal", mode="CENTRALIZED_RESERVATION", seed=1,
                    speed="BATCH", max_ticks=20, warehouse_map=self.test_map,
                )
        finally:
            cb.plan_centralized = original

    def test_invalid_map_error_propagates_not_swallowed(self):
        import planner.centralized_baseline as cb
        from planner.warehouse_map import InvalidMapError

        original = cb.plan_centralized

        def raiser(start_goals, warehouse_map, seed):
            raise InvalidMapError("synthetic invalid map for test")

        cb.plan_centralized = raiser
        try:
            with self.assertRaises(InvalidMapError):
                self.runner.run(
                    "a_normal", mode="CENTRALIZED_RESERVATION", seed=1,
                    speed="BATCH", max_ticks=20, warehouse_map=self.test_map,
                )
        finally:
            cb.plan_centralized = original

    def test_import_error_still_takes_the_documented_fallback(self):
        """The fallback path is only for plan_centralized being unimportable,
        not for it raising a planning-domain error — that distinction is the
        whole point of the fix, so confirm the ImportError path still works."""
        import simulation.runner as runner_module

        # Force the `from planner.centralized_baseline import plan_centralized`
        # inside _build_centralized_schedules to raise ImportError by making
        # the module temporarily unimportable.
        import sys
        original_module = sys.modules.get("planner.centralized_baseline")
        sys.modules["planner.centralized_baseline"] = None  # None sentinel -> ImportError
        try:
            metric = self.runner.run(
                "a_normal", mode="CENTRALIZED_RESERVATION", seed=1,
                speed="BATCH", max_ticks=20, warehouse_map=self.test_map,
            )
            self.assertIsInstance(metric, PerformanceMetric)
        finally:
            if original_module is not None:
                sys.modules["planner.centralized_baseline"] = original_module
            else:
                del sys.modules["planner.centralized_baseline"]


class TestCompletionFlag(unittest.TestCase):
    """last_run_completed distinguishes a real completion from a timeout, which
    totalCompletionTicks alone cannot (it equals maxTicks in both the
    'finished on the last tick' and 'never finished' cases)."""

    def setUp(self):
        self.runner = SimulationRunner(backend_url="http://127.0.0.1:59999")
        self.test_map = _create_test_warehouse_map()

    def test_completed_run_sets_flag_true(self):
        self.runner.run("a_normal", mode="DECENTRALIZED_PROPOSED", speed="BATCH",
                        max_ticks=20, warehouse_map=self.test_map)
        self.assertTrue(self.runner.last_run_completed)

    def test_timed_out_run_sets_flag_false(self):
        self.runner.run("c_narrow_aisle", mode="STOP_AND_WAIT", speed="BATCH",
                        max_ticks=50, warehouse_map=self.test_map)
        self.assertFalse(self.runner.last_run_completed)

    def test_flag_is_reset_between_runs(self):
        self.runner.run("c_narrow_aisle", mode="STOP_AND_WAIT", speed="BATCH",
                        max_ticks=50, warehouse_map=self.test_map)
        self.assertFalse(self.runner.last_run_completed)
        self.runner.run("a_normal", mode="DECENTRALIZED_PROPOSED", speed="BATCH",
                        max_ticks=20, warehouse_map=self.test_map)
        self.assertTrue(self.runner.last_run_completed)


class TestTaskReassignment(unittest.TestCase):
    """Mid-run task reassignment: an OFFLINE robot's unfinished destination is
    handed to an idle peer, and the run's own completion check ('all_done')
    no longer waits forever on a robot that can never itself reach its goal.

    Root cause (see CLAUDE.md Known Bugs #10): f_task_reassignment previously
    timed out for DECENTRALIZED_PROPOSED in every run because (a) nothing in
    simulation/runner.py ever reassigned R1's task to the idle backup R2, and
    (b) even a successful reassignment would not have helped, since 'all_done'
    required the now-permanently-OFFLINE R1 to itself reach its own
    destination, which it structurally never can. Fixed with pure runner-level
    bookkeeping — no change to RobotAgent, ConflictDetector, ConflictResolver,
    or DeadlockDetector, and STOP_AND_WAIT/CENTRALIZED_RESERVATION are
    untouched (they never call agent.tick(), so status never becomes OFFLINE
    for them at all — confirmed by test_F below).
    """

    def setUp(self):
        self.runner = SimulationRunner(backend_url="http://127.0.0.1:59999")
        self.test_map = _create_test_warehouse_map()

    def test_A_f_task_reassignment_now_completes_in_decentralized_mode(self):
        """This is the exact scenario/mode that timed out pre-fix (0/10 seeds
        completed in the authoritative 240-run benchmark)."""
        metric = self.runner.run(
            "f_task_reassignment", mode="DECENTRALIZED_PROPOSED", speed="BATCH",
            max_ticks=40, warehouse_map=self.test_map,
        )
        self.assertTrue(self.runner.last_run_completed,
                         "f_task_reassignment should now complete instead of timing out")
        self.assertEqual(metric.collisionCount, 0)

    def test_B_task_reassigned_event_is_recorded_with_correct_payload(self):
        self.runner.run(
            "f_task_reassignment", mode="DECENTRALIZED_PROPOSED", speed="BATCH",
            max_ticks=40, warehouse_map=self.test_map,
        )
        reassign_events = [e for e in self.runner.events if e.type == "TASK_REASSIGNED"]
        self.assertEqual(len(reassign_events), 1, "exactly one reassignment should occur")
        ev = reassign_events[0]
        self.assertEqual(ev.payload["fromRobotId"], "R1")
        self.assertEqual(ev.payload["toRobotId"], "R2")
        self.assertEqual(ev.payload["taskId"], "task_R1")
        # Reassignment must happen at/after the tick R1 actually goes OFFLINE
        # (tick 5 per the scenario's fault_config), never speculatively early.
        self.assertGreaterEqual(ev.tick, 5)

    def test_C_reassignment_is_reproducible_across_seeds(self):
        for seed in (1, 2, 3):
            runner = SimulationRunner(backend_url="http://127.0.0.1:59999")
            metric = runner.run(
                "f_task_reassignment", mode="DECENTRALIZED_PROPOSED", seed=seed,
                speed="BATCH", max_ticks=40, warehouse_map=self.test_map,
            )
            self.assertTrue(runner.last_run_completed, f"seed {seed} should complete")
            self.assertEqual(metric.collisionCount, 0, f"seed {seed} must stay collision-free")

    def test_D_baselines_now_genuinely_experience_the_offline_fault_and_time_out(self):
        """SUPERSEDED by this session's baseline-event-fidelity fix (see
        CLAUDE.md "Benchmark Fairness — Identical Event Exposure"): this test
        previously asserted STOP_AND_WAIT/CENTRALIZED_RESERVATION silently
        ignored R1's OFFLINE fault and "completed" at 8/9 ticks — that was
        the bug being fixed, not the correct baseline. Both baselines now
        genuinely observe R1 going OFFLINE (same RobotAgent._apply_telemetry()
        call DECENTRALIZED_PROPOSED already used) and the SAME task-layer
        reassignment decision is made for them too (R2 is handed R1's
        destination, exactly as for DECENTRALIZED_PROPOSED) — but neither
        baseline has any on-demand replanning of its own, so R2 never
        computes a route to the new goal and the run correctly times out.
        This is a REAL, symmetric failure — not STOP_AND_WAIT/CENTRALIZED
        magically gaining rerouting, and not a fake success being invented
        for them."""
        saw = self.runner.run(
            "f_task_reassignment", mode="STOP_AND_WAIT", speed="BATCH",
            max_ticks=40, warehouse_map=self.test_map,
        )
        self.assertFalse(self.runner.last_run_completed,
                          "STOP_AND_WAIT has no replanning, so it cannot act on "
                          "the reassignment and must legitimately time out")
        self.assertEqual(saw.collisionCount, 0)
        # The task-layer DECISION still happens identically to DECENTRALIZED_PROPOSED —
        # this is what proves the event/reassignment signal itself is symmetric.
        self.assertEqual(len([e for e in self.runner.events if e.type == "TASK_REASSIGNED"]), 1)

        cen = self.runner.run(
            "f_task_reassignment", mode="CENTRALIZED_RESERVATION", speed="BATCH",
            max_ticks=40, warehouse_map=self.test_map,
        )
        self.assertFalse(self.runner.last_run_completed,
                          "CENTRALIZED_RESERVATION has no live replanning either")
        self.assertEqual(cen.collisionCount, 0)
        self.assertEqual(len([e for e in self.runner.events if e.type == "TASK_REASSIGNED"]), 1)

    def test_E_other_scenarios_have_no_reassignment_event_and_unchanged_makespan(self):
        """No other scenario uses offline_robots — this change must be a
        complete no-op for all of them."""
        for scenario_id, expected_ticks in (("a_normal", 6), ("h_negative_control", 9)):
            runner = SimulationRunner(backend_url="http://127.0.0.1:59999")
            metric = runner.run(
                scenario_id, mode="DECENTRALIZED_PROPOSED", speed="BATCH",
                max_ticks=20, warehouse_map=self.test_map,
            )
            self.assertTrue(runner.last_run_completed)
            self.assertEqual(metric.totalCompletionTicks, expected_ticks,
                              f"{scenario_id} makespan must be unchanged")
            self.assertEqual(len([e for e in runner.events if e.type == "TASK_REASSIGNED"]), 0)

    def test_F_find_reassignment_target_returns_none_when_no_peer_is_idle(self):
        """Direct unit test of the helper: a busy/offline-only fleet must not
        fabricate a target — reassignment should retry later, never guess."""
        busy_state = RobotState(
            robotId="R2", position=Position(x=0, y=0), velocity=1.0, battery=100.0,
            currentTaskId="t2", destination=Position(x=5, y=5), currentPath=[Position(x=1, y=0)],
            status="MOVING", timestamp=0,
        )

        class _FakeAgent:
            pass

        target = _FakeAgent()
        target.state = busy_state
        agents = {"R1": _FakeAgent(), "R2": target}
        agents["R1"].state = None
        result = SimulationRunner._find_reassignment_target(agents, ["R1", "R2"], exclude="R1")
        self.assertIsNone(result, "no IDLE peer exists, so no target should be returned")

    def test_G_reassign_task_updates_target_destination_task_and_forces_replan(self):
        """Direct unit test of the helper: verifies the target's goal/task/path
        are updated and a replan is requested, without touching movement logic
        itself (that remains RobotAgent.tick()'s job on the next tick)."""
        offline_state = RobotState(
            robotId="R1", position=Position(x=6, y=2), velocity=0.0, battery=100.0,
            currentTaskId="task_R1", destination=Position(x=10, y=2), currentPath=[],
            status="OFFLINE", timestamp=5,
        )
        target_state = RobotState(
            robotId="R2", position=Position(x=2, y=17), velocity=0.0, battery=100.0,
            currentTaskId=None, destination=Position(x=2, y=17), currentPath=[],
            status="IDLE", timestamp=5,
        )

        class _FakeAgent:
            _replan_requested = False

        target = _FakeAgent()
        target.state = target_state
        SimulationRunner._reassign_task(target, offline_state)

        self.assertEqual((target.state.destination.x, target.state.destination.y), (10, 2))
        self.assertEqual(target.state.currentTaskId, "task_R1")
        self.assertEqual(target.state.currentPath, [])
        self.assertEqual(target.state.status, "MOVING")
        self.assertTrue(target._replan_requested)


class TestIdenticalEventFidelity(unittest.TestCase):
    """PART 1 fix: STOP_AND_WAIT and CENTRALIZED_RESERVATION must genuinely
    experience the same scripted environmental events DECENTRALIZED_PROPOSED
    does — the offline sensor fault (f_task_reassignment) and the scripted
    blocked-cell event (e_blocked_aisle) — WITHOUT gaining any new
    replanning/rerouting capability of their own. Each baseline keeps its
    own defined, unmodified algorithm; only whether the fault reaches it at
    all changed. See CLAUDE.md "Benchmark Fairness — Identical Event Exposure"."""

    def setUp(self):
        self.test_map = _create_test_warehouse_map()

    # ── e_blocked_aisle ──────────────────────────────────────────────────

    def test_blocked_aisle_event_is_recorded_for_every_mode(self):
        """The scripted AISLE_BLOCKED event itself was already mode-agnostic
        before this session's fix — this locks that down as a regression
        guard while the READ side (below) is what actually changed."""
        for mode in ("STOP_AND_WAIT", "CENTRALIZED_RESERVATION", "DECENTRALIZED_PROPOSED"):
            runner = SimulationRunner(backend_url="http://127.0.0.1:59999")
            runner.run("e_blocked_aisle", mode=mode, speed="BATCH",
                       max_ticks=50, warehouse_map=self.test_map)
            self.assertEqual(
                len([e for e in runner.events if e.type == "AISLE_BLOCKED"]), 1,
                f"{mode} should record the scripted block event",
            )

    def test_stop_and_wait_now_respects_the_blocked_cell_and_times_out(self):
        """Pre-fix, STOP_AND_WAIT silently drove through (10,9) and
        "completed" at 14 ticks. It has no replanning, so once it genuinely
        observes the block it can only refuse the cell forever."""
        runner = SimulationRunner(backend_url="http://127.0.0.1:59999")
        metric = runner.run("e_blocked_aisle", mode="STOP_AND_WAIT", speed="BATCH",
                            max_ticks=50, warehouse_map=self.test_map)
        self.assertFalse(runner.last_run_completed)
        self.assertEqual(metric.collisionCount, 0)

    def test_centralized_reservation_now_respects_the_blocked_cell_and_times_out(self):
        """Same reasoning: its schedule was fixed before the tick-4 event, so
        discovering the obstruction on arrival halts it — a physical floor,
        not new rerouting logic."""
        runner = SimulationRunner(backend_url="http://127.0.0.1:59999")
        metric = runner.run("e_blocked_aisle", mode="CENTRALIZED_RESERVATION", speed="BATCH",
                            max_ticks=50, warehouse_map=self.test_map)
        self.assertFalse(runner.last_run_completed)
        self.assertEqual(metric.collisionCount, 0)

    def test_decentralized_proposed_still_reroutes_and_completes_unchanged(self):
        """Regression guard: DECENTRALIZED_PROPOSED's own rerouting capability
        must be completely untouched by this fairness fix."""
        runner = SimulationRunner(backend_url="http://127.0.0.1:59999")
        metric = runner.run("e_blocked_aisle", mode="DECENTRALIZED_PROPOSED", speed="BATCH",
                            max_ticks=50, warehouse_map=self.test_map)
        self.assertTrue(runner.last_run_completed)
        self.assertEqual(metric.totalCompletionTicks, 16)  # unchanged from every prior session
        self.assertEqual(metric.collisionCount, 0)

    # ── f_task_reassignment ──────────────────────────────────────────────

    def test_offline_event_reaches_all_three_modes(self):
        """A TASK_REASSIGNED event only fires off a genuinely-read OFFLINE
        status — so its presence in all 3 modes proves the sensor fault
        itself (not just its consequence) is now symmetric."""
        for mode in ("STOP_AND_WAIT", "CENTRALIZED_RESERVATION", "DECENTRALIZED_PROPOSED"):
            runner = SimulationRunner(backend_url="http://127.0.0.1:59999")
            runner.run("f_task_reassignment", mode=mode, speed="BATCH",
                       max_ticks=40, warehouse_map=self.test_map)
            self.assertEqual(
                len([e for e in runner.events if e.type == "TASK_REASSIGNED"]), 1,
                f"{mode} should observe R1 going OFFLINE and reassign its task",
            )

    def test_decentralized_proposed_still_completes_f_task_reassignment_unchanged(self):
        runner = SimulationRunner(backend_url="http://127.0.0.1:59999")
        metric = runner.run("f_task_reassignment", mode="DECENTRALIZED_PROPOSED", speed="BATCH",
                            max_ticks=40, warehouse_map=self.test_map)
        self.assertTrue(runner.last_run_completed)
        self.assertEqual(metric.totalCompletionTicks, 28)  # unchanged
        self.assertEqual(metric.collisionCount, 0)


class TestPerRobotTaskCompletion(unittest.TestCase):
    """last_run_completion_ticks_per_robot — the per-task granularity behind
    the new deadline/task-completion metric (Part 3). Never fabricated: a
    robot appears only if it genuinely reached ITS CURRENT destination."""

    def setUp(self):
        self.test_map = _create_test_warehouse_map()

    def test_every_completed_robot_is_recorded_when_the_run_completes(self):
        runner = SimulationRunner(backend_url="http://127.0.0.1:59999")
        metric = runner.run("a_normal", mode="DECENTRALIZED_PROPOSED", speed="BATCH",
                            max_ticks=20, warehouse_map=self.test_map)
        self.assertTrue(runner.last_run_completed)
        # a_normal has 2 robots — both must show a genuine positive tick.
        self.assertEqual(len(runner.last_run_completion_ticks_per_robot), 2)
        for tick in runner.last_run_completion_ticks_per_robot.values():
            self.assertGreater(tick, 0)

    def test_a_never_arriving_robot_is_never_recorded_as_completed(self):
        """The offline robot in f_task_reassignment (STOP_AND_WAIT, which
        cannot act on its reassignment) must never appear as completed —
        this is the direct proof of Part 5 rule 1: never count an unfinished
        task as completed."""
        runner = SimulationRunner(backend_url="http://127.0.0.1:59999")
        runner.run("f_task_reassignment", mode="STOP_AND_WAIT", speed="BATCH",
                   max_ticks=40, warehouse_map=self.test_map)
        self.assertFalse(runner.last_run_completed)
        self.assertNotIn("R1", runner.last_run_completion_ticks_per_robot)

    def test_reassigned_robot_completion_tick_reflects_the_new_destination(self):
        """R2 trivially "completes" its own original start==goal task at tick
        1 — that entry must be cleared and replaced once R2 is reassigned
        R1's real task, so this reports the REAL completion, not the stale
        trivial one."""
        runner = SimulationRunner(backend_url="http://127.0.0.1:59999")
        runner.run("f_task_reassignment", mode="DECENTRALIZED_PROPOSED", speed="BATCH",
                   max_ticks=40, warehouse_map=self.test_map)
        self.assertTrue(runner.last_run_completed)
        self.assertIn("R2", runner.last_run_completion_ticks_per_robot)
        self.assertGreater(runner.last_run_completion_ticks_per_robot["R2"], 5,
                           "must reflect the reassigned task's real completion, not the stale tick=1 entry")
        self.assertNotIn("R1", runner.last_run_completion_ticks_per_robot)

if __name__ == "__main__":
    unittest.main()
