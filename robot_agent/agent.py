"""
robot_agent/agent.py — RobotAgent orchestration loop.
Owner: Member 3

This is the Phase-0 skeleton written collaboratively by the whole team.
It defines the tick() shape that every other Python module plugs into.
Member 3 maintains and extends it in small, incremental PRs.

IMPORTANT: Keep changes to this file small and announce them to the team —
it is the most cross-cutting file in the repo and all other members' work
depends on the call signatures staying stable.

Import contracts from shared.python.models — do NOT redefine them here.
"""

from shared.python.models import Position, RobotState, RobotPath


class RobotAgent:
    """Orchestration shell for a single robot in the simulation.

    Composition (all injected via constructor, all mockable independently):
        planner    → Member 1 (Planner)
        transport  → Member 2 (Transport)
        sensor     → Member 5 (SensorSource)
        detector   → Member 3 (ConflictDetector)
        resolver   → Member 3 (ConflictResolver)
        deadlock   → Member 3 (DeadlockDetector)

    The actual implementations are stubs until each member delivers them.
    """

    def __init__(
        self,
        robot_id: str,
        planner,          # planner.astar.Planner
        transport,        # robot_agent.communication.transport.Transport
        sensor,           # edge.sensor_source.SensorSource
        detector,         # collision_engine.detection.ConflictDetector
        resolver,         # collision_engine.resolution.ConflictResolver
        deadlock,         # collision_engine.deadlock.DeadlockDetector
    ):
        self.robot_id = robot_id
        self.planner = planner
        self.transport = transport
        self.sensor = sensor
        self.detector = detector
        self.resolver = resolver
        self.deadlock = deadlock

        # Internal state — assembled/updated each tick
        self.state: RobotState | None = None    # initialised by simulation runner before tick 0
        self._stall_ticks: int = 0
        self._waiting_on: str | None = None     # robot_id of the peer we're waiting on
        self._blocked_cells: list[Position] = []
        self._temporary_avoid_cells: list[Position] = []
        self._version: int = 1
        self._replan_requested: bool = False
        self._action_this_tick: str | None = None

    def tick(self, current_tick: int) -> RobotState:
        """Execute one simulation tick for this robot.

        Tick sequence (Phase-0 skeleton — Member 3 fills in):
          1. Read sensor telemetry (Member 5)
          2. Apply telemetry to state
          3. Replan if needed (Member 1)
          4. Receive peer intents from bus (Member 2)
          5. Detect conflicts (Member 3)
          6. Resolve conflicts if any (Member 3)
          7. Check for deadlock (Member 3)
          8. Advance one cell if clear
          9. Broadcast own intent (Member 2)
          10. Stamp timestamp and return state

        Implementation: Member 3's responsibility.
        Returns a fully populated RobotState for this tick.
        """
        try:
            from robot_agent.communication.messages import build_intent_message  # noqa: import here to avoid circular at module load
        except ImportError:
            build_intent_message = None

        telemetry = None
        if self.sensor:
            try:
                telemetry = self.sensor.read(self.robot_id, current_tick)          # Member 5
            except Exception:
                telemetry = None

        self.state = self._apply_telemetry(self.state, telemetry, current_tick)

        if self._needs_replan() and self.planner and self.state.destination:
            try:
                plan_result = self.planner.plan(                    # Member 1
                    self.state.position,
                    self.state.destination,
                    self._known_blocked_cells(),
                )
                if hasattr(plan_result, "waypoints"):
                    self.state.currentPath = list(plan_result.waypoints)
                elif isinstance(plan_result, list):
                    self.state.currentPath = list(plan_result)
                self.state.status = "MOVING"
                self._version += 1
            except Exception:
                # Planner unavailable / raises PlanningFailedError: robot enters status=BLOCKED, retries next tick
                self.state.status = "BLOCKED"
                self.state.velocity = 0.0

        incoming = []
        if self.transport:
            try:
                incoming = self.transport.receive(self.robot_id) or []              # Member 2
            except Exception:
                incoming = []

        conflict = None
        if self.detector:
            conflict = self.detector.detect(self.state, self._current_path_obj(), incoming)  # Member 3

        if conflict and self.resolver:
            action = self.resolver.resolve(conflict, self.state, incoming)
            self._apply_action(action, conflict)

        if self.deadlock and self.deadlock.check(self.robot_id, self._stall_ticks, self._waiting_on):
            self._force_yield()

        self._advance_one_cell_if_clear()

        # Broadcast intent
        if self.transport:
            intent_msg = None
            if build_intent_message:
                try:
                    intent_msg = build_intent_message(self.state)
                except Exception:
                    intent_msg = None
            if intent_msg is None:
                intent_msg = {
                    "robotId": self.state.robotId,
                    "position": self.state.position,
                    "destination": self.state.destination,
                    "plannedPath": list(self.state.currentPath or []),
                    "currentTask": self.state.currentTaskId,
                    "priority": getattr(self.state, "task_priority", 1),
                    "battery": self.state.battery,
                    "status": self.state.status,
                    "timestamp": current_tick,
                }
            try:
                self.transport.broadcast(intent_msg)                                # Member 2
            except Exception:
                pass

        self.state.timestamp = current_tick
        return self.state

    # ── Private helpers — implementations for Member 3 ─────────────────────

    def _apply_telemetry(self, state, telemetry, current_tick: int) -> RobotState:
        """Fold sensor telemetry into the current robot state."""
        if state is None:
            state = RobotState(
                robotId=self.robot_id,
                position=Position(x=0, y=0),
                velocity=0.0,
                battery=100.0,
                currentTaskId=None,
                destination=None,
                currentPath=[],
                status="IDLE",
                timestamp=current_tick,
            )

        if telemetry is not None:
            if hasattr(telemetry, "battery") and telemetry.battery is not None:
                state.battery = float(telemetry.battery)
            if hasattr(telemetry, "sensorHealth") and telemetry.sensorHealth == "OFFLINE":
                state.status = "OFFLINE"
                state.velocity = 0.0
            if hasattr(telemetry, "position") and telemetry.position is not None:
                if state.status != "OFFLINE":
                    state.position = Position(x=telemetry.position.x, y=telemetry.position.y)
        return state

    def _needs_replan(self) -> bool:
        """Return True if the robot needs a new path this tick."""
        if not self.state or self.state.status == "OFFLINE":
            return False
        if self._replan_requested:
            self._replan_requested = False
            return True
        if self.state.destination is not None:
            # Need replan if no path exists and we haven't reached destination
            has_no_path = not self.state.currentPath or len(self.state.currentPath) == 0
            not_at_goal = (
                self.state.position.x != self.state.destination.x
                or self.state.position.y != self.state.destination.y
            )
            return has_no_path and not_at_goal
        return False

    def _known_blocked_cells(self) -> list:    # list[Position]
        """Return the set of currently known blocked cells."""
        combined = list(self._blocked_cells)
        for p in self._temporary_avoid_cells:
            if not any(b.x == p.x and b.y == p.y for b in combined):
                combined.append(p)
        return combined

    def _current_path_obj(self) -> RobotPath:
        """Reconstruct a RobotPath object from the current state."""
        waypoints = list(self.state.currentPath) if self.state and self.state.currentPath else []
        ts = self.state.timestamp if self.state else 0
        return RobotPath(
            robotId=self.robot_id,
            waypoints=waypoints,
            generatedAtTick=ts,
            version=self._version,
        )

    def _apply_action(self, action: str, conflict) -> None:
        """Apply a conflict resolution action to this robot's state."""
        self._action_this_tick = action
        peer_id = None
        if conflict and hasattr(conflict, "robotIds"):
            peer_id = next((rid for rid in conflict.robotIds if rid != self.robot_id), None)

        if action == "CONTINUE":
            self._waiting_on = None
            if self.state.status == "WAITING":
                self.state.status = "MOVING"
            self.state.velocity = 1.0
        elif action == "WAIT":
            self.state.status = "WAITING"
            self.state.velocity = 0.0
            self._waiting_on = peer_id
        elif action == "YIELD":
            self.state.status = "WAITING"
            self.state.velocity = 0.0
            self._waiting_on = peer_id
            if conflict and hasattr(conflict, "predictedCell") and conflict.predictedCell:
                self._temporary_avoid_cells.append(conflict.predictedCell)
                self._replan_requested = True
        elif action == "REROUTE":
            self._waiting_on = None
            if conflict and hasattr(conflict, "predictedCell") and conflict.predictedCell:
                self._temporary_avoid_cells.append(conflict.predictedCell)
            self._replan_requested = True
        elif action == "REASSIGN_TASK":
            self.state.status = "BLOCKED"
            self.state.velocity = 0.0
            self._waiting_on = None

    def _force_yield(self) -> None:
        """Force the robot to yield and replan (deadlock recovery)."""
        self.state.status = "WAITING"
        self.state.velocity = 0.0
        self._stall_ticks = 0
        self._waiting_on = None
        self._replan_requested = True

    def _advance_one_cell_if_clear(self) -> None:
        """Move the robot one cell along its current path if the next cell is clear."""
        if not self.state or self.state.status in ("OFFLINE", "WAITING", "BLOCKED"):
            self.state.velocity = 0.0
            if self.state and self.state.status in ("WAITING", "BLOCKED"):
                self._stall_ticks += 1
            return

        if self.state.currentPath and len(self.state.currentPath) > 0:
            next_wp = self.state.currentPath[0]
            blocked = any(b.x == next_wp.x and b.y == next_wp.y for b in self._known_blocked_cells())
            if blocked:
                self.state.status = "BLOCKED"
                self.state.velocity = 0.0
                self._stall_ticks += 1
                self._replan_requested = True
                return

            # Advance
            self.state.currentPath.pop(0)
            old_pos = (self.state.position.x, self.state.position.y)
            self.state.position = Position(x=next_wp.x, y=next_wp.y, tick=None)
            new_pos = (self.state.position.x, self.state.position.y)

            if old_pos != new_pos:
                self._stall_ticks = 0
                self._waiting_on = None
                self.state.velocity = 1.0
            else:
                self._stall_ticks += 1

            # Check if destination reached
            if (
                self.state.destination
                and self.state.position.x == self.state.destination.x
                and self.state.position.y == self.state.destination.y
            ):
                self.state.status = "IDLE"
                self.state.velocity = 0.0
                self.state.currentTaskId = None
                self.state.currentPath = []
        else:
            self.state.velocity = 0.0
            if (
                self.state.destination
                and self.state.position.x == self.state.destination.x
                and self.state.position.y == self.state.destination.y
            ):
                self.state.status = "IDLE"
