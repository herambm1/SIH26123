"""
planner/astar.py — A* path planner and windowed cooperative replanning.
Owner: Member 1

Implements:
  - Standard grid A* with Manhattan-distance heuristic and 4-connected movement
    (no diagonals — keeps collision checking simple, per §8.2).
  - Windowed cooperative replanning (related to Cooperative A* / WHCA*): when
    broadcast peer intents reveal (cell, tick) collisions, replan treating those
    space-time pairs as temporarily blocked (§8.3).
  - Dynamic replanning on AISLE_BLOCKED events (§8.4).

Import contracts from shared.python.models — do NOT redefine them here.

Run standalone for a quick smoke-test (§15):
    python -m planner.astar
"""

from __future__ import annotations

import heapq
from typing import Optional

from shared.python.models import Position, RobotPath, WarehouseMap
from planner.warehouse_map import InvalidMapError


# ── Custom exceptions ─────────────────────────────────────────────────────────

class PlanningFailedError(Exception):
    """Raised when no path exists between start and goal.

    Callers (RobotAgent) MUST catch this and set status=BLOCKED — never let
    this propagate to crash the simulation loop.

    Attributes:
        start:  The start position that was requested.
        goal:   The goal position that was requested.
        reason: A human-readable explanation.
    """

    def __init__(self, start: Position, goal: Position, reason: str = ""):
        self.start = start
        self.goal = goal
        self.reason = reason
        super().__init__(
            f"No path from ({start.x},{start.y}) to ({goal.x},{goal.y})"
            + (f": {reason}" if reason else "")
        )


# ── Internal A* types ─────────────────────────────────────────────────────────

# A node in the A* open set: (f_score, g_score, x, y, tick)
# We include tick for space-time A* (windowed replanning).
_AStarNode = tuple[int, int, int, int, int]


# ── Planner ───────────────────────────────────────────────────────────────────

