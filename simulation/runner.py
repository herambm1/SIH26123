import heapq
import json
import logging
import random
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from shared.python.models import (
    Conflict,
    PerformanceMetric,
    Position,
    RobotPath,
    RobotState,
    SimulationEvent,
    WarehouseMap,
)
from collision_engine.deadlock import DeadlockDetector
from collision_engine.detection import ConflictDetector
from collision_engine.resolution import ConflictResolver
from robot_agent.agent import RobotAgent
from robot_agent.communication.transport import InProcessBus, MessageFaultConfig
from edge.sensor_source import SimulationSensorSource
from edge.fault_injection import SensorFaultConfig
from simulation.referee import CollisionReferee
from simulation.scenarios import Scenario, get_scenario, list_scenarios

logger = logging.getLogger("simulation.runner")

# ── FastAPI setup (graceful if fastapi is not installed) ──────────────────────
try:
    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    app = FastAPI(title="SIH 26123 — Simulation Control API", version="0.1.0")
except ImportError:
    app = None
    JSONResponse = None


# ── Transport instrumentation ──────────────────────────────────────────────────
# The real InProcessBus (robot_agent.communication.transport) doesn't track a
# cumulative message count — it's not part of the Transport contract, it was
# only ever an ad hoc metric the old MockInProcessBus stand-in kept for itself.
# This wrapper delegates every call unchanged to the real bus and only adds a
# counter, so PerformanceMetric.messageCount keeps working without touching
# robot_agent/communication (owned by Member 2) or reimplementing any
# messaging/fault-injection logic of its own.
class _MessageCountingTransport:
    """Thin pass-through instrumentation wrapper around a real Transport."""

    def __init__(self, bus):
        self._bus = bus
        self.message_count: int = 0

    def broadcast(self, msg: dict) -> None:
        self.message_count += 1
        self._bus.broadcast(msg)

    def send(self, to: str, msg: dict) -> None:
        self.message_count += 1
        self._bus.send(to, msg)

    def receive(self, robot_id: str) -> list[dict]:
        return self._bus.receive(robot_id)

    def advance_tick(self) -> None:
        self._bus.advance_tick()


# ── Deadlock instrumentation ──────────────────────────────────────────────────
# PerformanceMetric.deadlockCount must reflect what the REAL DeadlockDetector
# actually did. It previously did not: the count was inferred from
# `_action_this_tick == "YIELD" and _stall_ticks >= 5`, which is the
# ConflictResolver's narrow-aisle YIELD path — a different mechanism entirely —
# and `_force_yield()` zeroes `_stall_ticks` the instant the real detector
# fires, so the proxy could never observe a genuine activation. A strict audit
# proved this: DeadlockDetector.check() returned True twice during d_deadlock
# while the reported deadlockCount stayed 0.
#
# This wrapper delegates every call unchanged to the real DeadlockDetector and
# only tallies how many times it returned True — the same pure-instrumentation
# pattern _MessageCountingTransport uses above. DeadlockDetector's algorithm and
# decision logic are untouched, and RobotAgent needs no changes: it just calls
# .check() as before.
class _DeadlockCountingDetector:
    """Pass-through counter around a real DeadlockDetector.

    One activation == one `check()` call that returned True (which is exactly
    one `_force_yield()` in RobotAgent.tick()), so a single deadlock recovery
    is never double-counted. The counter is shared across every robot in a run.
    """

    def __init__(self, detector, counter: dict):
        self._detector = detector
        self._counter = counter

    def check(self, robot_id: str, stall_ticks: int, waiting_on) -> bool:
        fired = self._detector.check(robot_id, stall_ticks, waiting_on)
        if fired:
            self._counter["count"] += 1
        return fired

    def __getattr__(self, name):
        # Anything else (e.g. stall_threshold) reads straight off the real detector.
        return getattr(self._detector, name)


# ── Grid A* Path Planner (conforming to Member 1's Planner interface) ────────
class GridAStarPlanner:
    """4-connected grid A* path planner on WarehouseMap."""

    def __init__(self, warehouse_map: WarehouseMap):
        self.warehouse_map = warehouse_map
        self._static_obstacles = {(o.x, o.y) for o in (warehouse_map.obstacles or [])}

    def plan(
        self,
        start: Position,
        goal: Position,
        blocked_cells: list[Position] | None = None,
        avoid_intervals: list[tuple[Position, int]] | None = None,
        start_tick: int = 0,
    ) -> RobotPath:
        blocked = set(self._static_obstacles)
        if blocked_cells:
            for b in blocked_cells:
                blocked.add((b.x, b.y))

        avoid_st = set()
        if avoid_intervals:
            for cell, t in avoid_intervals:
                avoid_st.add((cell.x, cell.y, t))

        start_pt = (start.x, start.y)
        goal_pt = (goal.x, goal.y)
        if start_pt == goal_pt:
            return RobotPath(
                robotId="",
                waypoints=[Position(x=goal.x, y=goal.y, tick=start_tick + 1)],
                generatedAtTick=start_tick,
                version=1,
            )

        open_set = []
        heapq.heappush(open_set, (0 + abs(start.x - goal.x) + abs(start.y - goal.y), 0, start_pt, 0))
        came_from = {}
        cost_so_far = {start_pt: 0}

        w = self.warehouse_map.gridWidth
        h = self.warehouse_map.gridHeight
        counter = 0

        found_end = None
        while open_set:
            _, _, current, curr_t = heapq.heappop(open_set)
            if current == goal_pt:
                found_end = current
                break

            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nx, ny = current[0] + dx, current[1] + dy
                next_pt = (nx, ny)
                next_t = start_tick + cost_so_far[current] + 1

                if not (0 <= nx < w and 0 <= ny < h):
                    continue
                if next_pt in blocked and next_pt != goal_pt:
                    continue
                if (nx, ny, next_t) in avoid_st:
                    continue

                new_cost = cost_so_far[current] + 1
                if next_pt not in cost_so_far or new_cost < cost_so_far[next_pt]:
                    cost_so_far[next_pt] = new_cost
                    priority = new_cost + abs(nx - goal.x) + abs(ny - goal.y)
                    counter += 1
                    heapq.heappush(open_set, (priority, counter, next_pt, next_t))
                    came_from[next_pt] = current

        if not found_end:
            # Fallback path if blocked
            return RobotPath(
                robotId="",
                waypoints=[],
                generatedAtTick=start_tick,
                version=1,
            )

        # Reconstruct path
        path_coords = []
        curr = goal_pt
        while curr != start_pt:
            path_coords.append(curr)
            curr = came_from[curr]
        path_coords.reverse()

        waypoints = [
            Position(x=c[0], y=c[1], tick=start_tick + idx + 1)
            for idx, c in enumerate(path_coords)
        ]
        return RobotPath(
            robotId="",
            waypoints=waypoints,
            generatedAtTick=start_tick,
            version=1,
        )


