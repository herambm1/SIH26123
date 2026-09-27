"""simulation/product/session.py — the live, seeded "Product" driver.

Reuses the exact same real building blocks simulation.runner.SimulationRunner
already assembles for a scenario run (GridAStarPlanner, InProcessBus,
SimulationSensorSource, RobotAgent, ConflictDetector, ConflictResolver,
DeadlockDetector, CollisionReferee) — imported FROM simulation.runner, never
reimplemented. This module is NOT imported by simulation/scenarios/,
simulation/benchmarks/, or the scenario registry, and does not register a
scenario — a running ProductSession has no scenario_id at all.

Runs its own tick loop on a background thread (started by
POST /control/product/start, stopped by POST /control/product/stop or the
safety tick cap). Unlike SimulationRunner.run(), there is no scripted
scenario.events list and no scenario-driven mid-run reassignment sweep —
every task assignment and every world fault this driver ever applies comes
from an inbox fed by real HTTP calls (POST /control/task from Java,
POST /control/inject from a judge or Java), or from the session's own seeded
WorldFaultGenerator. Nothing here fabricates activity.

See docs/PRODUCT_MODE.md for the full real/simulated/deterministic breakdown.
"""

from __future__ import annotations

import json
import logging
import random
import threading
import time
import urllib.request
import uuid
from typing import Any

from shared.python.models import Position, RobotState, SimulationEvent, WarehouseMap
from collision_engine.deadlock import DeadlockDetector
from collision_engine.detection import ConflictDetector
from collision_engine.resolution import ConflictResolver
from robot_agent.agent import RobotAgent
from robot_agent.communication.transport import InProcessBus, MessageFaultConfig
from edge.sensor_source import SimulationSensorSource
from edge.fault_injection import SensorFaultConfig
from simulation.referee import CollisionReferee
from simulation.warehouse.demo_map import get_demo_map

# Reused, not reimplemented — the identical instrumentation wrappers and
# planner class simulation.runner.SimulationRunner already uses for every
# scenario run. Importing these here is why this module cannot be imported
# at simulation.runner's own module-load time (would be circular) — it is
# only ever imported lazily, from inside a FastAPI route handler, after
# simulation.runner has already finished loading.
from simulation.runner import GridAStarPlanner, _DeadlockCountingDetector

from simulation.product.envelope import (
    ORIGIN_JAVA_TASK,
    ORIGIN_PRODUCT_INJECTED_FAULT,
    ORIGIN_ROBOT_DECISION,
    ORIGIN_SYSTEM,
    event_to_wire,
    state_to_wire,
    tagged_event,
)
from simulation.product.task_inbox import TaskInbox
from simulation.product.world_faults import WorldFaultGenerator

logger = logging.getLogger("simulation.product.session")

_STALL_TICKS = 30
_DEFAULT_MAX_TICKS = 20000  # safety cap only — see class docstring
# Defense-in-depth reassignment cooldown — see ProductSession._apply_assignment
# for the full rationale. A small, deliberately conservative number of ticks
# (roughly "a tick or two" of margin beyond the one tick a fresh broadcast
# needs to reach a peer): long enough for a peer negotiating around a
# just-freed robot's last-known position to receive at least one broadcast
# reflecting its departure before that robot is redirected into a brand-new
# path, short enough to cost negligible real throughput.
_REASSIGNMENT_COOLDOWN_TICKS = 3


class _ObservingTransport:
    """Pure-delegation wrapper around a real InProcessBus.

    Same idiom as simulation.runner._MessageCountingTransport (message_count
    on top of unmodified delegation) plus one more purely observational
    capability: a per-tick, compact comm-flow record built by diffing the
    real bus's own _queues/_delay_buffers length BEFORE and AFTER calling
    the real, unmodified broadcast(). Every delivery/drop/delay DECISION
    already happened inside InProcessBus._enqueue() by the time this wrapper
    looks — it only reads the resulting queue lengths afterward, the same
    as inspecting the aftermath of a call that already fully executed. No
    order, content, or probability is altered.
    """

    def __init__(self, bus: InProcessBus, robot_ids: list[str]) -> None:
        self._bus = bus
        self._robot_ids = list(robot_ids)
        self.message_count: int = 0
        self._tick_records: list[dict] = []

    def broadcast(self, msg: dict) -> None:
        self.message_count += 1
        sender = msg.get("robotId")
        recipients = [rid for rid in self._robot_ids if rid != sender]
        before_q = {rid: len(self._bus._queues[rid]) for rid in recipients}
        before_d = {rid: len(self._bus._delay_buffers[rid]) for rid in recipients}
        self._bus.broadcast(msg)
        delivered = delayed = dropped = 0
        for rid in recipients:
            if len(self._bus._queues[rid]) > before_q[rid]:
                delivered += 1
            elif len(self._bus._delay_buffers[rid]) > before_d[rid]:
                delayed += 1
            else:
                dropped += 1
        self._tick_records.append({
            "sender": sender,
            "recipients": len(recipients),
            "plannedPathLen": len(msg.get("plannedPath") or []),
            "status": msg.get("status"),
            "delivered": delivered,
            "delayed": delayed,
            "dropped": dropped,
        })

    def send(self, to: str, msg: dict) -> None:
        self.message_count += 1
        self._bus.send(to, msg)

    def receive(self, robot_id: str) -> list[dict]:
        return self._bus.receive(robot_id)

    def advance_tick(self) -> None:
        self._bus.advance_tick()

    def drain_comm_records(self) -> list[dict]:
        records, self._tick_records = self._tick_records, []
        return records


