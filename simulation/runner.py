import heapq
import json
import logging
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
    Telemetry,
    WarehouseMap,
)
from collision_engine.deadlock import DeadlockDetector
from collision_engine.detection import ConflictDetector
from collision_engine.resolution import ConflictResolver
from robot_agent.agent import RobotAgent
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


# ── In-process Transport fallback for parallel development ───────────────────
class MockInProcessBus:
    """Deterministic in-process transport conforming to Member 2's Transport interface."""

    def __init__(self, robot_ids: list[str], delay_ticks: int = 0):
        self.robot_ids = list(robot_ids)
        self.delay_ticks = delay_ticks
        self._queues: dict[str, list[dict]] = {rid: [] for rid in self.robot_ids}
        self._delayed: list[tuple[int, str, dict]] = []  # (release_tick, to, msg)
        self.message_count: int = 0

    def broadcast(self, msg: dict) -> None:
        sender = msg.get("robotId")
        self.message_count += 1
        for rid in self.robot_ids:
            if rid != sender:
                if self.delay_ticks > 0:
                    self._delayed.append((self.delay_ticks, rid, msg))
                else:
                    self._queues[rid].append(msg)

    def send(self, to: str, msg: dict) -> None:
        self.message_count += 1
        if to in self._queues:
            if self.delay_ticks > 0:
                self._delayed.append((self.delay_ticks, to, msg))
            else:
                self._queues[to].append(msg)

    def receive(self, robot_id: str) -> list[dict]:
        msgs = list(self._queues.get(robot_id, []))
        self._queues[robot_id] = []
        return msgs

    def advance_tick(self) -> None:
        still_delayed = []
        for remaining, to, msg in self._delayed:
            if remaining <= 1:
                if to in self._queues:
                    self._queues[to].append(msg)
            else:
                still_delayed.append((remaining - 1, to, msg))
        self._delayed = still_delayed


