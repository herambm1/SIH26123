"""
planner/astar.py — A* path planner and windowed replanning.
Owner: Member 1

Import contracts from shared.python.models — do NOT redefine them here.
"""

from shared.python.models import Position, RobotPath, WarehouseMap


class PlanningFailedError(Exception):
    """Raised when no path exists between start and goal.

    Callers (RobotAgent) must catch this and set status=BLOCKED — never let
    this propagate to crash the simulation loop.
    """


class Planner:
    """A* planner with windowed cooperative replanning.

    Implements: standard grid A* (Manhattan heuristic, 4-connected movement),
    windowed replanning treating peer (cell, tick) claims as temporary obstacles,
    and dynamic replanning on AISLE_BLOCKED events.

    Related MAPF technique: Cooperative A* / WHCA*.
    """

    def __init__(self, warehouse_map: WarehouseMap):
        """Initialise the planner with a loaded WarehouseMap.

        Implementation: Member 1's responsibility.
        """
        raise NotImplementedError

    def plan(
        self,
        start: Position,
        goal: Position,
        blocked_cells: list,                   # list[Position]
        avoid_intervals: list | None = None,   # list[tuple[Position, int]] — (cell, tick) peer claims
        start_tick: int = 0,
    ) -> RobotPath:
        """Compute a path from start to goal.

        avoid_intervals: (cell, tick) pairs claimed by other robots' broadcast intents.
            Optional — if None or empty, plan without peer constraints.

        Raises PlanningFailedError if no path exists. Caller (RobotAgent) is
        responsible for catching it and setting status=BLOCKED.

        Implementation: Member 1's responsibility.
        """
        raise NotImplementedError

    def replan(
        self,
        current_path: RobotPath,
        new_blocked_cells: list,   # list[Position]
        current_tick: int,
    ) -> RobotPath:
        """Replan from the current position around newly blocked cells.

        Called by RobotAgent when a SimulationEvent(AISLE_BLOCKED) arrives.

        Implementation: Member 1's responsibility.
        """
        raise NotImplementedError
