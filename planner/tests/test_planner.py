"""
planner/tests/test_planner.py — Comprehensive unit tests for the planner module.
Owner: Member 1

Test coverage (per 01_PATH_PLANNING.md §15 and the implementation prompt):
  1.  Basic path (open map, A→B reachable)
  2.  Obstacle avoidance
  3.  Blocked goal raises PlanningFailedError
  4.  Unreachable goal raises PlanningFailedError
  5.  Start == goal (zero-step path)
  6.  Narrow corridor navigation
  7.  Multiple valid paths (verify validity, not specific route)
  8.  Invalid map inputs raise InvalidMapError
  9.  Path validity (no obstacle overlap, connected waypoints, ticks increment)
  10. Windowed replanning (avoid_intervals) avoids peer (cell, tick) claims
  11. replan() correctly reroutes around a newly blocked cell
  12. plan_centralized() produces no (cell, tick) collisions for full fleet
  13. Demo map loads and is structurally sound
  14. Out-of-bounds start/goal raises InvalidMapError
  15. build_warehouse_map() validation errors

Run with:
    python -m pytest planner/tests/test_planner.py -v
or from repo root:
    python -m pytest planner/ -v
"""

import pytest

from shared.python.models import Position, RobotPath, WarehouseMap
from planner.warehouse_map import build_warehouse_map, InvalidMapError
from planner.astar import Planner, PlanningFailedError, validate_path
from planner.centralized_baseline import plan_centralized
from simulation.warehouse.demo_map import get_demo_map


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures — reusable mock maps
# ═══════════════════════════════════════════════════════════════════════════════

def _p(x: int, y: int) -> Position:
    """Shorthand: Position without tick (map/input use)."""
    return Position(x=x, y=y)


@pytest.fixture
def open_map_5x5():
    """5×5 grid with no obstacles — free movement everywhere."""
    return build_warehouse_map(
        width=5, height=5,
        obstacles=[],
        choke_points=[],
        pickup_points=[_p(0, 0)],
        drop_points=[_p(4, 4)],
    )


@pytest.fixture
def wall_map():
    """10×10 grid with a vertical wall at x=5 (rows 0–7).
    The wall has a single gap at row 8, creating one choke point.

         0123456789
    y=0  .....█....
    y=1  .....█....
    ...
    y=7  .....█....
    y=8  ..........  ← gap (choke)
    y=9  ..........
    """
    obs = [_p(5, r) for r in range(8)]
    return build_warehouse_map(
        width=10, height=10,
        obstacles=obs,
        choke_points=[_p(5, 8)],
        pickup_points=[_p(0, 0)],
        drop_points=[_p(9, 9)],
    )