# ── Simulation Runner Engine ──────────────────────────────────────────────────
class SimulationRunner:
    """Core simulation execution engine supporting 3 comparison modes."""

    def __init__(self, backend_url: str = "http://localhost:8080"):
        self.backend_url = backend_url
        self.running: bool = False
        self.current_tick: int = 0
        self.scenario_id: str | None = None
        self.mode: str = "DECENTRALIZED_PROPOSED"
        self._stop_requested: bool = False
        self.referee = CollisionReferee()
        self.events: list[SimulationEvent] = []
        # True only if the most recent run() ended because every robot reached
        # its destination (the all_done break) — False if it exhausted
        # max_ticks or was stopped. PerformanceMetric is a frozen contract and
        # has no field for this, so it is exposed here instead: a run that
        # times out has NO valid makespan, and totalCompletionTicks == maxTicks
        # for such a run is a censoring artifact, not a completion time.
        self.last_run_completed: bool = False
        # Per-robot task completion ticks from the most recent run() —
        # {robotId: tick it first reached ITS CURRENT destination}. A robot
        # that never reached its destination (dead, stuck, or the run timed
        # out first) has no entry — never fabricated. Exposed the same way
        # as last_run_completed (PerformanceMetric is a frozen contract with
        # no per-robot field) so the benchmark can report genuine per-task
        # completion/deadline metrics distinct from whole-run makespan (see
        # CLAUDE.md "Benchmark Categories" / Part 3 deadline metric).
        self.last_run_completion_ticks_per_robot: dict[str, int] = {}

    def stop(self) -> None:
        """Signal the simulation to halt."""
        self._stop_requested = True
        self.running = False

    def run(
        self,
        scenario_id: str,
        mode: str = "DECENTRALIZED_PROPOSED",
        seed: int = 42,
        speed: str = "BATCH",
        max_ticks: int | None = None,
        warehouse_map: WarehouseMap | None = None,
        task_assignments: list[dict] | None = None,
    ) -> PerformanceMetric:
        """Execute a scenario run synchronously and return the resulting PerformanceMetric.

        task_assignments: optional list of Java-originated assignment dicts,
        each shaped like {robotId, taskId, pickupPosition:{x,y}, dropPosition:{x,y},
        priority} — the real TaskAssignment/Task data the backend's
        TaskAllocationService already computed (see docs/00_SHARED_CONTRACTS.md
        Task/TaskAssignment). When a robotId in this list matches a robot in the
        scenario, that assignment's dropPosition/taskId/priority override the
        scenario's hardcoded goal/task_id/priority for that robot — this is what
        makes centralized Java task allocation actually influence which robot
        goes where in a real run (previously backend-only bookkeeping, see
        CLAUDE.md Known Integration Gaps #3). Absent/empty (the default),
        every scenario behaves exactly as before — no assignment for a robot
        means its scenario-defined start/goal is used unchanged.
        """
        self.scenario_id = scenario_id
        self.mode = mode
        self.running = True
        self._stop_requested = False
        self.current_tick = 0
        self.events = []
        self.referee = CollisionReferee()
        self.last_run_completed = False
        self.last_run_completion_ticks_per_robot = {}

        scenario = get_scenario(scenario_id, seed, warehouse_map=warehouse_map)
        sim_max_ticks = max_ticks or scenario.max_ticks

        # Push the actual WarehouseMap this run uses to the Java backend, so
        # GET /api/warehouse (Java) serves the real map the simulation is
        # executing against rather than nothing/fabricated data (see
        # CLAUDE.md Known Integration Gaps #2). Resilient — silently no-ops
        # if the backend is unreachable, same as every other backend push.
        self._push_to_backend("/api/warehouse", self._warehouse_map_to_dict(scenario.warehouse_map))

        assignments_by_robot: dict[str, dict] = {
            a.get("robotId"): a for a in (task_assignments or []) if a.get("robotId")
        }
        robot_configs = [self._apply_task_assignment(r, assignments_by_robot) for r in scenario.robots]
        robot_ids = [r["robotId"] for r in robot_configs]

        # Initialize planner
        planner = GridAStarPlanner(scenario.warehouse_map)

        # Initialize transport — the real InProcessBus (robot_agent.communication),
        # wrapped only for the messageCount metric (see _MessageCountingTransport).
        bus_fault_config = MessageFaultConfig(
            drop_rate=scenario.fault_config.get("drop_rate", 0.0),
            delay_ticks=scenario.fault_config.get("delay_ticks", 0),
        )
        # The run's seed is propagated into every existing randomness source so
        # "same scenario + same mode + same seed" is reproducible and a
        # different seed genuinely varies the mechanisms that DO use randomness.
        # No new randomness is introduced anywhere — these three RNGs already
        # existed and were simply being left unseeded (or hardcoded).
        transport = _MessageCountingTransport(
            InProcessBus(robot_ids, fault_config=bus_fault_config, rng=random.Random(seed))
        )

        # Ground truth position map
        gt_positions: dict[str, Position] = {
            r["robotId"]: Position(x=r["start"].x, y=r["start"].y) for r in robot_configs
        }

        def _ground_truth(rid: str) -> Position:
            return gt_positions.get(rid, Position(x=0, y=0))

        # Per-robot fault profile — offline_robots is a per-robot {robotId: tick}
        # map (e.g. scenario f_task_reassignment: only R1 goes offline, R2 must
        # stay available to take over its task), but SensorFaultConfig's
        # offline_after_tick is a single value per SimulationSensorSource
        # instance. The real SensorSource is built to be constructed once per
        # robot (read() already takes robot_id) — one instance per robot with
        # its own fault profile is the correct adaptation, not a limitation to
        # work around by reintroducing a shared mock.
        offline_schedule: dict[str, int] = scenario.fault_config.get("offline_robots", {})
        noise_std = scenario.fault_config.get("noise_std", 0.0)
        dropout_rate = scenario.fault_config.get("dropout_rate", 0.0)

        # Construct agents
        deadlock_activations: dict[str, int] = {"count": 0}
        agents: dict[str, RobotAgent] = {}
        for r in robot_configs:
            rid = r["robotId"]
            detector = ConflictDetector()
            resolver = ConflictResolver()
            # Real DeadlockDetector, wrapped only to tally genuine activations
            # for PerformanceMetric.deadlockCount (see _DeadlockCountingDetector).
            deadlock = _DeadlockCountingDetector(
                DeadlockDetector(stall_threshold=5), deadlock_activations
            )

            sensor_fault_config = SensorFaultConfig(
                noise_std=noise_std,
                dropout_rate=dropout_rate,
                offline_after_tick=offline_schedule.get(rid),
            )
            # Per-robot RNG derived deterministically from the run seed, so each
            # robot's noise/dropout stream is distinct but fully reproducible.
            # String seeding is used deliberately: it is stable across processes,
            # unlike hash(), which is randomized per interpreter by PYTHONHASHSEED.
            sensor = SimulationSensorSource(
                _ground_truth, sensor_fault_config, rng=random.Random(f"{seed}:{rid}")
            )

            agent = RobotAgent(
                robot_id=rid,
                planner=planner,
                transport=transport,
                sensor=sensor,
                detector=detector,
                resolver=resolver,
                deadlock=deadlock,
            )

            # Initial path planning
            initial_path = planner.plan(r["start"], r["goal"], start_tick=0)
            agent.state = RobotState(
                robotId=rid,
                position=Position(x=r["start"].x, y=r["start"].y),
                velocity=1.0 if initial_path.waypoints else 0.0,
                battery=100.0,
                currentTaskId=r.get("taskId", f"task_{rid}"),
                destination=Position(x=r["goal"].x, y=r["goal"].y),
                currentPath=list(initial_path.waypoints),
                status="MOVING" if initial_path.waypoints else "IDLE",
                timestamp=0,
            )
            setattr(agent.state, "task_priority", r.get("priority", 1))
            agents[rid] = agent

        # Setup for CENTRALIZED_RESERVATION mode
        centralized_schedules: dict[str, list[Position]] = {}
        if mode == "CENTRALIZED_RESERVATION":
            centralized_schedules = self._build_centralized_schedules(
                scenario.warehouse_map, robot_configs, planner, seed
            )
            for rid, sched in centralized_schedules.items():
                if rid in agents and agents[rid].state:
                    agents[rid].state.currentPath = list(sched)

        # Metrics tracking
        total_collisions = 0
        reroutes_count = 0
        idle_ticks_total = 0
        completion_ticks_per_robot: dict[str, int] = {}
        # robotIds whose incomplete task has already been handed to a peer —
        # prevents re-triggering reassignment every tick for the same robot
        # once it has succeeded (see the mid-run reassignment step below).
        reassigned_from: set[str] = set()
        # Last NEGOTIATION resolutionAction emitted per robot — pure
        # observability bookkeeping (frontend Phase 5, approved addition
        # "b-2"), used only to emit a real event on a real CHANGE rather than
        # spamming one every tick a robot happens to still hold the same
        # resolver verdict. Reads agent._action_this_tick/_waiting_on/
        # _blocked_by_peer — attributes ConflictResolver/RobotAgent already
        # compute for their own decision-making — and writes nothing back.
        # Does not alter conflict detection/resolution in any way.
        last_negotiation_action: dict[str, str | None] = {}

        # ── Main Tick Loop ────────────────────────────────────────────────────
        for tick in range(1, sim_max_ticks + 1):
            if self._stop_requested:
                break
            self.current_tick = tick

            # 1. Process scripted scenario events (e.g. AISLE_BLOCKED)
            for ev in scenario.events:
                if ev.get("tick") == tick:
                    ev_type = ev.get("type", "")
                    payload = ev.get("payload", {})
                    # Found via live full-stack verification (frontend
                    # integration task): a scripted event's payload may embed
                    # a raw Position dataclass (e.g. AISLE_BLOCKED's "cell",
                    # authored directly in the scenario file) — json.dumps
                    # cannot serialize that, and _push_to_backend's broad
                    # `except Exception: pass` was silently swallowing the
                    # resulting TypeError every tick, so AISLE_BLOCKED never
                    # actually reached the Java backend/dashboard even though
                    # it was correctly applied to agent._blocked_cells the
                    # whole time (a real robot detour still happened; only
                    # the outward-facing event was lost). Fix: build a
                    # JSON-safe copy for the outward SimulationEvent only —
                    # the original `payload` (with the real Position object)
                    # is untouched below for agent bookkeeping, and no
                    # scenario file/coordinate/timing was changed.
                    json_safe_payload = {
                        k: ({"x": v.x, "y": v.y} if isinstance(v, Position) else v)
                        for k, v in payload.items()
                    }
                    sim_event = SimulationEvent(
                        eventId=f"ev_{tick}_{ev_type}",
                        type=ev_type,
                        tick=tick,
                        payload=json_safe_payload,
                    )
                    self.events.append(sim_event)
                    if ev_type == "AISLE_BLOCKED" and "cell" in payload:
                        blocked_cell = payload["cell"]
                        for ag in agents.values():
                            ag._blocked_cells.append(blocked_cell)
                            ag._replan_requested = True

            # 2. Advance transport delayed messages
            transport.advance_tick()

            # 3. Step robots based on mode
            tick_states: list[RobotState] = []
            for rid in robot_ids:
                agent = agents[rid]

                if mode == "DECENTRALIZED_PROPOSED":
                    state = agent.tick(tick)
                    self._emit_negotiation_event_if_changed(rid, agent, tick, last_negotiation_action)
                elif mode == "STOP_AND_WAIT":
                    state = self._step_stop_and_wait(agent, gt_positions, tick)
                elif mode == "CENTRALIZED_RESERVATION":
                    state = self._step_centralized(agent, tick)
                else:
                    state = agent.tick(tick)

                # Update ground truth
                gt_positions[rid] = Position(x=state.position.x, y=state.position.y)
                tick_states.append(state)

                # Track metrics
                if state.status in ("IDLE", "WAITING"):
                    idle_ticks_total += 1
                if agent._replan_requested or getattr(agent, "_action_this_tick", "") == "REROUTE":
                    reroutes_count += 1

                # Goal completion check
                dest = state.destination
                if (
                    dest
                    and state.position.x == dest.x
                    and state.position.y == dest.y
                    and rid not in completion_ticks_per_robot
                ):
                    completion_ticks_per_robot[rid] = tick

            # 3.5 Mid-run task reassignment: a robot whose sensor has reported
            # it OFFLINE with an unfinished destination hands that destination
            # to an idle peer, instead of the fleet freezing on a dead robot
            # forever (see CLAUDE.md Known Bugs #10). This is pure runner-level
            # bookkeeping — the same role Java's TaskAllocationService.
            # handleRobotOffline() already plays, just applied directly here
            # because a headless Python run never talks to Java (this mirrors
            # the existing _apply_task_assignment() pattern, which already
            # applies a Java-originated assignment before tick 1; this is the
            # same kind of centralized goal handoff, only triggered mid-run).
            # It does NOT touch how the receiving robot decides to move —
            # that is still entirely its own RobotAgent.tick() next tick,
            # planning/negotiating/avoiding conflicts from local info only.
            for rid in robot_ids:
                agent = agents[rid]
                st = agent.state
                if (
                    st
                    and st.status == "OFFLINE"
                    and rid not in reassigned_from
                    and st.destination
                    and (st.position.x != st.destination.x or st.position.y != st.destination.y)
                ):
                    target_id = self._find_reassignment_target(agents, robot_ids, exclude=rid)
                    if target_id is not None:
                        self._reassign_task(agents[target_id], st)
                        reassigned_from.add(rid)
                        # target_id may already hold a completion_ticks_per_robot
                        # entry from its OWN prior (now-superseded) destination
                        # (e.g. f_task_reassignment's idle backup robot, whose
                        # trivial start==goal was already "completed" at tick
                        # 1) — that entry is now stale: it recorded the OLD
                        # task, not the newly-assigned one. Clearing it lets a
                        # genuine completion of the NEW destination be recorded
                        # fresh; never inflates or fakes a completion.
                        completion_ticks_per_robot.pop(target_id, None)
                        self.events.append(
                            SimulationEvent(
                                eventId=f"reassign_{tick}_{rid}_{target_id}",
                                type="TASK_REASSIGNED",
                                tick=tick,
                                payload={
                                    "fromRobotId": rid,
                                    "toRobotId": target_id,
                                    "taskId": st.currentTaskId,
                                },
                            )
                        )
                    # If no idle peer exists yet, this is retried next tick —
                    # rid stays out of reassigned_from until it actually
                    # succeeds, so a temporarily-busy fleet still eventually
                    # hands off the task once someone frees up.

            # 4. Independent ground truth collision check
            tick_collisions = self.referee.check(gt_positions)
            if tick_collisions:
                total_collisions += len(tick_collisions)
                for r1, r2 in tick_collisions:
                    self.events.append(
                        SimulationEvent(
                            eventId=f"coll_{tick}_{r1}_{r2}",
                            type="CONFLICT_DETECTED",
                            tick=tick,
                            payload={"robotIds": [r1, r2], "collision": True},
                        )
                    )

            # 5. Push telemetry and events to backend (resilient to failure)
            self._push_to_backend("/api/telemetry/batch", [self._state_to_dict(s) for s in tick_states])
            if self.events:
                self._push_to_backend(
                    "/api/events",
                    [{"eventId": e.eventId, "type": e.type, "tick": e.tick, "payload": e.payload} for e in self.events],
                )

            # 6. Check if all robots reached destination
            # An OFFLINE robot only stops being a live blocker on "all_done"
            # if its task was ACTUALLY handed to a peer (rid in
            # reassigned_from) — never merely because it went offline. A
            # blanket "OFFLINE == done" would fabricate a false completion
            # for a mode with no reassignment mechanism of its own (e.g.
            # STOP_AND_WAIT/CENTRALIZED_RESERVATION correctly experiencing
            # the same OFFLINE fault but having no on-demand replanning to
            # act on a handoff — see CLAUDE.md "Benchmark Fairness"): that
            # robot's original task was never actually finished by anyone,
            # so the run must keep waiting on it (and correctly time out at
            # maxTicks) exactly like any other genuinely unresolved task.
            # This does not weaken collision safety: an OFFLINE robot is
            # still tracked in gt_positions and checked by CollisionReferee
            # every tick, and every peer still treats it as a permanent
            # physical obstacle via _PEER_STATIONARY_STATUSES — this only
            # changes when the RUN is considered finished, never where
            # anyone is allowed to move.
            all_done = all(
                ag.state.status == "IDLE"
                or (ag.state.status == "OFFLINE" and rid in reassigned_from)
                or (ag.state.destination and ag.state.position.x == ag.state.destination.x and ag.state.position.y == ag.state.destination.y)
                for rid, ag in agents.items()
            )
            if all_done:
                # The ONLY path that counts as a genuine completion. Reaching
                # the end of the tick range instead means the run timed out and
                # has no valid makespan (see last_run_completed's docstring).
                self.last_run_completed = True
                break

            # Rate limiting for LIVE speed (~2 ticks per second)
            if speed == "LIVE":
                time.sleep(0.5)

        # Compute completion statistics
        # Exposed verbatim for the benchmark's per-task/deadline metrics (see
        # Part 3 in CLAUDE.md "Benchmark Categories") — never fabricated: a
        # robot appears here only if it genuinely reached its OWN CURRENT
        # destination (a stale entry from a superseded destination is
        # cleared at reassignment time, above).
        self.last_run_completion_ticks_per_robot = dict(completion_ticks_per_robot)
        final_tick = self.current_tick
        total_completion_ticks = final_tick
        avg_completion_ticks = (
            sum(completion_ticks_per_robot.values()) / len(completion_ticks_per_robot)
            if completion_ticks_per_robot
            else float(final_tick)
        )

        metric = PerformanceMetric(
            runId=f"run_{scenario_id}_{mode}_{seed}_{int(time.time())}",
            scenarioId=scenario_id,
            mode=mode,
            totalCompletionTicks=total_completion_ticks,
            avgCompletionTicks=round(avg_completion_ticks, 2),
            collisionCount=total_collisions,
            # Number of genuine DeadlockDetector.check() activations (== forced
            # deadlock recoveries) across all robots for the whole run.
            deadlockCount=deadlock_activations["count"],
            rerouteCount=reroutes_count,
            idleTicksTotal=idle_ticks_total,
            messageCount=transport.message_count,
            seed=seed,
        )

        # Push final metrics to Java backend
        self._push_to_backend("/api/metrics", {
            "runId": metric.runId,
            "scenarioId": metric.scenarioId,
            "mode": metric.mode,
            "totalCompletionTicks": metric.totalCompletionTicks,
            "avgCompletionTicks": metric.avgCompletionTicks,
            "collisionCount": metric.collisionCount,
            "deadlockCount": metric.deadlockCount,
            "rerouteCount": metric.rerouteCount,
            "idleTicksTotal": metric.idleTicksTotal,
            "messageCount": metric.messageCount,
            "seed": metric.seed,
        })

        self.running = False
        return metric

    def _emit_negotiation_event_if_changed(
        self,
        rid: str,
        agent: RobotAgent,
        tick: int,
        last_negotiation_action: dict[str, str | None],
    ) -> None:
        """Observability only — approved addition "b-2" (frontend Phase 5).

        Reads agent._action_this_tick (the real ConflictResolver verdict for
        this robot: CONTINUE|WAIT|YIELD|REROUTE|REASSIGN_TASK, the exact
        vocabulary docs/00_SHARED_CONTRACTS.md already defines for
        Conflict.resolutionAction) and agent._waiting_on/_blocked_by_peer
        (the real peer robotId, if any) — both already computed by
        RobotAgent/ConflictResolver for their own decision-making, inside
        agent.tick() which already ran before this is called. This method
        does not call the detector or resolver, does not read any field they
        don't already expose as an instance attribute, and writes nothing
        back onto the agent or its state — it can change nothing about how a
        conflict is detected or resolved, only whether an already-decided
        outcome is also recorded as a NEGOTIATION SimulationEvent.

        Fires only on a genuine CHANGE from the last action recorded for
        this robot (never every tick a stale value happens to persist) —
        _action_this_tick is set once inside RobotAgent._apply_action() and
        is not reset to None between ticks, so reading it unconditionally
        every tick would misreport a resolver decision from several ticks
        ago as still happening now. Never invents a value: robotId, the
        peer's id, resolutionAction, and tick are all read verbatim.
        """
        action = getattr(agent, "_action_this_tick", None)
        if action is None or last_negotiation_action.get(rid) == action:
            return
        last_negotiation_action[rid] = action
        peer_id = getattr(agent, "_waiting_on", None) or getattr(agent, "_blocked_by_peer", None)
        self.events.append(
            SimulationEvent(
                eventId=f"neg_{tick}_{rid}_{action}",
                type="NEGOTIATION",
                tick=tick,
                payload={"robotId": rid, "peerRobotId": peer_id, "resolutionAction": action},
            )
        )

    @staticmethod
    def _apply_sensor_telemetry(agent: RobotAgent, current_tick: int) -> None:
        """Read this tick's sensor telemetry and fold it into agent.state,
        via the EXACT SAME RobotAgent._apply_telemetry() DECENTRALIZED_PROPOSED's
        agent.tick() already calls — not a re-implementation.

        Both baseline step functions call this before doing anything else, so
        every mode observes an identical scripted fault (e.g. f_task_reassignment's
        R1 going OFFLINE) at the same tick, via the same detection logic
        (same OFFLINE/DEGRADED/dropout semantics, same HeartbeatMonitor
        threshold) — see CLAUDE.md "Benchmark Fairness — Identical Event
        Exposure". A no-op for every scenario that doesn't configure
        offline_after_tick/noise_std/dropout_rate (all 7 others): the
        returned telemetry position always matches ground truth and
        sensorHealth is "OK". This does not give either baseline any new
        movement capability — it only ensures the underlying fault is
        genuinely observed, exactly like DECENTRALIZED_PROPOSED observes it.
        """
        if not agent.state or not agent.sensor:
            return
        try:
            telemetry = agent.sensor.read(agent.robot_id, current_tick)
        except Exception:
            telemetry = None
        agent.state = agent._apply_telemetry(agent.state, telemetry, current_tick)

    @staticmethod
    def _cell_is_scripted_blocked(agent: RobotAgent, cell: Position) -> bool:
        """True if `cell` was named by a scripted AISLE_BLOCKED-style event
        (agent._blocked_cells) — the same list DECENTRALIZED_PROPOSED's
        `_known_blocked_cells()` already checks. Injection into this list
        already happens identically for every mode (runner.py's per-tick
        scenario-event loop is mode-agnostic) — this only adds the missing
        READ side for the two baselines, so they refuse to enter an
        impassable cell instead of silently driving through it. This is a
        physical safety floor (a real obstacle cannot be driven through),
        not a rerouting decision: neither baseline gains any replanning —
        each simply cannot advance past this one cell, ever, and may
        legitimately time out (see CLAUDE.md "Benchmark Fairness").
        """
        return any(b.x == cell.x and b.y == cell.y for b in agent._blocked_cells)

    def _step_stop_and_wait(
        self, agent: RobotAgent, all_positions: dict[str, Position], current_tick: int
    ) -> RobotState:
        """Naive baseline: stops if any other robot is on the next waypoint
        cell, or if that cell was named by a scripted blocked-cell event.
        Never replans, never reroutes — that is the entire point of this
        baseline, and must stay true even under a real scripted fault."""
        self._apply_sensor_telemetry(agent, current_tick)
        if not agent.state or agent.state.status == "OFFLINE":
            if agent.state:
                agent.state.velocity = 0.0
                agent.state.timestamp = current_tick
            return agent.state

        if agent.state.currentPath and len(agent.state.currentPath) > 0:
            next_wp = agent.state.currentPath[0]
            # Check if occupied by another robot, or by a scripted obstacle.
            conflict = self._cell_is_scripted_blocked(agent, next_wp)
            if not conflict:
                for rid, pos in all_positions.items():
                    if rid != agent.robot_id and pos.x == next_wp.x and pos.y == next_wp.y:
                        conflict = True
                        break

            if conflict:
                agent.state.status = "WAITING"
                agent.state.velocity = 0.0
                agent._stall_ticks += 1
            else:
                agent.state.currentPath.pop(0)
                agent.state.position = Position(x=next_wp.x, y=next_wp.y)
                agent.state.status = "MOVING"
                agent.state.velocity = 1.0
                agent._stall_ticks = 0

            if (
                agent.state.destination
                and agent.state.position.x == agent.state.destination.x
                and agent.state.position.y == agent.state.destination.y
            ):
                agent.state.status = "IDLE"
                agent.state.velocity = 0.0
        else:
            agent.state.velocity = 0.0

        agent.state.timestamp = current_tick
        return agent.state

    def _step_centralized(self, agent: RobotAgent, current_tick: int) -> RobotState:
        """Centralized schedule execution: follow the pre-computed space-time
        schedule, unless the next cell was named by a scripted blocked-cell
        event that arose AFTER the schedule was computed — the schedule was
        built once, at run-start, with no knowledge of a later event, so
        discovering a physical obstruction on arrival simply halts execution
        (a physical floor, not a live replanning capability this baseline
        does not have). Never replans, never re-reserves — that is the
        entire point of this baseline."""
        self._apply_sensor_telemetry(agent, current_tick)
        if not agent.state or agent.state.status == "OFFLINE":
            if agent.state:
                agent.state.velocity = 0.0
                agent.state.timestamp = current_tick
            return agent.state

        if agent.state.currentPath and len(agent.state.currentPath) > 0:
            next_wp = agent.state.currentPath[0]
            if self._cell_is_scripted_blocked(agent, next_wp):
                agent.state.status = "WAITING"
                agent.state.velocity = 0.0
                agent._stall_ticks += 1
            else:
                agent.state.currentPath.pop(0)
                agent.state.position = Position(x=next_wp.x, y=next_wp.y)
                agent.state.status = "MOVING"
                agent.state.velocity = 1.0
                agent._stall_ticks = 0
                if (
                    agent.state.destination
                    and agent.state.position.x == agent.state.destination.x
                    and agent.state.position.y == agent.state.destination.y
                ):
                    agent.state.status = "IDLE"
                    agent.state.velocity = 0.0
        else:
            agent.state.velocity = 0.0

        agent.state.timestamp = current_tick
        return agent.state

    def _build_centralized_schedules(
        self, warehouse_map: WarehouseMap, robot_configs: list[dict], planner: GridAStarPlanner,
        seed: int = 42,
    ) -> dict[str, list[Position]]:
        """Sequential space-time reservation planning for CENTRALIZED_RESERVATION mode.

        `seed` is the run's actual seed and is forwarded to plan_centralized(),
        which uses it to shuffle the planning order. It used to be hardcoded to
        42 here, which silently made every seed produce an identical schedule.

        A genuine planning failure from plan_centralized() (PlanningFailedError
        because a robot cannot reach its goal given prior reservations, or
        InvalidMapError for a bad start/goal) is deliberately allowed to
        propagate rather than being silently swallowed and replaced by the
        weaker fallback table below. That fallback only does vertex-conflict
        avoidance (via GridAStarPlanner.plan()'s avoid_intervals) — it has no
        equivalent of plan_centralized's _astar_reserved() edge/swap-conflict
        check (see Known Bugs #5 in CLAUDE.md, the exact bug class that fix
        closed). Silently falling back here would mean a run reporting
        CENTRALIZED_RESERVATION could actually be collision-unsafe by
        construction, undermining the benchmark's own zero-collision claim.
        Only an ImportError — planner.centralized_baseline itself being
        unavailable, not a planning failure — takes the fallback path.
        Callers (e.g. the benchmark's per-combination try/except in
        simulation/benchmarks/benchmark.py::run_one) record a propagated
        planning failure as an explicit failed run, not a silent success.
        """
        try:
            from planner.centralized_baseline import plan_centralized
        except ImportError:
            pass
        else:
            start_goals = {r["robotId"]: (r["start"], r["goal"]) for r in robot_configs}
            return {rid: path.waypoints for rid, path in plan_centralized(start_goals, warehouse_map, seed).items()}

        # Fallback space-time reservation table — reached only when
        # planner.centralized_baseline cannot be imported at all.
        reserved: set[tuple[int, int, int]] = set()
        schedules: dict[str, list[Position]] = {}

        for r in robot_configs:
            rid = r["robotId"]
            start, goal = r["start"], r["goal"]
            avoid = [(Position(x=x, y=y), t) for (x, y, t) in reserved]
            path = planner.plan(start, goal, avoid_intervals=avoid, start_tick=0)
            wps = list(path.waypoints)
            for wp in wps:
                reserved.add((wp.x, wp.y, wp.tick if wp.tick is not None else 0))
            schedules[rid] = wps

        return schedules

    @staticmethod
    def _find_reassignment_target(agents: dict, robot_ids: list[str], exclude: str) -> str | None:
        """Return the robotId of the first available peer to hand a task to.

        "Available" means genuinely idle (status=="IDLE") and not itself the
        offline robot. Deterministic — always scans robot_ids in the
        scenario's own declared order, never randomly — so the same scenario
        + seed always reassigns to the same peer. Returns None (retry next
        tick) if no peer is currently free.
        """
        for rid in robot_ids:
            if rid == exclude:
                continue
            st = agents[rid].state
            if st and st.status == "IDLE":
                return rid
        return None

    @staticmethod
    def _reassign_task(target_agent: RobotAgent, offline_state: RobotState) -> None:
        """Hand an OFFLINE robot's unfinished destination/task to target_agent.

        This only supplies a new goal — exactly the same effect
        _apply_task_assignment() already has at run-start for a real Java
        TaskAssignment, just triggered mid-run instead. Clearing currentPath
        and setting _replan_requested makes the target's own RobotAgent.tick()
        replan on its very next tick via the existing _needs_replan() check;
        no new planning/negotiation logic is added, and every conflict/
        collision/deadlock decision for the target robot's actual movement
        toward this new goal is still made entirely by its own tick() from
        local peer intents, same as any other destination.
        """
        target_agent.state.destination = Position(x=offline_state.destination.x, y=offline_state.destination.y)
        target_agent.state.currentTaskId = offline_state.currentTaskId
        target_agent.state.currentPath = []
        target_agent.state.status = "MOVING"
        target_agent.state.velocity = 1.0
        target_agent._replan_requested = True

    @staticmethod
    def _apply_task_assignment(r: dict, assignments_by_robot: dict[str, dict]) -> dict:
        """Return r (a scenario robot config), with goal/taskId/priority
        overridden by a matching Java TaskAssignment if one was supplied.

        Only dropPosition is used to override movement — it's the final
        destination the RobotState.destination field already represents.
        pickupPosition/robotId are still accepted and would carry through
        should a future two-leg pickup-then-drop route be added, but no
        pickup-arrival state exists anywhere in agent.py today (an MVP
        deliberately doesn't add one — see final report). Returns r
        unchanged when no assignment exists for this robot, which is what
        preserves every existing no-assignment scenario's behavior exactly.
        """
        assignment = assignments_by_robot.get(r["robotId"])
        if not assignment:
            return r
        updated = dict(r)
        drop = assignment.get("dropPosition")
        if drop:
            updated["goal"] = Position(x=drop["x"], y=drop["y"])
        if assignment.get("taskId"):
            updated["taskId"] = assignment["taskId"]
        if assignment.get("priority") is not None:
            updated["priority"] = assignment["priority"]
        return updated

    @staticmethod
    def _warehouse_map_to_dict(wm: WarehouseMap) -> dict:
        def _pts(positions: list[Position]) -> list[dict]:
            return [{"x": p.x, "y": p.y, "tick": p.tick} for p in (positions or [])]

        return {
            "gridWidth": wm.gridWidth,
            "gridHeight": wm.gridHeight,
            "obstacles": _pts(wm.obstacles),
            "chokePoints": _pts(wm.chokePoints),
            "pickupPoints": _pts(wm.pickupPoints),
            "dropPoints": _pts(wm.dropPoints),
            "blockedCells": _pts(wm.blockedCells),
        }

    def _push_to_backend(self, endpoint: str, data: Any) -> None:
        """Resiliently push data to Java backend. Logs and continues if unreachable."""
        url = f"{self.backend_url.rstrip('/')}{endpoint}"
        try:
            payload = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=0.2) as resp:
                pass
        except Exception:
            # Backend unreachable — expected in standalone or resilient demo mode
            pass

    def _state_to_dict(self, state: RobotState) -> dict:
        return {
            "robotId": state.robotId,
            "position": {"x": state.position.x, "y": state.position.y, "tick": state.position.tick},
            "velocity": state.velocity,
            "battery": state.battery,
            "currentTaskId": state.currentTaskId,
            "destination": (
                {"x": state.destination.x, "y": state.destination.y} if state.destination else None
            ),
            "currentPath": [{"x": p.x, "y": p.y, "tick": p.tick} for p in state.currentPath],
            "status": state.status,
            "timestamp": state.timestamp,
        }