class Planner:
    """A* planner with windowed cooperative replanning (WHCA*-style).

    Each robot computes its path independently via plan().  When peer robots
    broadcast their (cell, tick) intents, this planner can replan treating
    those pairs as temporarily blocked — without a central reservation table.

    Related MAPF technique: Cooperative A* / Windowed Hierarchical Cooperative
    A* (WHCA*).  Name it this way to SIH judges.
    """

    # 4-connected movement deltas: right, left, down, up
    _MOVES = [(1, 0), (-1, 0), (0, 1), (0, -1)]

    def __init__(self, warehouse_map: WarehouseMap) -> None:
        """Initialise the planner with a loaded WarehouseMap.

        Builds an internal obstacle lookup set for O(1) cell-validity checks.
        The planner holds a reference to the map so that blockedCells mutated
        at runtime (by simulation/scenarios) are automatically reflected on the
        next plan() call.
        """
        self._map = warehouse_map
        # Permanent obstacle set — never changes after construction.
        # blockedCells is read fresh on each plan() call (it mutates at runtime).
        self._static_obstacles: frozenset[tuple[int, int]] = frozenset(
            (p.x, p.y) for p in warehouse_map.obstacles
        )
        # Version counter for RobotPath.version — incremented on each replan.
        self._version: int = 0

    # ── Public interface ──────────────────────────────────────────────────────

    def plan(
        self,
        start: Position,
        goal: Position,
        blocked_cells: list,                    # list[Position]
        avoid_intervals: Optional[list] = None, # list[tuple[Position, int]] — (cell, tick) peer claims
        start_tick: int = 0,
        robot_id: str = "",
    ) -> RobotPath:
        """Compute a path from start to goal using space-time A*.

        Parameters
        ----------
        start:
            Starting grid cell.  Must not be an obstacle or blocked cell.
        goal:
            Target grid cell.  Must not be a permanent obstacle.
        blocked_cells:
            Cells currently blocked at runtime (AISLE_BLOCKED events, etc.).
            Combined with the map's static obstacles for this search.
        avoid_intervals:
            (cell, tick) pairs claimed by other robots' broadcast intents.
            Optional — if None or [], plan without peer constraints (standard A*).
            Treated as temporarily blocked only at the specific tick they claim.
        start_tick:
            The simulation tick at which the robot begins moving.  Waypoint
            ticks are set relative to this.
        robot_id:
            Used to set RobotPath.robotId.  Defaults to "" for tests.

        Returns
        -------
        RobotPath
            waypoints is a list[Position] with .tick set on each element.
            The first waypoint is start (at start_tick), the last is goal.

        Raises
        ------
        InvalidMapError
            If start or goal are on a permanent obstacle cell, or out of bounds.
        PlanningFailedError
            If no path exists (boxed-in, goal unreachable).  Caller must catch.
        """
        width = self._map.gridWidth
        height = self._map.gridHeight

        # ── Validate start and goal ───────────────────────────────────────────
        self._validate_cell(start, "start", width, height)
        self._validate_cell(goal, "goal", width, height)

        # Special case: start == goal — zero movement needed
        if start.x == goal.x and start.y == goal.y:
            self._version += 1
            waypoint = Position(x=start.x, y=start.y, tick=start_tick)
            return RobotPath(
                robotId=robot_id,
                waypoints=[waypoint],
                generatedAtTick=start_tick,
                version=self._version,
            )

        # ── Build combined obstacle set for this call ─────────────────────────
        runtime_blocked: frozenset[tuple[int, int]] = frozenset(
            (p.x, p.y) for p in blocked_cells
        )
        all_blocked = self._static_obstacles | runtime_blocked

        # ── Build space-time avoid set ────────────────────────────────────────
        # avoid_set: {(x, y, tick)} — blocked only at that exact tick.
        avoid_set: set[tuple[int, int, int]] = set()
        if avoid_intervals:
            for cell, tick in avoid_intervals:
                avoid_set.add((cell.x, cell.y, tick))

        # ── A* search ─────────────────────────────────────────────────────────
        waypoints = self._astar(
            start_x=start.x,
            start_y=start.y,
            goal_x=goal.x,
            goal_y=goal.y,
            width=width,
            height=height,
            all_blocked=all_blocked,
            avoid_set=avoid_set,
            start_tick=start_tick,
        )

        if waypoints is None:
            raise PlanningFailedError(start, goal, "grid is fully blocked or goal unreachable")

        self._version += 1
        return RobotPath(
            robotId=robot_id,
            waypoints=waypoints,
            generatedAtTick=start_tick,
            version=self._version,
        )

    def replan(
        self,
        current_path: RobotPath,
        new_blocked_cells: list,  # list[Position]
        current_tick: int,
    ) -> RobotPath:
        """Replan from the current position around newly blocked cells.

        Called by RobotAgent when a SimulationEvent(AISLE_BLOCKED) arrives.

        Finds the robot's position at current_tick from its existing path,
        adds new_blocked_cells to the map's blockedCells, and replans from
        that position to the original goal.

        Parameters
        ----------
        current_path:
            The robot's current RobotPath (may be partially executed).
        new_blocked_cells:
            Newly blocked cells from the AISLE_BLOCKED event.
        current_tick:
            The simulation tick at which replanning is triggered.

        Returns
        -------
        RobotPath
            A new path from the robot's current cell to the original goal,
            avoiding all blocked cells (including the newly blocked ones).

        Raises
        ------
        PlanningFailedError
            If no path exists after adding the new blocked cells.
        """
        # ── Determine current position ────────────────────────────────────────
        # Find the waypoint at or before current_tick.
        current_pos: Optional[Position] = None
        goal_pos: Optional[Position] = None

        if not current_path.waypoints:
            raise PlanningFailedError(
                Position(0, 0), Position(0, 0), "current_path has no waypoints"
            )

        goal_pos = current_path.waypoints[-1]

        # Walk the waypoints to find where the robot is at current_tick.
        for wp in current_path.waypoints:
            if wp.tick is not None and wp.tick <= current_tick:
                current_pos = wp
            elif wp.tick is None:
                # Fallback: if ticks aren't set (shouldn't happen), use first.
                current_pos = wp
                break

        if current_pos is None:
            # Tick is before the path started — start from the beginning.
            current_pos = current_path.waypoints[0]

        # ── Merge new blocked cells into the map's blockedCells ───────────────
        # blockedCells is a mutable list on the WarehouseMap — add any new cells
        # that aren't already there.
        existing_blocked = {(p.x, p.y) for p in self._map.blockedCells}
        for p in new_blocked_cells:
            if (p.x, p.y) not in existing_blocked:
                self._map.blockedCells.append(p)
                existing_blocked.add((p.x, p.y))

        # ── Replan from current position to original goal ─────────────────────
        start_no_tick = Position(x=current_pos.x, y=current_pos.y)
        goal_no_tick = Position(x=goal_pos.x, y=goal_pos.y)

        return self.plan(
            start=start_no_tick,
            goal=goal_no_tick,
            blocked_cells=self._map.blockedCells,
            avoid_intervals=None,   # replan without peer constraints (conservative)
            start_tick=current_tick,
            robot_id=current_path.robotId,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _validate_cell(
        self,
        pos: Position,
        label: str,
        width: int,
        height: int,
    ) -> None:
        """Raise InvalidMapError if pos is out of bounds or on a static obstacle."""
        if not (0 <= pos.x < width and 0 <= pos.y < height):
            raise InvalidMapError(
                f"{label} ({pos.x},{pos.y}) is out of bounds for a "
                f"{width}×{height} grid."
            )
        if (pos.x, pos.y) in self._static_obstacles:
            raise InvalidMapError(
                f"{label} ({pos.x},{pos.y}) lies on a permanent obstacle cell."
            )

    @staticmethod
    def _heuristic(x: int, y: int, gx: int, gy: int) -> int:
        """Manhattan distance heuristic (admissible for 4-connected grid)."""
        return abs(x - gx) + abs(y - gy)

    def _astar(
        self,
        start_x: int,
        start_y: int,
        goal_x: int,
        goal_y: int,
        width: int,
        height: int,
        all_blocked: frozenset,          # frozenset[tuple[int,int]]
        avoid_set: set,                  # set[tuple[int,int,int]] — (x,y,tick)
        start_tick: int,
    ) -> Optional[list]:                 # Optional[list[Position]]
        """Core A* search in space-time.

        When avoid_intervals is non-empty we search in (x, y, tick) space so
        that peer (cell, tick) claims are respected.  When avoid_intervals is
        empty this degrades to standard grid A* without the tick dimension.

        Movement cost = 1 tick per cell (at most one move per tick, per project
        spec).  Waiting in place is also a legal action (costs 1 tick).

        Returns None if no path found.
        Returns list[Position] with .tick set on each waypoint if found.
        """
        use_space_time = len(avoid_set) > 0

        # Max ticks to search: prevents infinite loops if robots wait
        # indefinitely.  Use a generous bound: width*height*2 should cover any
        # reasonable scenario.
        max_tick = start_tick + width * height * 2

        # open_set entries: (f, g, x, y, tick)
        # tie-break on g (prefer shorter paths over waiting) then x, y
        start_g = 0
        start_h = self._heuristic(start_x, start_y, goal_x, goal_y)
        start_f = start_g + start_h

        open_set: list[_AStarNode] = []
        heapq.heappush(open_set, (start_f, start_g, start_x, start_y, start_tick))

        # came_from: (x, y, tick) → (parent_x, parent_y, parent_tick)
        came_from: dict[tuple[int, int, int], tuple[int, int, int]] = {}

        # g_score: best known cost to reach (x, y, tick)
        g_score: dict[tuple[int, int, int], int] = {
            (start_x, start_y, start_tick): 0
        }

        while open_set:
            f, g, cx, cy, ct = heapq.heappop(open_set)

            # Safety: discard stale entries
            if g > g_score.get((cx, cy, ct), float("inf")):
                continue

            # Goal check (ignoring tick at goal — any tick is fine)
            if cx == goal_x and cy == goal_y:
                return self._reconstruct_path(came_from, cx, cy, ct)

            next_tick = ct + 1
            if next_tick > max_tick:
                continue

            # Generate neighbours: 4-connected moves + wait-in-place
            for dx, dy in self._MOVES:
                nx, ny = cx + dx, cy + dy
                # Bounds check
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                # Permanent/runtime obstacle check
                if (nx, ny) in all_blocked:
                    continue
                # Space-time avoid_intervals check
                if use_space_time and (nx, ny, next_tick) in avoid_set:
                    continue

                new_g = g + 1
                state = (nx, ny, next_tick)
                if new_g < g_score.get(state, float("inf")):
                    g_score[state] = new_g
                    came_from[state] = (cx, cy, ct)
                    h = self._heuristic(nx, ny, goal_x, goal_y)
                    heapq.heappush(open_set, (new_g + h, new_g, nx, ny, next_tick))

            # Wait in place (costs 1 tick) — only when we have avoid_intervals
            # to resolve, otherwise pure A* never needs to wait.
            if use_space_time:
                if (cx, cy, next_tick) not in avoid_set:
                    new_g = g + 1
                    state = (cx, cy, next_tick)
                    if new_g < g_score.get(state, float("inf")):
                        g_score[state] = new_g
                        came_from[state] = (cx, cy, ct)
                        h = self._heuristic(cx, cy, goal_x, goal_y)
                        heapq.heappush(open_set, (new_g + h, new_g, cx, cy, next_tick))

        return None  # No path found

    @staticmethod
    def _reconstruct_path(
        came_from: dict,
        goal_x: int,
        goal_y: int,
        goal_tick: int,
    ) -> list:  # list[Position]
        """Walk came_from backwards to reconstruct the path, then reverse."""
        path: list[Position] = []
        current = (goal_x, goal_y, goal_tick)
        while current in came_from:
            x, y, t = current
            path.append(Position(x=x, y=y, tick=t))
            current = came_from[current]
        # Append the start node (not in came_from)
        sx, sy, st = current
        path.append(Position(x=sx, y=sy, tick=st))
        path.reverse()
        return path


# ── Path validation utility ───────────────────────────────────────────────────

def validate_path(path: RobotPath, warehouse_map: WarehouseMap) -> list[str]:
    """Validate a RobotPath against the warehouse map.

    Returns a list of error strings (empty list means the path is valid).
    Checks:
    - waypoints list is non-empty.
    - Every waypoint is within grid bounds.
    - No waypoint falls on a static obstacle.
    - No waypoint falls on a blockedCell.
    - Consecutive waypoints are adjacent (Manhattan distance == 1) or equal (wait).
    - .tick increments by exactly 1 between consecutive waypoints.
    - The first waypoint's .tick is not None.
    """
    errors: list[str] = []
    if not path.waypoints:
        errors.append("path.waypoints is empty")
        return errors

    width = warehouse_map.gridWidth
    height = warehouse_map.gridHeight
    obstacle_set = {(p.x, p.y) for p in warehouse_map.obstacles}
    blocked_set = {(p.x, p.y) for p in warehouse_map.blockedCells}

    prev = None
    for i, wp in enumerate(path.waypoints):
        # Bounds
        if not (0 <= wp.x < width and 0 <= wp.y < height):
            errors.append(f"waypoint[{i}] ({wp.x},{wp.y}) out of bounds")
        # Obstacle
        if (wp.x, wp.y) in obstacle_set:
            errors.append(f"waypoint[{i}] ({wp.x},{wp.y}) is a static obstacle")
        # Blocked
        if (wp.x, wp.y) in blocked_set:
            errors.append(f"waypoint[{i}] ({wp.x},{wp.y}) is a blocked cell")
        # Tick presence
        if wp.tick is None:
            errors.append(f"waypoint[{i}] ({wp.x},{wp.y}) has tick=None")

        if prev is not None:
            # Adjacency: Manhattan distance must be 0 (wait) or 1 (move)
            dist = abs(wp.x - prev.x) + abs(wp.y - prev.y)
            if dist > 1:
                errors.append(
                    f"waypoint[{i-1}]→waypoint[{i}]: "
                    f"Manhattan distance={dist} (must be 0 or 1)"
                )
            # Tick increment
            if wp.tick is not None and prev.tick is not None:
                if wp.tick != prev.tick + 1:
                    errors.append(
                        f"waypoint[{i-1}]→waypoint[{i}]: "
                        f"tick jump {prev.tick}→{wp.tick} (must be +1)"
                    )
        prev = wp

    return errors


# ── Standalone smoke-test ─────────────────────────────────────────────────────

if __name__ == "__main__":
    """Standalone smoke-test: no other module needed.

    Builds a small hardcoded map, plans a path, and prints the result.
    Demonstrates that the planner works independently (§15).
    """
    from planner.warehouse_map import build_warehouse_map

    print("=== planner/astar.py standalone smoke-test ===\n")

    # 10×10 map with a wall along col 5 (rows 0–7), leaving a gap at row 8
    obstacles = [Position(x=5, y=r) for r in range(8)]
    wmap = build_warehouse_map(
        width=10,
        height=10,
        obstacles=obstacles,
        choke_points=[Position(x=5, y=8)],
        pickup_points=[Position(x=0, y=0)],
        drop_points=[Position(x=9, y=9)],
    )
    planner = Planner(wmap)

    start = Position(x=0, y=0)
    goal = Position(x=9, y=9)
    print(f"Planning from {start} to {goal} …")
    path = planner.plan(start, goal, blocked_cells=[], start_tick=0, robot_id="R1")
    print(f"Path length: {len(path.waypoints)} waypoints")
    for wp in path.waypoints:
        print(f"  tick={wp.tick:3d}  ({wp.x:2d}, {wp.y:2d})")

    errors = validate_path(path, wmap)
    if errors:
        print(f"\nVALIDATION ERRORS: {errors}")
    else:
        print("\nPath is valid [OK]")

    # Demonstrate PlanningFailedError
    print("\nAttempting to plan to a boxed-in goal …")
    box_obstacles = [
        Position(x=3, y=2), Position(x=3, y=4),
        Position(x=2, y=3), Position(x=4, y=3),
    ]
    wmap2 = build_warehouse_map(10, 10, box_obstacles, [], [Position(x=0, y=0)], [])
    planner2 = Planner(wmap2)
    try:
        planner2.plan(Position(x=0, y=0), Position(x=3, y=3), blocked_cells=[])
    except PlanningFailedError as e:
        print(f"Caught PlanningFailedError (expected): {e}")

    print("\nSmoke-test complete.")