@pytest.fixture
def corridor_map():
    """10×3 map: only row 1 is walkable (narrow corridor).

    y=0  ██████████  (all obstacle)
    y=1  ..........  (corridor)
    y=2  ██████████  (all obstacle)
    """
    top = [_p(x, 0) for x in range(10)]
    bot = [_p(x, 2) for x in range(10)]
    return build_warehouse_map(
        width=10, height=3,
        obstacles=top + bot,
        choke_points=[_p(5, 1)],
        pickup_points=[_p(0, 1)],
        drop_points=[_p(9, 1)],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# §1 — build_warehouse_map() validation (InvalidMapError)
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuildWarehouseMap:
    """Tests for map construction and validation."""

    def test_basic_construction(self, open_map_5x5):
        m = open_map_5x5
        assert m.gridWidth == 5
        assert m.gridHeight == 5
        assert m.obstacles == []
        assert m.blockedCells == []
        assert m.pickupPoints == [_p(0, 0)]
        assert m.dropPoints == [_p(4, 4)]

    def test_zero_width_raises(self):
        with pytest.raises(InvalidMapError, match="positive"):
            build_warehouse_map(0, 5, [], [], [], [])

    def test_zero_height_raises(self):
        with pytest.raises(InvalidMapError, match="positive"):
            build_warehouse_map(5, 0, [], [], [], [])

    def test_negative_dimensions_raise(self):
        with pytest.raises(InvalidMapError):
            build_warehouse_map(-1, -1, [], [], [], [])

    def test_obstacle_out_of_bounds_raises(self):
        with pytest.raises(InvalidMapError, match="out of bounds"):
            build_warehouse_map(5, 5, [_p(5, 0)], [], [], [])

    def test_pickup_on_obstacle_raises(self):
        with pytest.raises(InvalidMapError, match="Pickup"):
            build_warehouse_map(5, 5, [_p(1, 1)], [], [_p(1, 1)], [])

    def test_drop_on_obstacle_raises(self):
        with pytest.raises(InvalidMapError, match="Drop"):
            build_warehouse_map(5, 5, [_p(3, 3)], [], [], [_p(3, 3)])

    def test_choke_on_obstacle_raises(self):
        with pytest.raises(InvalidMapError, match="Choke"):
            build_warehouse_map(5, 5, [_p(2, 2)], [_p(2, 2)], [], [])

    def test_choke_out_of_bounds_raises(self):
        with pytest.raises(InvalidMapError, match="out of bounds"):
            build_warehouse_map(5, 5, [], [_p(10, 10)], [], [])

    def test_blockedcells_starts_empty(self, open_map_5x5):
        assert open_map_5x5.blockedCells == []

    def test_returns_warehouse_map_type(self, open_map_5x5):
        assert isinstance(open_map_5x5, WarehouseMap)

    def test_non_int_dimensions_raise(self):
        with pytest.raises(InvalidMapError):
            build_warehouse_map(5.0, 5, [], [], [], [])  # type: ignore


# ═══════════════════════════════════════════════════════════════════════════════
# §2 — Basic path (open map)
# ═══════════════════════════════════════════════════════════════════════════════

class TestBasicPath:
    """A path must exist on an open map and be geometrically valid."""

    def test_open_map_path_exists(self, open_map_5x5):
        planner = Planner(open_map_5x5)
        path = planner.plan(_p(0, 0), _p(4, 4), blocked_cells=[], start_tick=0, robot_id="R1")
        assert isinstance(path, RobotPath)
        assert path.robotId == "R1"
        assert len(path.waypoints) > 0

    def test_start_and_goal_in_path(self, open_map_5x5):
        planner = Planner(open_map_5x5)
        path = planner.plan(_p(0, 0), _p(4, 4), blocked_cells=[], start_tick=0)
        first = path.waypoints[0]
        last = path.waypoints[-1]
        assert (first.x, first.y) == (0, 0)
        assert (last.x, last.y) == (4, 4)

    def test_optimal_manhattan_length(self, open_map_5x5):
        """On a fully open map A* should find the shortest path."""
        planner = Planner(open_map_5x5)
        path = planner.plan(_p(0, 0), _p(4, 0), blocked_cells=[], start_tick=0)
        # Shortest path along row 0: 4 moves → 5 waypoints
        assert len(path.waypoints) == 5

    def test_ticks_start_at_start_tick(self, open_map_5x5):
        planner = Planner(open_map_5x5)
        path = planner.plan(_p(0, 0), _p(2, 2), blocked_cells=[], start_tick=10)
        assert path.waypoints[0].tick == 10

    def test_path_validity_open_map(self, open_map_5x5):
        planner = Planner(open_map_5x5)
        path = planner.plan(_p(0, 0), _p(4, 4), blocked_cells=[], start_tick=0)
        errors = validate_path(path, open_map_5x5)
        assert errors == [], f"Path invalid: {errors}"

    def test_generated_at_tick(self, open_map_5x5):
        planner = Planner(open_map_5x5)
        path = planner.plan(_p(0, 0), _p(1, 0), blocked_cells=[], start_tick=42)
        assert path.generatedAtTick == 42

    def test_version_increments_per_plan(self, open_map_5x5):
        planner = Planner(open_map_5x5)
        p1 = planner.plan(_p(0, 0), _p(1, 0), blocked_cells=[], start_tick=0)
        p2 = planner.plan(_p(0, 0), _p(2, 0), blocked_cells=[], start_tick=0)
        assert p2.version > p1.version


# ═══════════════════════════════════════════════════════════════════════════════
# §3 — Start == Goal
# ═══════════════════════════════════════════════════════════════════════════════

class TestStartEqualsGoal:
    def test_returns_single_waypoint(self, open_map_5x5):
        planner = Planner(open_map_5x5)
        path = planner.plan(_p(2, 2), _p(2, 2), blocked_cells=[], start_tick=5)
        assert len(path.waypoints) == 1
        assert path.waypoints[0].x == 2
        assert path.waypoints[0].y == 2
        assert path.waypoints[0].tick == 5

    def test_validity_start_equals_goal(self, open_map_5x5):
        planner = Planner(open_map_5x5)
        path = planner.plan(_p(3, 3), _p(3, 3), blocked_cells=[], start_tick=0)
        errors = validate_path(path, open_map_5x5)
        assert errors == []


# ═══════════════════════════════════════════════════════════════════════════════
# §4 — Obstacle avoidance
# ═══════════════════════════════════════════════════════════════════════════════

class TestObstacleAvoidance:
    def test_path_avoids_static_obstacles(self, wall_map):
        """Path from left side to right side must go around the wall at x=5."""
        planner = Planner(wall_map)
        path = planner.plan(_p(0, 0), _p(9, 0), blocked_cells=[], start_tick=0)
        obstacle_cells = {(5, r) for r in range(8)}
        for wp in path.waypoints:
            assert (wp.x, wp.y) not in obstacle_cells, (
                f"Waypoint ({wp.x},{wp.y}) at tick {wp.tick} is on an obstacle"
            )

    def test_path_validity_wall_map(self, wall_map):
        planner = Planner(wall_map)
        path = planner.plan(_p(0, 9), _p(9, 0), blocked_cells=[], start_tick=0)
        errors = validate_path(path, wall_map)
        assert errors == [], f"Path invalid: {errors}"

    def test_path_avoids_blocked_cells(self, open_map_5x5):
        """Cells in blocked_cells are treated as runtime walls.

        Block col x=2 rows 0–3 (leave row 4 open as a detour gap).
        The path from (0,0) to (4,0) must route around the blocked column
        via row 4 rather than going straight through x=2.
        """
        blocked = [_p(2, 0), _p(2, 1), _p(2, 2), _p(2, 3)]
        planner = Planner(open_map_5x5)
        path = planner.plan(_p(0, 0), _p(4, 0), blocked_cells=blocked, start_tick=0)
        blocked_set = {(p.x, p.y) for p in blocked}
        for wp in path.waypoints:
            assert (wp.x, wp.y) not in blocked_set, (
                f"Waypoint ({wp.x},{wp.y}) is in blocked_cells"
            )

    def test_no_waypoint_on_static_obstacle(self, wall_map):
        planner = Planner(wall_map)
        path = planner.plan(_p(0, 5), _p(9, 5), blocked_cells=[], start_tick=0)
        static = {(p.x, p.y) for p in wall_map.obstacles}
        for wp in path.waypoints:
            assert (wp.x, wp.y) not in static


# ═══════════════════════════════════════════════════════════════════════════════
# §5 — Blocked / unreachable goal
# ═══════════════════════════════════════════════════════════════════════════════

class TestUnreachableGoal:
    def test_blocked_goal_raises_planning_failed(self, open_map_5x5):
        """Goal completely surrounded by blocked cells → PlanningFailedError."""
        blocked = [_p(3, 2), _p(3, 4), _p(2, 3), _p(4, 3)]
        planner = Planner(open_map_5x5)
        with pytest.raises(PlanningFailedError):
            planner.plan(_p(0, 0), _p(3, 3), blocked_cells=blocked, start_tick=0)

    def test_fully_boxed_in_raises(self):
        """A map where the start is fully surrounded by obstacles."""
        obs = [
            _p(1, 1), _p(2, 1), _p(3, 1),
            _p(1, 2),            _p(3, 2),
            _p(1, 3), _p(2, 3), _p(3, 3),
        ]
        wmap = build_warehouse_map(5, 5, obs, [], [_p(0, 0)], [_p(4, 4)])
        planner = Planner(wmap)
        with pytest.raises(PlanningFailedError):
            planner.plan(_p(2, 2), _p(0, 0), blocked_cells=[], start_tick=0)

    def test_planning_failed_error_contains_start_goal(self, open_map_5x5):
        blocked = [_p(3, 2), _p(3, 4), _p(2, 3), _p(4, 3)]
        planner = Planner(open_map_5x5)
        with pytest.raises(PlanningFailedError) as exc_info:
            planner.plan(_p(0, 0), _p(3, 3), blocked_cells=blocked, start_tick=0)
        err = exc_info.value
        assert err.start.x == 0 and err.start.y == 0
        assert err.goal.x == 3 and err.goal.y == 3

    def test_out_of_bounds_start_raises_invalid_map(self, open_map_5x5):
        planner = Planner(open_map_5x5)
        with pytest.raises(InvalidMapError, match="out of bounds"):
            planner.plan(_p(10, 0), _p(0, 0), blocked_cells=[], start_tick=0)

    def test_out_of_bounds_goal_raises_invalid_map(self, open_map_5x5):
        planner = Planner(open_map_5x5)
        with pytest.raises(InvalidMapError, match="out of bounds"):
            planner.plan(_p(0, 0), _p(0, 10), blocked_cells=[], start_tick=0)

    def test_start_on_obstacle_raises_invalid_map(self, wall_map):
        planner = Planner(wall_map)
        with pytest.raises(InvalidMapError, match="permanent obstacle"):
            planner.plan(_p(5, 0), _p(9, 9), blocked_cells=[], start_tick=0)

    def test_goal_on_obstacle_raises_invalid_map(self, wall_map):
        planner = Planner(wall_map)
        with pytest.raises(InvalidMapError, match="permanent obstacle"):
            planner.plan(_p(0, 0), _p(5, 3), blocked_cells=[], start_tick=0)


# ═══════════════════════════════════════════════════════════════════════════════
# §6 — Narrow corridor
# ═══════════════════════════════════════════════════════════════════════════════

class TestNarrowCorridor:
    def test_corridor_path_found(self, corridor_map):
        planner = Planner(corridor_map)
        path = planner.plan(_p(0, 1), _p(9, 1), blocked_cells=[], start_tick=0)
        assert (path.waypoints[0].x, path.waypoints[0].y) == (0, 1)
        assert (path.waypoints[-1].x, path.waypoints[-1].y) == (9, 1)

    def test_corridor_all_waypoints_in_row1(self, corridor_map):
        """Every waypoint must stay in the walkable row (y=1)."""
        planner = Planner(corridor_map)
        path = planner.plan(_p(0, 1), _p(9, 1), blocked_cells=[], start_tick=0)
        for wp in path.waypoints:
            assert wp.y == 1, f"Waypoint ({wp.x},{wp.y}) left the corridor"

    def test_corridor_validity(self, corridor_map):
        planner = Planner(corridor_map)
        path = planner.plan(_p(0, 1), _p(9, 1), blocked_cells=[], start_tick=0)
        errors = validate_path(path, corridor_map)
        assert errors == []

    def test_corridor_no_route_if_blocked(self, corridor_map):
        """Block a cell mid-corridor → PlanningFailedError."""
        blocked = [_p(5, 1)]  # severs the only route
        planner = Planner(corridor_map)
        with pytest.raises(PlanningFailedError):
            planner.plan(_p(0, 1), _p(9, 1), blocked_cells=blocked, start_tick=0)


# ═══════════════════════════════════════════════════════════════════════════════
# §7 — Multiple valid paths (validate correctness, not specific route)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMultipleValidPaths:
    def test_any_valid_path_accepted(self, open_map_5x5):
        """On an open map with multiple routes, any valid path is acceptable."""
        planner = Planner(open_map_5x5)
        path = planner.plan(_p(0, 0), _p(4, 4), blocked_cells=[], start_tick=0)
        errors = validate_path(path, open_map_5x5)
        assert errors == []

    def test_path_length_at_least_manhattan(self, open_map_5x5):
        """Any path is at least as long as the Manhattan distance."""
        start, goal = _p(0, 0), _p(4, 4)
        manhattan = abs(4 - 0) + abs(4 - 0)  # 8
        planner = Planner(open_map_5x5)
        path = planner.plan(start, goal, blocked_cells=[], start_tick=0)
        assert len(path.waypoints) - 1 >= manhattan


# ═══════════════════════════════════════════════════════════════════════════════
# §8 — Path validity (validate_path utility)
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidatePath:
    """Direct tests of the validate_path() helper."""

    def _make_path(self, waypoints: list[Position], robot_id: str = "R0") -> RobotPath:
        return RobotPath(robotId=robot_id, waypoints=waypoints,
                         generatedAtTick=0, version=1)

    def test_valid_path_returns_no_errors(self, open_map_5x5):
        wps = [Position(x=0, y=0, tick=0), Position(x=1, y=0, tick=1),
               Position(x=2, y=0, tick=2)]
        path = self._make_path(wps)
        assert validate_path(path, open_map_5x5) == []

    def test_empty_waypoints_is_error(self, open_map_5x5):
        path = self._make_path([])
        assert validate_path(path, open_map_5x5) != []

    def test_obstacle_waypoint_detected(self, wall_map):
        wps = [Position(x=0, y=0, tick=0), Position(x=5, y=0, tick=1)]
        path = self._make_path(wps)
        errors = validate_path(path, wall_map)
        assert any("obstacle" in e for e in errors)

    def test_gap_in_path_detected(self, open_map_5x5):
        wps = [Position(x=0, y=0, tick=0), Position(x=2, y=0, tick=1)]
        path = self._make_path(wps)
        errors = validate_path(path, open_map_5x5)
        assert any("distance" in e for e in errors)

    def test_bad_tick_increment_detected(self, open_map_5x5):
        wps = [Position(x=0, y=0, tick=0), Position(x=1, y=0, tick=3)]
        path = self._make_path(wps)
        errors = validate_path(path, open_map_5x5)
        assert any("tick" in e for e in errors)

    def test_out_of_bounds_waypoint_detected(self, open_map_5x5):
        wps = [Position(x=0, y=0, tick=0), Position(x=99, y=0, tick=1)]
        path = self._make_path(wps)
        errors = validate_path(path, open_map_5x5)
        assert any("out of bounds" in e for e in errors)

    def test_blocked_cell_waypoint_detected(self, open_map_5x5):
        open_map_5x5.blockedCells.append(_p(1, 0))
        wps = [Position(x=0, y=0, tick=0), Position(x=1, y=0, tick=1)]
        path = self._make_path(wps)
        errors = validate_path(path, open_map_5x5)
        assert any("blocked" in e for e in errors)
        open_map_5x5.blockedCells.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# §9 — Windowed replanning (avoid_intervals)
# ═══════════════════════════════════════════════════════════════════════════════

class TestWindowedReplanning:
    """Two fabricated conflicting paths; confirm replanning avoids peer claims."""

    def test_avoids_claimed_cell_at_tick(self, open_map_5x5):
        """R2 claims cell (2,0) at tick 2.  R1 must not be at (2,0) at tick 2."""
        planner = Planner(open_map_5x5)

        r2_claim = (_p(2, 0), 2)

        path = planner.plan(
            start=_p(0, 0),
            goal=_p(4, 0),
            blocked_cells=[],
            avoid_intervals=[r2_claim],
            start_tick=0,
            robot_id="R1",
        )
        for wp in path.waypoints:
            if wp.tick == 2:
                assert not (wp.x == 2 and wp.y == 0), (
                    "R1 entered peer-claimed (2,0) at tick 2"
                )

    def test_avoids_multiple_peer_claims(self, open_map_5x5):
        """Multiple peer (cell,tick) claims are all respected."""
        planner = Planner(open_map_5x5)
        claims = [
            (_p(1, 0), 1),
            (_p(2, 0), 2),
            (_p(3, 0), 3),
        ]
        path = planner.plan(
            start=_p(0, 0),
            goal=_p(4, 0),
            blocked_cells=[],
            avoid_intervals=claims,
            start_tick=0,
        )
        claim_set = {(cell.x, cell.y, t) for cell, t in claims}
        for wp in path.waypoints:
            assert (wp.x, wp.y, wp.tick) not in claim_set, (
                f"Waypoint ({wp.x},{wp.y}) at tick {wp.tick} hits a peer claim"
            )

    def test_no_avoid_intervals_falls_back_to_standard_astar(self, open_map_5x5):
        """Passing avoid_intervals=None must still produce a valid path."""
        planner = Planner(open_map_5x5)
        path = planner.plan(_p(0, 0), _p(4, 4), blocked_cells=[], avoid_intervals=None)
        errors = validate_path(path, open_map_5x5)
        assert errors == []

    def test_empty_avoid_intervals_works(self, open_map_5x5):
        planner = Planner(open_map_5x5)
        path = planner.plan(_p(0, 0), _p(4, 4), blocked_cells=[], avoid_intervals=[])
        errors = validate_path(path, open_map_5x5)
        assert errors == []

    def test_peer_claim_different_tick_is_ignored(self, open_map_5x5):
        """A claim at tick 99 must not block movement at tick 1."""
        planner = Planner(open_map_5x5)
        path = planner.plan(
            _p(0, 0), _p(2, 0),
            blocked_cells=[],
            avoid_intervals=[(_p(1, 0), 99)],
            start_tick=0,
        )
        errors = validate_path(path, open_map_5x5)
        assert errors == []
        assert (path.waypoints[-1].x, path.waypoints[-1].y) == (2, 0)


# ═══════════════════════════════════════════════════════════════════════════════
# §10 — replan() dynamic blocked-cell rerouting
# ═══════════════════════════════════════════════════════════════════════════════

class TestReplan:
    """replan() correctly reroutes around a newly blocked cell (§8.4)."""

    def test_replan_avoids_new_blocked_cell(self, wall_map):
        planner = Planner(wall_map)
        initial = planner.plan(_p(0, 9), _p(9, 9), blocked_cells=[], start_tick=0)

        next_cell = initial.waypoints[1]
        new_blocked = [_p(next_cell.x, next_cell.y)]

        replanned = planner.replan(initial, new_blocked_cells=new_blocked, current_tick=0)

        assert isinstance(replanned, RobotPath)
        new_blocked_set = {(p.x, p.y) for p in new_blocked}
        for wp in replanned.waypoints:
            assert (wp.x, wp.y) not in new_blocked_set

    def test_replan_still_reaches_goal(self, open_map_5x5):
        planner = Planner(open_map_5x5)
        initial = planner.plan(_p(0, 0), _p(4, 4), blocked_cells=[], start_tick=0)
        replanned = planner.replan(initial, new_blocked_cells=[_p(2, 2)], current_tick=1)
        last = replanned.waypoints[-1]
        assert (last.x, last.y) == (4, 4)

    def test_replan_version_increments(self, open_map_5x5):
        planner = Planner(open_map_5x5)
        initial = planner.plan(_p(0, 0), _p(4, 0), blocked_cells=[], start_tick=0)
        replanned = planner.replan(initial, new_blocked_cells=[_p(2, 0)], current_tick=1)
        assert replanned.version > initial.version

    def test_replan_path_validity(self, open_map_5x5):
        planner = Planner(open_map_5x5)
        initial = planner.plan(_p(0, 0), _p(4, 4), blocked_cells=[], start_tick=0)
        replanned = planner.replan(initial, new_blocked_cells=[_p(2, 2)], current_tick=2)
        errors = validate_path(replanned, open_map_5x5)
        assert errors == [], f"Replanned path invalid: {errors}"

    def test_replan_blocked_cell_added_to_map(self, open_map_5x5):
        fresh_map = build_warehouse_map(5, 5, [], [], [_p(0, 0)], [_p(4, 4)])
        planner = Planner(fresh_map)
        initial = planner.plan(_p(0, 0), _p(4, 4), blocked_cells=[], start_tick=0)
        planner.replan(initial, new_blocked_cells=[_p(3, 3)], current_tick=2)
        blocked_xy = [(p.x, p.y) for p in fresh_map.blockedCells]
        assert (3, 3) in blocked_xy

    def test_replan_raises_if_goal_unreachable(self):
        obs_map = build_warehouse_map(
            width=5, height=5,
            obstacles=[_p(0, 1), _p(1, 1), _p(2, 1), _p(3, 1), _p(4, 1),
                       _p(0, 2), _p(1, 2), _p(2, 2), _p(3, 2), _p(4, 2),
                       _p(0, 3), _p(1, 3), _p(2, 3), _p(3, 3), _p(4, 3),
                       _p(0, 4), _p(1, 4), _p(2, 4), _p(3, 4), _p(4, 4)],
            choke_points=[], pickup_points=[_p(0, 0)], drop_points=[],
        )
        planner = Planner(obs_map)
        initial = planner.plan(_p(0, 0), _p(4, 0), blocked_cells=[], start_tick=0)
        with pytest.raises(PlanningFailedError):
            planner.replan(
                initial,
                new_blocked_cells=[_p(1, 0), _p(2, 0), _p(3, 0)],
                current_tick=0,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# §11 — plan_centralized() no (cell, tick) collisions
# ═══════════════════════════════════════════════════════════════════════════════

class TestPlanCentralized:
    """plan_centralized() must produce collision-free schedules (§8.5)."""

    def _make_small_map(self) -> WarehouseMap:
        return build_warehouse_map(
            width=10, height=10,
            obstacles=[],
            choke_points=[_p(5, 5)],
            pickup_points=[_p(0, 0), _p(9, 0)],
            drop_points=[_p(0, 9), _p(9, 9)],
        )

    def test_returns_path_for_each_robot(self):
        wmap = self._make_small_map()
        start_goals = {
            "R1": (_p(0, 0), _p(9, 9)),
            "R2": (_p(9, 0), _p(0, 9)),
        }
        result = plan_centralized(start_goals, wmap, seed=42)
        assert set(result.keys()) == {"R1", "R2"}
        for robot_id, path in result.items():
            assert isinstance(path, RobotPath)
            assert path.robotId == robot_id

    def test_no_space_time_collisions_two_robots(self):
        wmap = self._make_small_map()
        start_goals = {
            "R1": (_p(0, 0), _p(9, 9)),
            "R2": (_p(9, 0), _p(0, 9)),
        }
        result = plan_centralized(start_goals, wmap, seed=42)
        space_time: dict[tuple, str] = {}
        for robot_id, path in result.items():
            for wp in path.waypoints:
                key = (wp.x, wp.y, wp.tick)
                assert key not in space_time, (
                    f"Space-time collision at {key}: "
                    f"{space_time[key]} and {robot_id}"
                )
                space_time[key] = robot_id

    def test_no_space_time_collisions_four_robots(self):
        """Four robots, single open map — guaranteed no collisions."""
        wmap = self._make_small_map()
        start_goals = {
            "R1": (_p(0, 0), _p(9, 9)),
            "R2": (_p(9, 0), _p(0, 9)),
            "R3": (_p(0, 9), _p(9, 0)),
            "R4": (_p(9, 9), _p(0, 0)),
        }
        result = plan_centralized(start_goals, wmap, seed=7)
        space_time: dict[tuple, str] = {}
        for robot_id, path in result.items():
            for wp in path.waypoints:
                key = (wp.x, wp.y, wp.tick)
                assert key not in space_time, (
                    f"Space-time collision at {key}: "
                    f"{space_time[key]} and {robot_id}"
                )
                space_time[key] = robot_id

    def test_each_robot_reaches_its_goal(self):
        wmap = self._make_small_map()
        start_goals = {
            "R1": (_p(0, 0), _p(9, 9)),
            "R2": (_p(9, 0), _p(0, 9)),
        }
        result = plan_centralized(start_goals, wmap, seed=0)
        assert (result["R1"].waypoints[-1].x, result["R1"].waypoints[-1].y) == (9, 9)
        assert (result["R2"].waypoints[-1].x, result["R2"].waypoints[-1].y) == (0, 9)

    def test_empty_input_returns_empty_dict(self):
        wmap = self._make_small_map()
        assert plan_centralized({}, wmap, seed=0) == {}

    def test_same_seed_same_order(self):
        """Same seed must always produce the same result (reproducible §19)."""
        wmap = self._make_small_map()
        sg = {
            "R1": (_p(0, 0), _p(9, 9)),
            "R2": (_p(9, 0), _p(0, 9)),
            "R3": (_p(0, 9), _p(9, 0)),
        }
        result_a = plan_centralized(sg, wmap, seed=123)
        result_b = plan_centralized(sg, wmap, seed=123)
        for rid in sg:
            wps_a = [(wp.x, wp.y, wp.tick) for wp in result_a[rid].waypoints]
            wps_b = [(wp.x, wp.y, wp.tick) for wp in result_b[rid].waypoints]
            assert wps_a == wps_b, f"Non-deterministic output for {rid}"

    def test_centralized_paths_are_valid(self):
        wmap = self._make_small_map()
        start_goals = {"R1": (_p(1, 0), _p(8, 9)), "R2": (_p(8, 0), _p(1, 9))}
        result = plan_centralized(start_goals, wmap, seed=1)
        for robot_id, path in result.items():
            errors = validate_path(path, wmap)
            assert errors == [], f"Path for {robot_id} invalid: {errors}"

    def test_start_equals_goal_centralized(self):
        wmap = self._make_small_map()
        start_goals = {"R1": (_p(2, 2), _p(2, 2))}
        result = plan_centralized(start_goals, wmap, seed=0)
        assert len(result["R1"].waypoints) == 1
        assert result["R1"].waypoints[0].x == 2

    def test_invalid_start_raises(self):
        wmap = build_warehouse_map(
            5, 5, [_p(1, 1)], [], [_p(0, 0)], [_p(4, 4)]
        )
        with pytest.raises(InvalidMapError):
            plan_centralized({"R1": (_p(1, 1), _p(4, 4))}, wmap, seed=0)


class TestPlanCentralizedEdgeConflicts:
    """Regression tests for the referee-verified CENTRALIZED_RESERVATION
    collisions the benchmark found in c_narrow_aisle, d_deadlock and
    g_high_load.

    The reservation table used to reserve only vertices (cell, tick). Two
    robots traversing the same edge in opposite directions between the same
    two ticks share NO vertex — A is at u@t and v@t+1, B is at v@t and u@t+1 —
    so a vertex-only table happily schedules them straight through each other.
    simulation/referee.py flags exactly that as a collision (its swap rule).
    """

    @staticmethod
    def _corridor_map(width=8, height=1) -> WarehouseMap:
        """A strictly single-file corridor: swapping is the ONLY way for two
        head-on robots to pass, so any surviving swap shows up immediately."""
        return build_warehouse_map(
            width=width, height=height, obstacles=[], choke_points=[],
            pickup_points=[_p(0, 0)], drop_points=[_p(width - 1, 0)],
        )

    @staticmethod
    def _edge_swaps(result: dict) -> list:
        """Every pair of robots that exchange cells between consecutive ticks.

        Mirrors simulation/referee.py's swap rule, re-derived here rather than
        imported — the referee must stay an independent checker.
        """
        by_robot: dict = {}
        for robot_id, path in result.items():
            by_robot[robot_id] = {wp.tick: (wp.x, wp.y) for wp in path.waypoints}

        swaps = []
        ids = sorted(by_robot)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = by_robot[ids[i]], by_robot[ids[j]]
                for t in sorted(set(a) & set(b)):
                    if (t + 1) in a and (t + 1) in b:
                        if a[t] == b[t + 1] and a[t + 1] == b[t] and a[t] != a[t + 1]:
                            swaps.append((ids[i], ids[j], t))
        return swaps

    def test_head_on_pair_in_single_file_corridor_never_swaps(self):
        """Reproduces c_narrow_aisle / d_deadlock: two robots swapping ends."""
        wmap = self._corridor_map()
        start_goals = {"R1": (_p(0, 0), _p(7, 0)), "R2": (_p(7, 0), _p(0, 0))}

        try:
            result = plan_centralized(start_goals, wmap, seed=42)
        except PlanningFailedError:
            # Refusing to schedule an impossible swap is a correct outcome —
            # in a 1-wide corridor with no passing place there is no
            # collision-free schedule. Silently emitting one is not.
            return

        assert self._edge_swaps(result) == [], "robots swapped through each other"

    def test_three_head_on_pairs_never_swap(self):
        """Reproduces g_high_load, which had three exactly-opposed pairs and
        produced three referee-verified collisions on one tick."""
        wmap = build_warehouse_map(
            width=12, height=6, obstacles=[], choke_points=[],
            pickup_points=[_p(0, 0)], drop_points=[_p(11, 5)],
        )
        start_goals = {
            "R1": (_p(0, 1), _p(11, 1)), "R2": (_p(11, 1), _p(0, 1)),
            "R3": (_p(0, 3), _p(11, 3)), "R4": (_p(11, 3), _p(0, 3)),
            "R5": (_p(0, 5), _p(11, 5)), "R6": (_p(11, 5), _p(0, 5)),
        }

        result = plan_centralized(start_goals, wmap, seed=42)

        assert self._edge_swaps(result) == [], "head-on pairs swapped through each other"

    def test_vertex_freedom_still_holds_alongside_edge_freedom(self):
        """The original guarantee must not regress while fixing edges."""
        wmap = build_warehouse_map(
            width=12, height=6, obstacles=[], choke_points=[],
            pickup_points=[_p(0, 0)], drop_points=[_p(11, 5)],
        )
        start_goals = {
            "R1": (_p(0, 1), _p(11, 1)), "R2": (_p(11, 1), _p(0, 1)),
            "R3": (_p(0, 3), _p(11, 3)), "R4": (_p(11, 3), _p(0, 3)),
        }

        result = plan_centralized(start_goals, wmap, seed=42)

        space_time: dict = {}
        for robot_id, path in result.items():
            for wp in path.waypoints:
                key = (wp.x, wp.y, wp.tick)
                assert key not in space_time, f"vertex collision at {key}"
                space_time[key] = robot_id


# ═══════════════════════════════════════════════════════════════════════════════
# §12 — Demo map structural tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestDemoMap:
    """Verify the demo map is structurally sound and has required choke points."""

    def test_demo_map_loads(self):
        wmap = get_demo_map()
        assert isinstance(wmap, WarehouseMap)

    def test_demo_map_dimensions(self):
        wmap = get_demo_map()
        assert wmap.gridWidth == 20
        assert wmap.gridHeight == 15

    def test_demo_map_has_obstacles(self):
        wmap = get_demo_map()
        assert len(wmap.obstacles) > 0

    def test_demo_map_has_at_least_two_choke_points(self):
        """Spec §8.1 and §17: ≥2–3 unavoidable choke points."""
        wmap = get_demo_map()
        unique_chokes = {(p.x, p.y) for p in wmap.chokePoints}
        assert len(unique_chokes) >= 2, (
            f"Demo map only has {len(unique_chokes)} choke points; need ≥2"
        )

    def test_demo_map_has_pickup_and_drop_points(self):
        wmap = get_demo_map()
        assert len(wmap.pickupPoints) > 0
        assert len(wmap.dropPoints) > 0

    def test_demo_map_choke_points_not_on_obstacles(self):
        wmap = get_demo_map()
        obs_set = {(p.x, p.y) for p in wmap.obstacles}
        for cp in wmap.chokePoints:
            assert (cp.x, cp.y) not in obs_set, (
                f"Choke point ({cp.x},{cp.y}) is on an obstacle"
            )

    def test_demo_map_obstacles_in_bounds(self):
        wmap = get_demo_map()
        for obs in wmap.obstacles:
            assert 0 <= obs.x < wmap.gridWidth
            assert 0 <= obs.y < wmap.gridHeight

    def test_demo_map_blocked_cells_starts_empty(self):
        wmap = get_demo_map()
        assert wmap.blockedCells == []

    def test_demo_map_planner_can_route_across_choke_points(self):
        """A path from top-left to bottom-right must navigate choke points."""
        wmap = get_demo_map()
        planner = Planner(wmap)
        path = planner.plan(_p(1, 0), _p(17, 14), blocked_cells=[], start_tick=0)
        assert (path.waypoints[-1].x, path.waypoints[-1].y) == (17, 14)
        errors = validate_path(path, wmap)
        assert errors == [], f"Demo map path invalid: {errors}"

    def test_demo_map_centralized_four_robots(self):
        """plan_centralized on the real demo map with 4 robots — no collisions."""
        wmap = get_demo_map()
        start_goals = {
            "R1": (_p(1, 0),  _p(17, 14)),
            "R2": (_p(17, 0), _p(1, 14)),
            "R3": (_p(1, 14), _p(17, 0)),
            "R4": (_p(11, 0), _p(1, 11)),
        }
        result = plan_centralized(start_goals, wmap, seed=42)
        assert len(result) == 4
        space_time: dict[tuple, str] = {}
        for robot_id, path in result.items():
            for wp in path.waypoints:
                key = (wp.x, wp.y, wp.tick)
                assert key not in space_time, (
                    f"Collision at {key}: {space_time[key]} vs {robot_id}"
                )
                space_time[key] = robot_id

    def test_demo_map_choke_points_in_bounds(self):
        wmap = get_demo_map()
        for cp in wmap.chokePoints:
            assert 0 <= cp.x < wmap.gridWidth
            assert 0 <= cp.y < wmap.gridHeight