class _ObservingConflictDetector:
    """Pure-delegation wrapper around a real ConflictDetector.

    Captures the last Conflict object (or None) returned by detect() so the
    session's NEGOTIATION-event enrichment can read its EXISTING fields
    (type, predictedCell, predictedTick — see shared/python/models.py's
    Conflict dataclass) after RobotAgent.tick() has already run. No new
    field is added to Conflict; nothing is inferred; a "deciding rule id"
    is deliberately NOT exposed here (no such field exists on Conflict, and
    adding one is a Tier A change that was not approved for this pass).
    """

    def __init__(self, detector: ConflictDetector) -> None:
        self._detector = detector
        self.last_conflict = None

    def detect(self, own_state, own_path, peer_intents):
        self.last_conflict = self._detector.detect(own_state, own_path, peer_intents)
        return self.last_conflict

    def __getattr__(self, name):
        return getattr(self._detector, name)


class ProductSession:
    """One live, seeded, continuously-running Product-mode session.

    DECENTRALIZED_PROPOSED only, real simulation/warehouse/demo_map.py,
    4-6 robots — per the Product-mode design brief. There is no
    scenario_id: robots start IDLE at distinct pickup-point cells with no
    destination, and only move once a real task assignment arrives via
    POST /control/task (Java-authoritative in product mode — this driver
    never invents a destination for a robot on its own initiative). World
    faults come only from POST /control/inject or this session's own seeded
    WorldFaultGenerator, both gated by the same guard checks.
    """

    def __init__(self, backend_url: str = "http://localhost:8080") -> None:
        self.backend_url = backend_url
        self.session_id = f"product_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        self.running: bool = False
        self.current_tick: int = 0
        self.seed: int | None = None
        self.collision_count: int = 0
        # Shared with every robot's _DeadlockCountingDetector instance (see
        # _run_inner) — {"count": N}, tallying real DeadlockDetector.check()
        # activations across the whole fleet, exactly like
        # simulation.runner.SimulationRunner already does for
        # PerformanceMetric.deadlockCount. Not exposed at all until this
        # fix — found missing while instrumenting the Phase 3 soak test.
        self.deadlock_activations: dict[str, int] = {"count": 0}
        self.task_inbox = TaskInbox()
        # Set by _run_inner once the session's WorldFaultGenerator exists; _apply_recover needs it to free the
        # robot's permanently held ROBOT_OFFLINE slot.
        self._world_faults: WorldFaultGenerator | None = None

        self._stop_requested = False
        self._thread: threading.Thread | None = None
        self.events: list[SimulationEvent] = []
        self._pushed_event_count = 0
        self.agents: dict[str, RobotAgent] = {}
        self._detector_wrappers: dict[str, _ObservingConflictDetector] = {}
        self._logged_push_failures: set[tuple[str, str]] = set()

    # ── Lifecycle ────────────────────────────────────────────────────────

    def start(self, seed: int | None, speed: str, config: dict) -> int:
        seed = int(seed) if seed is not None else random.SystemRandom().randrange(1, 2**31 - 1)
        self.seed = seed
        self.running = True
        self._stop_requested = False
        self.current_tick = 0
        self._thread = threading.Thread(target=self._run, args=(seed, speed, config), daemon=True)
        self._thread.start()
        return seed

    def stop(self) -> None:
        self._stop_requested = True

    # ── Setup + tick loop ────────────────────────────────────────────────

    def _run(self, seed: int, speed: str, config: dict) -> None:
        try:
            self._run_inner(seed, speed, config)
        finally:
            self.running = False

    def _run_inner(self, seed: int, speed: str, config: dict) -> None:
        rng = random.Random(f"product_roster:{seed}")
        robot_count = max(4, min(6, int(config.get("robotCount", 5))))
        max_ticks = int(config.get("maxTicks", _DEFAULT_MAX_TICKS))
        speed_multiplier = max(1, min(4, int(config.get("speedMultiplier", 1))))

        warehouse_map: WarehouseMap = get_demo_map()
        starts = self._pick_start_positions(warehouse_map, robot_count, rng)
        # "PR" (Product Robot), never "R" — every scenario file names its
        # robots R1, R2, ... and RobotEntity/RobotCacheService on the Java
        # side are keyed by robotId globally, never cleared between runs
        # (found by reading RobotCacheService directly during Phase 2
        # design). Sharing the "R{n}" namespace would let a stale scenario
        # robot's cached status/position be picked up by
        # TaskAllocationService.nearestIdleRobot() during a later product
        # session, or vice versa. A distinct namespace makes that
        # structurally impossible rather than relying on timing.
        robot_ids = [f"PR{i + 1}" for i in range(robot_count)]

        planner = GridAStarPlanner(warehouse_map)
        bus = InProcessBus(robot_ids, fault_config=MessageFaultConfig(drop_rate=0.0, delay_ticks=0), rng=random.Random(f"product_bus:{seed}"))
        transport = _ObservingTransport(bus, robot_ids)

        gt_positions: dict[str, Position] = {rid: Position(x=p.x, y=p.y) for rid, p in zip(robot_ids, starts)}

        def _ground_truth(rid: str) -> Position:
            return gt_positions.get(rid, Position(x=0, y=0))

        self.deadlock_activations = {"count": 0}  # fresh per run, same object every robot's wrapper shares
        deadlock_activations = self.deadlock_activations
        self.agents = {}
        self._detector_wrappers = {}
        # Reassignment-cooldown bookkeeping — see _apply_assignment.
        self._robot_idle_since: dict[str, int] = {}
        self._deferred_assignments: dict[str, dict] = {}
        for rid, start_pos in zip(robot_ids, starts):
            raw_detector = ConflictDetector()
            detector = _ObservingConflictDetector(raw_detector)
            self._detector_wrappers[rid] = detector
            resolver = ConflictResolver()
            deadlock = _DeadlockCountingDetector(DeadlockDetector(stall_threshold=5), deadlock_activations)
            sensor = SimulationSensorSource(_ground_truth, SensorFaultConfig(), rng=random.Random(f"product_sensor:{seed}:{rid}"))

            agent = RobotAgent(robot_id=rid, planner=planner, transport=transport, sensor=sensor, detector=detector, resolver=resolver, deadlock=deadlock)
            agent.state = RobotState(
                robotId=rid,
                position=Position(x=start_pos.x, y=start_pos.y),
                velocity=0.0,
                battery=100.0,
                currentTaskId=None,
                destination=None,
                currentPath=[],
                status="IDLE",
                timestamp=0,
            )
            setattr(agent.state, "task_priority", 1)
            self.agents[rid] = agent

        world_faults = WorldFaultGenerator(seed=seed)
        self._world_faults = world_faults
        self._push_to_backend("/api/warehouse", self._warehouse_map_to_dict(warehouse_map))

        last_negotiation_action: dict[str, str | None] = {}
        last_move_tick = 0
        last_task_complete_tick = 0
        stall_reported = False

        for tick in range(1, max_ticks + 1):
            if self._stop_requested:
                break
            self.current_tick = tick

            # 0. Drain Java-originated robot RELEASES (an abandoned, stalled
            # task's robot — see _apply_release). Before assignments, so a
            # release and a fresh assignment for the same robot arriving
            # together apply in the order Java issued them.
            for body in self.task_inbox.drain_releases():
                self._apply_release(body, tick)
            # 0b. Manual recovery of a broken-down (ROBOT_OFFLINE) robot — see _apply_recover.
            for body in self.task_inbox.drain_recoveries():
                self._apply_recover(body, tick)

            # 1. Drain Java-originated task assignments — the ONLY way a
            # robot in a product session is ever given a destination.
            for body in self.task_inbox.drain_assignments():
                self._apply_assignment(body, tick)

            # 1b. Apply any assignment that was deferred by the
            # reassignment cooldown (see _apply_assignment) once enough
            # ticks have passed since that robot went idle.
            for rid in list(self._deferred_assignments.keys()):
                idle_since = self._robot_idle_since.get(rid, -_REASSIGNMENT_COOLDOWN_TICKS)
                if tick - idle_since >= _REASSIGNMENT_COOLDOWN_TICKS:
                    self._do_apply_assignment(self._deferred_assignments.pop(rid), tick)

            # 2. Drain manual injection requests (judge click or Java proxy).
            for body in self.task_inbox.drain_injections():
                self._apply_manual_injection(body, tick, world_faults, gt_positions, planner, bus)

            # 3. Seeded auto-generation (same guarded apply methods as manual).
            result = world_faults.maybe_generate(tick, self.agents, gt_positions, planner, bus)
            if result is not None:
                kind, detail, error = result
                if error:
                    self._append_event(tagged_event(
                        f"fault_skip_{tick}_{kind}", "SYSTEM", tick,
                        {"reason": f"{kind} skipped: {error}"}, session_id=self.session_id, origin=ORIGIN_SYSTEM,
                    ))
                else:
                    self._emit_fault_applied_event(kind, detail, tick, manual=False)

            # 3b. Clear any expired timed faults.
            for cell in world_faults.clear_expired_aisle_blocks(tick, self.agents):
                self._append_event(tagged_event(
                    f"aisle_clear_{tick}_{cell[0]}_{cell[1]}", "AISLE_CLEARED", tick,
                    {"cell": {"x": cell[0], "y": cell[1]}}, session_id=self.session_id, origin=ORIGIN_PRODUCT_INJECTED_FAULT,
                ))
            if world_faults.clear_expired_comm_delay(tick, bus):
                self._append_event(tagged_event(
                    f"comm_delay_end_{tick}", "COMM_DELAY_ENDED", tick, {}, session_id=self.session_id, origin=ORIGIN_PRODUCT_INJECTED_FAULT,
                ))

            # 4. Advance delayed messages.
            transport.advance_tick()

            # 5. Step every robot — real RobotAgent.tick(), nothing bypassed.
            tick_states: list[RobotState] = []
            any_moved = False
            for rid in robot_ids:
                agent = self.agents[rid]
                prev_status = agent.state.status
                prev_task_id = agent.state.currentTaskId
                prev_pos = (agent.state.position.x, agent.state.position.y)

                state = agent.tick(tick)
                gt_positions[rid] = Position(x=state.position.x, y=state.position.y)
                tick_states.append(state)

                if (state.position.x, state.position.y) != prev_pos:
                    any_moved = True

                self._emit_negotiation_if_changed(rid, agent, self._detector_wrappers[rid], tick, last_negotiation_action)

                if prev_status != "IDLE" and state.status == "IDLE" and prev_task_id:
                    self._append_event(tagged_event(
                        f"complete_{tick}_{rid}", "TASK_COMPLETED", tick,
                        {"robotId": rid, "taskId": prev_task_id}, session_id=self.session_id, origin=ORIGIN_SYSTEM,
                    ))
                    last_task_complete_tick = tick
                    self._robot_idle_since[rid] = tick

            if any_moved:
                last_move_tick = tick

            # 6. Comm-flow observability (compact, one event per tick with activity).
            comm_records = transport.drain_comm_records()
            if comm_records:
                self._append_event(tagged_event(
                    f"comm_{tick}", "COMM_FLOW", tick, {"records": comm_records}, session_id=self.session_id, origin=ORIGIN_SYSTEM,
                ))

            # 7. Independent ground-truth collision check — never suppressed.
            collisions = self.referee_check(gt_positions)
            for r1, r2 in collisions:
                self.collision_count += 1
                self._append_event(tagged_event(
                    f"coll_{tick}_{r1}_{r2}", "CONFLICT_DETECTED", tick,
                    {"robotIds": [r1, r2], "collision": True, "cumulativeCollisionCount": self.collision_count},
                    session_id=self.session_id, origin=ORIGIN_SYSTEM,
                ))

            # 8. Stall watchdog — reported once per stall episode, never masked.
            if tick - max(last_move_tick, last_task_complete_tick) >= _STALL_TICKS:
                if not stall_reported:
                    self._append_event(tagged_event(
                        f"stall_{tick}", "SYSTEM", tick,
                        {"reason": f"no robot has moved and no task has completed in the last {_STALL_TICKS} ticks"},
                        session_id=self.session_id, origin=ORIGIN_SYSTEM,
                    ))
                    stall_reported = True
            else:
                stall_reported = False

            # 9. Push DELTAS only — never the accumulated event list.
            self._push_to_backend("/api/telemetry/batch", [state_to_wire(s) for s in tick_states])
            new_events = self.events[self._pushed_event_count:]
            self._pushed_event_count = len(self.events)
            if new_events:
                self._push_to_backend("/api/events", [event_to_wire(e) for e in new_events])

            if speed == "LIVE":
                time.sleep(0.5 / speed_multiplier)

    @property
    def deadlock_count(self) -> int:
        """Real DeadlockDetector.check()==True activations across the whole
        fleet, this run — same semantics as PerformanceMetric.deadlockCount
        in the scenario/benchmark path (simulation.runner._DeadlockCountingDetector)."""
        return self.deadlock_activations.get("count", 0)

    # ── Referee (external cumulative tally — CollisionReferee itself has
    # no running counter; this mirrors exactly how simulation.runner already
    # tallies it into PerformanceMetric.collisionCount, no Tier A change to
    # simulation/referee.py) ────────────────────────────────────────────────

    def referee_check(self, gt_positions: dict[str, Position]) -> list:
        if not hasattr(self, "_referee"):
            self._referee = CollisionReferee()
        return self._referee.check(gt_positions)

    # ── Task assignment (Java-authoritative) ────────────────────────────

    def _apply_assignment(self, body: dict, tick: int) -> None:
        """Validate an incoming assignment and either apply it immediately
        or defer it briefly under the reassignment cooldown (see
        _REASSIGNMENT_COOLDOWN_TICKS)."""
        rid = body.get("robotId")
        agent = self.agents.get(rid)
        if agent is None or not agent.state:
            self._append_event(tagged_event(
                f"assign_rej_{tick}_{rid}", "SYSTEM", tick,
                {"reason": f"assignment rejected: unknown robotId {rid!r}", "requested": body},
                session_id=self.session_id, origin=ORIGIN_SYSTEM,
            ))
            return
        if agent.state.status == "OFFLINE":
            self._append_event(tagged_event(
                f"assign_rej_{tick}_{rid}", "SYSTEM", tick,
                {"reason": f"assignment rejected: {rid} is OFFLINE (no live recovery — see docs/PRODUCT_MODE.md)", "requested": body},
                session_id=self.session_id, origin=ORIGIN_SYSTEM,
            ))
            return
        drop = body.get("dropPosition")
        if not drop or "x" not in drop or "y" not in drop:
            self._append_event(tagged_event(
                f"assign_rej_{tick}_{rid}", "SYSTEM", tick,
                {"reason": "assignment rejected: missing/invalid dropPosition", "requested": body},
                session_id=self.session_id, origin=ORIGIN_SYSTEM,
            ))
            return

        # Defense-in-depth reassignment cooldown (Phase 3, added alongside —
        # not instead of — the actual root-cause fix, which is
        # start_tick=current_tick-1 in robot_agent/agent.py::tick(); that
        # fix aligns replanned-path ticks with the real clock so
        # ConflictDetector can compare them correctly again. This is a
        # SECOND, independent, non-Tier-A layer: a robot that just went
        # IDLE may still have peers whose most recently RECEIVED broadcast
        # intent for it reflects its old position/path — a peer's own
        # tick() this same tick reads whatever was queued for it, which can
        # be one or more ticks stale. Reassigning the just-freed robot
        # INSTANTLY forces a brand-new replan before such a peer has had a
        # chance to receive a broadcast reflecting the departure — exactly
        # the mechanism the seed=57 repro traced in this session's Phase 3
        # report (PR2/PR3 swapped cells the tick immediately after PR2 was
        # reassigned the instant it went idle). Deferring a few ticks costs
        # negligible throughput and lets normal peer-intent broadcast catch
        # up first. Only applies to a robot that has ACTUALLY completed a
        # real task before (self._robot_idle_since is only ever set there)
        # — the very first assignment of a session, to a robot that has
        # never moved, is never delayed, since no peer could possibly be
        # negotiating around a robot that hasn't done anything yet.
        idle_since = self._robot_idle_since.get(rid)
        if idle_since is not None and tick - idle_since < _REASSIGNMENT_COOLDOWN_TICKS:
            self._deferred_assignments[rid] = body
            self._append_event(tagged_event(
                f"assign_defer_{tick}_{rid}", "SYSTEM", tick,
                {
                    "reason": f"assignment for {rid} deferred {_REASSIGNMENT_COOLDOWN_TICKS - (tick - idle_since)} "
                              "more tick(s) — reassignment cooldown (defense in depth, see ProductSession docstring)",
                    "requested": body,
                },
                session_id=self.session_id, origin=ORIGIN_SYSTEM,
            ))
            return

        self._do_apply_assignment(body, tick)

    def _apply_release(self, body: dict, tick: int) -> None:
        """Release a robot whose task Java has abandoned as stalled.

        Backlog-freeze fix (see docs/PRODUCT_MODE_INVESTIGATION_STATUS.md,
        "Backlog freeze"): a robot that strands (RobotAgent's avoid-cell list
        never expires, so it eventually has no route) used to hold one of
        ProductSessionService's MAX_BACKLOG slots forever; three stranded
        robots froze task generation for the rest of the session. Java now
        abandons a task whose robot has not moved for STALL_ABANDON_TICKS and
        sends this request so the robot can take new work instead of staying
        stranded.

        Product-mode only; robot_agent/ is not touched. Only attributes that
        RobotAgent itself already exposes as externally settable (the same
        pattern _do_apply_assignment uses for _replan_requested) are reset.
        Guards — every one of these leaves the robot untouched:
          * unknown robot, or an OFFLINE / sensor-dead robot (a dead robot must
            never be resurrected as IDLE — the reason it is checked via the
            sensor fault config too, since a dead robot's agent status is not
            sticky: a REASSIGN_TASK verdict can leave it BLOCKED);
          * the robot is already IDLE, or is no longer on the task Java
            abandoned (it finished, or was handed something else, in between).
        """
        rid = body.get("robotId")
        task_id = body.get("taskId")
        agent = self.agents.get(rid)

        def _reject(reason: str) -> None:
            self._append_event(tagged_event(
                f"release_rej_{tick}_{rid}", "SYSTEM", tick,
                {"reason": f"robot release ignored: {reason}", "requested": body},
                session_id=self.session_id, origin=ORIGIN_SYSTEM,
            ))

        if agent is None or not agent.state:
            _reject(f"unknown robotId {rid!r}")
            return
        offline_after = getattr(agent.sensor.fault_config, "offline_after_tick", None)
        if agent.state.status == "OFFLINE" or (offline_after is not None and tick >= offline_after):
            _reject(f"{rid} is OFFLINE")
            return
        if agent.state.status == "IDLE":
            _reject(f"{rid} is already IDLE")
            return
        if task_id and agent.state.currentTaskId != task_id:
            _reject(f"{rid} is no longer on task {task_id!r}")
            return

        self._reset_agent_to_idle(agent, rid, tick)

        self._append_event(tagged_event(
            f"release_{tick}_{rid}", "SYSTEM", tick,
            {"reason": f"{rid} released from stalled task {task_id!r} (abandoned by the task orchestrator); "
                       "avoid-cell and wait state cleared, robot is IDLE and available for a new task",
             "robotId": rid, "taskId": task_id},
            session_id=self.session_id, origin=ORIGIN_SYSTEM,
        ))

    def _reset_agent_to_idle(self, agent: RobotAgent, rid: str, tick: int) -> None:
        """Shared by _apply_release and _apply_recover: clear the agent's avoid-cell and wait state, drop any task,
        destination and path, and set it IDLE. The robot's POSITION is never touched."""
        agent._temporary_avoid_cells = []
        agent._waiting_on = None
        agent._blocked_by_peer = None
        agent._stall_ticks = 0
        agent._replan_requested = False
        self._deferred_assignments.pop(rid, None)
        agent.state.destination = None
        agent.state.currentTaskId = None
        agent.state.currentPath = []
        agent.state.status = "IDLE"
        agent.state.velocity = 0.0
        # Same cooldown bookkeeping as a normal completion: a peer may hold a
        # stale broadcast for this robot, so do not re-task it this same tick.
        self._robot_idle_since[rid] = tick

    def _apply_recover(self, body: dict, tick: int) -> None:
        """Manually recover a broken-down robot ("Mark as fixed"; Java: POST /api/product/robot/{id}/fix).

        Why Python has to act (probe, docs/PRODUCT_MODE_INVESTIGATION_STATUS.md section 11): ROBOT_OFFLINE sets the
        sensor's offline_after_tick, so EVERY later sensor read re-marks the agent OFFLINE; agent.py never clears
        OFFLINE itself; _apply_assignment rejects OFFLINE robots; and the robot holds one of the fault generator's
        max_concurrent slots forever. A Java-side label change alone therefore cannot make the robot usable.

        Does: clear the sensor fault, free the robot's fault slot, and reset the agent exactly as _apply_release does
        (IDLE, no task/destination/path, avoid-cell and wait state cleared). Does NOT: move or relocate the robot
        (position and ground truth untouched), touch robot_agent/ or collision_engine/, or assign anything - the
        robot simply becomes selectable by Java's existing allocator once its telemetry reads IDLE. A robot that is
        not currently broken down is left untouched, with a SYSTEM event saying why.
        """
        rid = body.get("robotId")
        agent = self.agents.get(rid)

        def _reject(reason: str) -> None:
            self._append_event(tagged_event(
                f"recover_rej_{tick}_{rid}", "SYSTEM", tick,
                {"reason": f"robot recovery ignored: {reason}", "requested": body},
                session_id=self.session_id, origin=ORIGIN_SYSTEM,
            ))

        if agent is None or not agent.state:
            _reject(f"unknown robotId {rid!r}")
            return
        fault = agent.sensor.fault_config
        offline_after = getattr(fault, "offline_after_tick", None)
        fault_dead = offline_after is not None and tick >= offline_after
        if not fault_dead and agent.state.status != "OFFLINE":
            _reject(f"{rid} is not broken down")
            return

        fault.offline_after_tick = None
        if self._world_faults is not None:
            self._world_faults.active_offline_robots.discard(rid)
        self._reset_agent_to_idle(agent, rid, tick)

        self._append_event(tagged_event(
            f"recover_{tick}_{rid}", "SYSTEM", tick,
            {"reason": f"{rid} recovered (marked as fixed): sensor fault cleared, robot is IDLE where it stopped "
                       "and available for a new task",
             "robotId": rid},
            session_id=self.session_id, origin=ORIGIN_SYSTEM,
        ))

    def _do_apply_assignment(self, body: dict, tick: int) -> None:
        """The actual mutation — called either immediately from
        _apply_assignment, or later once a deferred assignment's cooldown
        has expired (see the tick loop's step 1b). Re-validates robot/
        OFFLINE state defensively, since a deferred assignment's target may
        have gone OFFLINE (or vanished) during the deferral window."""
        rid = body.get("robotId")
        agent = self.agents.get(rid)
        if agent is None or not agent.state or agent.state.status == "OFFLINE":
            self._append_event(tagged_event(
                f"assign_rej_{tick}_{rid}", "SYSTEM", tick,
                {"reason": f"deferred assignment for {rid!r} could no longer be applied (robot unknown or went OFFLINE during the cooldown)", "requested": body},
                session_id=self.session_id, origin=ORIGIN_SYSTEM,
            ))
            return
        drop = body["dropPosition"]

        # Same mutate-then-replan-request pattern
        # simulation.runner.SimulationRunner._reassign_task already uses for
        # scenario f_task_reassignment's mid-run handoff, generalized here to
        # any robot at any time (not only an OFFLINE robot's peer) — nothing
        # in robot_agent/agent.py is touched; _replan_requested is an
        # existing, externally-settable attribute agent.py's own
        # _needs_replan() already checks every tick.
        agent.state.destination = Position(x=drop["x"], y=drop["y"])
        task_id = body.get("taskId")
        if task_id:
            agent.state.currentTaskId = task_id
        priority = body.get("priority")
        if priority is not None:
            setattr(agent.state, "task_priority", priority)
        agent.state.currentPath = []
        agent.state.status = "MOVING"
        agent.state.velocity = 1.0
        agent._replan_requested = True

        self._append_event(tagged_event(
            f"assign_{tick}_{rid}", "TASK_ASSIGNED", tick,
            {"robotId": rid, "taskId": task_id, "dropPosition": drop, "priority": priority},
            session_id=self.session_id, origin=ORIGIN_JAVA_TASK,
        ))

    # ── Manual injection (judge click / Java proxy — same guards as auto) ──

    def _apply_manual_injection(self, body: dict, tick: int, world_faults: WorldFaultGenerator, gt_positions: dict, planner, bus) -> None:
        from simulation.product.world_faults import FaultGuardRejected

        kind = body.get("kind")
        try:
            if kind == "AISLE_BLOCK":
                cell = body.get("cell") or {}
                cell_tuple = (int(cell.get("x")), int(cell.get("y")))
                world_faults.try_apply_aisle_block(tick, cell_tuple, self.agents, gt_positions, planner)
                self._emit_fault_applied_event("AISLE_BLOCK", {"cell": cell_tuple}, tick, manual=True)
            elif kind == "ROBOT_OFFLINE":
                rid = body.get("robotId")
                world_faults.try_apply_robot_offline(tick, rid, self.agents)
                self._emit_fault_applied_event("ROBOT_OFFLINE", {"robotId": rid}, tick, manual=True)
            elif kind == "COMM_DELAY":
                world_faults.try_apply_comm_delay(tick, bus, gt_positions)
                self._emit_fault_applied_event("COMM_DELAY", {"delayTicks": 1, "episodeTicks": world_faults.comm_delay_episode_ticks}, tick, manual=True)
            else:
                raise FaultGuardRejected(f"unknown injection kind {kind!r}")
        except FaultGuardRejected as e:
            self._append_event(tagged_event(
                f"inject_rej_{tick}_{kind}", "SYSTEM", tick,
                {"reason": f"{kind} injection rejected: {e}", "requested": body},
                session_id=self.session_id, origin=ORIGIN_SYSTEM,
            ))

    def _emit_fault_applied_event(self, kind: str, detail: dict, tick: int, *, manual: bool) -> None:
        payload = dict(detail)
        payload["manual"] = manual
        event_type = {"AISLE_BLOCK": "AISLE_BLOCKED", "ROBOT_OFFLINE": "ROBOT_UNAVAILABLE", "COMM_DELAY": "COMM_DELAY_STARTED"}[kind]
        self._append_event(tagged_event(
            f"fault_{tick}_{kind}", event_type, tick, payload, session_id=self.session_id, origin=ORIGIN_PRODUCT_INJECTED_FAULT,
        ))

    # ── Negotiation enrichment ───────────────────────────────────────────

    def _emit_negotiation_if_changed(self, rid: str, agent: RobotAgent, detector: _ObservingConflictDetector, tick: int, last_negotiation_action: dict) -> None:
        """Same change-only-emit idiom as
        simulation.runner.SimulationRunner._emit_negotiation_if_changed,
        enriched with the real Conflict object's own existing fields
        (captured by _ObservingConflictDetector — no new Conflict field, no
        deciding-rule-id, per the approved Phase 0 scope)."""
        action = getattr(agent, "_action_this_tick", None)
        if action is None or last_negotiation_action.get(rid) == action:
            return
        last_negotiation_action[rid] = action
        peer_id = getattr(agent, "_waiting_on", None) or getattr(agent, "_blocked_by_peer", None)
        payload: dict[str, Any] = {"robotId": rid, "peerRobotId": peer_id, "resolutionAction": action}

        conflict = detector.last_conflict
        if conflict is not None:
            payload["conflictType"] = conflict.type
            if conflict.predictedCell is not None:
                payload["contestedCell"] = {"x": conflict.predictedCell.x, "y": conflict.predictedCell.y}
            payload["predictedTick"] = conflict.predictedTick
            payload["ownPriority"] = int(getattr(agent.state, "task_priority", 1) or 1)
            if peer_id:
                payload["peerPriority"] = int(agent._peer_priorities.get(peer_id, 1))

        self._append_event(tagged_event(
            f"neg_{tick}_{rid}_{action}", "NEGOTIATION", tick, payload, session_id=self.session_id, origin=ORIGIN_ROBOT_DECISION,
        ))

    # ── Small helpers ────────────────────────────────────────────────────

    def _append_event(self, event: SimulationEvent) -> None:
        self.events.append(event)

    @staticmethod
    def _pick_start_positions(warehouse_map: WarehouseMap, robot_count: int, rng: random.Random) -> list[Position]:
        pool = list(warehouse_map.pickupPoints) or []
        if len(pool) < robot_count:
            obstacles = {(o.x, o.y) for o in warehouse_map.obstacles}
            pool = [Position(x=x, y=y) for y in range(warehouse_map.gridHeight) for x in range(warehouse_map.gridWidth) if (x, y) not in obstacles]
        if len(pool) >= robot_count:
            return rng.sample(pool, robot_count)
        return [pool[i % len(pool)] for i in range(robot_count)]

    @staticmethod
    def _warehouse_map_to_dict(wm: WarehouseMap) -> dict:
        def _pts(positions):
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
        """Duplicated (not imported) from
        simulation.runner.SimulationRunner._push_to_backend — a small leaf
        function with no agent/detector/resolver equivalent to delegate to,
        unlike _apply_sensor_telemetry-style reuse elsewhere in this
        package. Same resilience behavior (never lets a backend-push
        failure crash the tick loop, same 0.2s timeout, same JSON POST
        shape) — but unlike the original, which has a bare `except
        Exception: pass` with no actual log call despite its own docstring
        claiming "Logs and continues" (found reading it during Phase 0),
        this one actually logs. A silent product session could otherwise
        run for a long time pushing nothing to Java with no visible reason
        why. Rate-limited to once per (endpoint, exception type) per
        session, not once per tick, so a genuinely-down backend doesn't
        spam the log every tick for a potentially very long-running
        session. This fix is scoped to this new push path only — the
        original simulation.runner.SimulationRunner._push_to_backend is
        untouched."""
        url = f"{self.backend_url.rstrip('/')}{endpoint}"
        try:
            payload = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=0.2):
                pass
        except Exception as e:
            key = (endpoint, type(e).__name__)
            if key not in self._logged_push_failures:
                self._logged_push_failures.add(key)
                logger.warning(
                    "Product session %s: backend push to %s failed (%s: %s) — will keep retrying silently for this failure type; session continues.",
                    self.session_id, endpoint, type(e).__name__, e,
                )