# ── Global Runner Instance & FastAPI Endpoints ───────────────────────────────
_runner = SimulationRunner()
_runner_thread: threading.Thread | None = None
_product_session = None  # type: "simulation.product.session.ProductSession | None"


if app is not None:
    @app.post("/control/start")
    async def control_start(body: dict):
        """Start a simulation run in the background."""
        global _runner_thread, _runner
        scenario_id = body.get("scenarioId", "a_normal")
        mode = body.get("mode", "DECENTRALIZED_PROPOSED")
        seed = body.get("seed", 42)
        speed = body.get("speed", "BATCH")
        # Optional, backward-compatible: existing callers sending only
        # {scenarioId, mode, seed, speed} are unaffected — absent/empty means
        # every robot uses its scenario-defined start/goal, exactly as before.
        task_assignments = body.get("taskAssignments") or None

        if _runner.running or (_product_session is not None and _product_session.running):
            return JSONResponse(status_code=400, content={"error": "Simulation is already running."})

        def _worker():
            _runner.run(scenario_id, mode=mode, seed=seed, speed=speed, task_assignments=task_assignments)

        _runner_thread = threading.Thread(target=_worker, daemon=True)
        _runner_thread.start()

        return {
            "message": "Simulation started",
            "scenarioId": scenario_id,
            "mode": mode,
            "speed": speed,
            "seed": seed,
        }

    @app.post("/control/stop")
    async def control_stop():
        """Stop the currently running simulation."""
        global _runner
        _runner.stop()
        return {"message": "Simulation stop signaled"}

    @app.get("/control/status")
    async def control_status():
        """Return current simulation status."""
        global _runner
        return {
            "running": _runner.running,
            "currentTick": _runner.current_tick,
            "scenarioId": _runner.scenario_id,
            "mode": _runner.mode,
        }

    # ── Product-mode routes ──────────────────────────────────────────────
    # Lazy-imported inside each handler (not at module top) so this file
    # never imports simulation.product at load time — simulation/product/
    # imports GridAStarPlanner/_MessageCountingTransport/_DeadlockCountingDetector
    # FROM this module, so a top-level import here would be circular. This
    # also keeps the benchmark/scenario code path (which imports this module
    # for SimulationRunner/GridAStarPlanner) from ever pulling in
    # simulation.product, and means these route bodies are the only
    # difference a diff of this file shows for Product mode — all actual
    # driver logic lives in simulation/product/.
    @app.post("/control/product/start")
    async def control_product_start(body: dict):
        global _product_session
        if _runner.running or (_product_session is not None and _product_session.running):
            return JSONResponse(status_code=400, content={"error": "Simulation is already running."})
        from simulation.product.session import ProductSession
        _product_session = ProductSession(backend_url=_runner.backend_url)
        seed = _product_session.start(
            seed=body.get("seed"), speed=body.get("speed", "BATCH"), config=body.get("config") or {}
        )
        return {"message": "Product session started", "sessionId": _product_session.session_id, "seed": seed}

    @app.post("/control/product/stop")
    async def control_product_stop():
        global _product_session
        if _product_session is not None:
            _product_session.stop()
        return {"message": "Product session stop signaled"}

    @app.post("/control/task")
    async def control_task(body: dict):
        if _product_session is None or not _product_session.running:
            return JSONResponse(status_code=400, content={"error": "No product session running."})
        _product_session.task_inbox.submit_assignment(body)
        return {"message": "Task assignment queued"}

    @app.post("/control/release")
    async def control_release(body: dict):
        if _product_session is None or not _product_session.running:
            return JSONResponse(status_code=400, content={"error": "No product session running."})
        _product_session.task_inbox.submit_release(body)
        return {"message": "Robot release queued"}

    @app.post("/control/recover")
    async def control_recover(body: dict):
        if _product_session is None or not _product_session.running:
            return JSONResponse(status_code=400, content={"error": "No product session running."})
        _product_session.task_inbox.submit_recover(body)
        return {"message": "Robot recovery queued"}

    @app.post("/control/inject")
    async def control_inject(body: dict):
        if _product_session is None or not _product_session.running:
            return JSONResponse(status_code=400, content={"error": "No product session running."})
        return _product_session.task_inbox.submit_injection(body)


if __name__ == "__main__":
    if app is not None:
        uvicorn.run("simulation.runner:app", host="0.0.0.0", port=8001, reload=False)
    else:
        print("FastAPI not installed. Running standalone scenario A batch demo...")
        metric = _runner.run("a_normal", mode="DECENTRALIZED_PROPOSED")
        print("Run finished:", metric)