# ── SensorSource fallback for parallel development ───────────────────────────
class MockSensorSource:
    """Sensor source conforming to Member 5's SensorSource interface."""

    def __init__(self, ground_truth_fn, offline_schedule: dict[str, int] | None = None):
        self.ground_truth_fn = ground_truth_fn
        self.offline_schedule = offline_schedule or {}

    def read(self, robot_id: str, current_tick: int) -> Telemetry:
        offline_at = self.offline_schedule.get(robot_id)
        is_offline = offline_at is not None and current_tick >= offline_at
        pos = self.ground_truth_fn(robot_id)
        return Telemetry(
            robotId=robot_id,
            position=pos,
            battery=0.0 if is_offline else 95.0,
            obstacleDetected=False,
            sensorHealth="OFFLINE" if is_offline else "OK",
            tick=current_tick,
        )


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
    ) -> PerformanceMetric:
        """Execute a scenario run synchronously and return the resulting PerformanceMetric."""
        self.scenario_id = scenario_id
        self.mode = mode
        self.running = True
        self._stop_requested = False
        self.current_tick = 0
        self.events = []
        self.referee = CollisionReferee()

        scenario = get_scenario(scenario_id, seed, warehouse_map=warehouse_map)
        sim_max_ticks = max_ticks or scenario.max_ticks

        robot_configs = scenario.robots
        robot_ids = [r["robotId"] for r in robot_configs]

        # Initialize planner
        planner = GridAStarPlanner(scenario.warehouse_map)

        # Initialize transport
        delay_ticks = scenario.fault_config.get("delay_ticks", 0)
        transport = MockInProcessBus(robot_ids, delay_ticks=delay_ticks)

        # Ground truth position map
        gt_positions: dict[str, Position] = {
            r["robotId"]: Position(x=r["start"].x, y=r["start"].y) for r in robot_configs
        }

        # Initialize sensor source
        sensor = MockSensorSource(
            lambda rid: gt_positions.get(rid, Position(x=0, y=0)),
            scenario.fault_config.get("offline_robots", {}),
        )

        # Construct agents
        agents: dict[str, RobotAgent] = {}
        for r in robot_configs:
            rid = r["robotId"]
            detector = ConflictDetector()
            resolver = ConflictResolver()
            deadlock = DeadlockDetector(stall_threshold=5)

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
                currentTaskId=f"task_{rid}",
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
                scenario.warehouse_map, robot_configs, planner
            )
            for rid, sched in centralized_schedules.items():
                if rid in agents and agents[rid].state:
                    agents[rid].state.currentPath = list(sched)

        # Metrics tracking
        total_collisions = 0
        deadlocks_resolved = 0
        reroutes_count = 0
        idle_ticks_total = 0
        completion_ticks_per_robot: dict[str, int] = {}

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
                    sim_event = SimulationEvent(
                        eventId=f"ev_{tick}_{ev_type}",
                        type=ev_type,
                        tick=tick,
                        payload=payload,
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
                if getattr(agent, "_action_this_tick", "") == "YIELD" and agent._stall_ticks >= 5:
                    deadlocks_resolved += 1

                # Goal completion check
                dest = state.destination
                if (
                    dest
                    and state.position.x == dest.x
                    and state.position.y == dest.y
                    and rid not in completion_ticks_per_robot
                ):
                    completion_ticks_per_robot[rid] = tick

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
            all_done = all(
                ag.state.status == "IDLE"
                or (ag.state.destination and ag.state.position.x == ag.state.destination.x and ag.state.position.y == ag.state.destination.y)
                for ag in agents.values()
            )
            if all_done:
                break

            # Rate limiting for LIVE speed (~2 ticks per second)
            if speed == "LIVE":
                time.sleep(0.5)

        # Compute completion statistics
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
            deadlockCount=deadlocks_resolved,
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

    def _step_stop_and_wait(
        self, agent: RobotAgent, all_positions: dict[str, Position], current_tick: int
    ) -> RobotState:
        """Naive baseline: stops if any other robot is on the next waypoint cell."""
        if not agent.state or agent.state.status == "OFFLINE":
            return agent.state

        if agent.state.currentPath and len(agent.state.currentPath) > 0:
            next_wp = agent.state.currentPath[0]
            # Check if occupied by another robot
            conflict = False
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
        """Centralized schedule execution: follow pre-computed space-time schedule."""
        if not agent.state or agent.state.status == "OFFLINE":
            return agent.state

        if agent.state.currentPath and len(agent.state.currentPath) > 0:
            next_wp = agent.state.currentPath.pop(0)
            agent.state.position = Position(x=next_wp.x, y=next_wp.y)
            agent.state.status = "MOVING"
            agent.state.velocity = 1.0
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
        self, warehouse_map: WarehouseMap, robot_configs: list[dict], planner: GridAStarPlanner
    ) -> dict[str, list[Position]]:
        """Sequential space-time reservation planning for CENTRALIZED_RESERVATION mode."""
        try:
            from planner.centralized_baseline import plan_centralized
            start_goals = {r["robotId"]: (r["start"], r["goal"]) for r in robot_configs}
            return {rid: path.waypoints for rid, path in plan_centralized(start_goals, warehouse_map, 42).items()}
        except Exception:
            pass

        # Fallback space-time reservation table
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


if app is not None:
    @app.post("/control/start")
    async def control_start(body: dict):
        """Start a simulation run in the background."""
        global _runner_thread, _runner
        scenario_id = body.get("scenarioId", "a_normal")
        mode = body.get("mode", "DECENTRALIZED_PROPOSED")
        seed = body.get("seed", 42)
        speed = body.get("speed", "BATCH")

        if _runner.running:
            return JSONResponse(status_code=400, content={"error": "Simulation is already running."})

        def _worker():
            _runner.run(scenario_id, mode=mode, seed=seed, speed=speed)

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


if __name__ == "__main__":
    if app is not None:
        uvicorn.run("simulation.runner:app", host="0.0.0.0", port=8001, reload=False)
    else:
        print("FastAPI not installed. Running standalone scenario A batch demo...")
        metric = _runner.run("a_normal", mode="DECENTRALIZED_PROPOSED")
        print("Run finished:", metric)
