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
        from robot_agent.communication.messages import build_intent_message  # noqa: import here to avoid circular at module load

        telemetry = self.sensor.read(self.robot_id, current_tick)          # Member 5
        self.state = self._apply_telemetry(self.state, telemetry, current_tick)

        if self._needs_replan():
            self.state.currentPath = self.planner.plan(                    # Member 1
                self.state.position,
                self.state.destination,
                self._known_blocked_cells(),
            ).waypoints

        incoming = self.transport.receive(self.robot_id)                   # Member 2
        conflict = self.detector.detect(self.state, self._current_path_obj(), incoming)  # Member 3
        if conflict:
            action = self.resolver.resolve(conflict, self.state, incoming)
            self._apply_action(action, conflict)

        if self.deadlock.check(self.robot_id, self._stall_ticks, self._waiting_on):
            self._force_yield()

        self._advance_one_cell_if_clear()
        self.transport.broadcast(build_intent_message(self.state))         # Member 2
        self.state.timestamp = current_tick
        return self.state

    # ── Private helpers — stubs for Member 3 to implement ───────────────────

    def _apply_telemetry(self, state, telemetry, current_tick: int):
        """Fold sensor telemetry into the current robot state."""
        raise NotImplementedError

    def _needs_replan(self) -> bool:
        """Return True if the robot needs a new path this tick."""
        raise NotImplementedError

    def _known_blocked_cells(self) -> list:    # list[Position]
        """Return the set of currently known blocked cells."""
        raise NotImplementedError

    def _current_path_obj(self):               # -> RobotPath
        """Reconstruct a RobotPath object from the current state."""
        raise NotImplementedError

    def _apply_action(self, action: str, conflict) -> None:
        """Apply a conflict resolution action to this robot's state."""
        raise NotImplementedError

    def _force_yield(self) -> None:
        """Force the robot to yield and replan (deadlock recovery)."""
        raise NotImplementedError

    def _advance_one_cell_if_clear(self) -> None:
        """Move the robot one cell along its current path if the next cell is clear."""
        raise NotImplementedError
