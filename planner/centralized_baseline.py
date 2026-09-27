"""
planner/centralized_baseline.py — Centralized reservation-table baseline planner.
Owner: Member 1

Implements the CENTRALIZED_RESERVATION comparison mode used by
simulation/runner.py to benchmark against the decentralized proposed approach.

Algorithm: Sequential prioritized A* against one shared space-time reservation
table.  Each robot is planned in a seed-determined order; once its path is
chosen, the (cell, tick) pairs it occupies are reserved before the next robot
plans.  No two robots are ever assigned the same cell at the same tick
(vertex conflicts), and no two robots are assigned opposite traversals of the
same edge between consecutive ticks (edge/swap conflicts).

This is a strong, realistic baseline — not the weak stop-and-wait strawman.

Reference: Cooperative A* (Silver 2005), CBS (Sharon et al. 2015).

Import contracts from shared.python.models — do NOT redefine them here.
"""

from __future__ import annotations

import heapq
import random
from typing import Optional

from shared.python.models import Position, RobotPath, WarehouseMap
from planner.warehouse_map import InvalidMapError
from planner.astar import PlanningFailedError


# ── Public API ────────────────────────────────────────────────────────────────

def plan_centralized(
    start_goals: dict,      # dict[str, tuple[Position, Position]] — {robotId: (start, goal)}
    warehouse_map: WarehouseMap,
    seed: int,
) -> dict:                  # dict[str, RobotPath]
    """Sequential prioritized A* against one shared space-time reservation table.

    Plans each robot in a seed-determined order (deterministic, reproducible).
    After each robot's path is found, every (cell, tick) pair it occupies is
    entered into the global reservation table so subsequent robots avoid it.

    Parameters
    ----------
    start_goals:
        Mapping from robotId to (start_position, goal_position).
    warehouse_map:
        The loaded WarehouseMap — obstacles and blockedCells are respected.
    seed:
        Random seed controlling the planning order.  Using the same seed on
        the same start_goals always produces the same schedule — required for
        reproducible evaluation runs (§19).

    Returns
    -------
    dict[str, RobotPath]
        One RobotPath per robot.  Guaranteed: no two paths share a (cell, tick)
        pair, and no two paths traverse the same edge in opposite directions
        between consecutive ticks (i.e., zero vertex AND zero edge/swap
        collisions by construction — both of the collision types the
        independent referee in simulation/referee.py checks for).

    Raises
    ------
    PlanningFailedError
        If any robot cannot reach its goal given the reservations already made
        (earlier robots have priority).  The robotId is included in the message.
    InvalidMapError
        If any start or goal is on a permanent obstacle or out of bounds.
    """
    if not start_goals:
        return {}

    # ── Determine planning order ───────────────────────────────────────────────
    rng = random.Random(seed)
    robot_ids = list(start_goals.keys())
    rng.shuffle(robot_ids)

    # ── Shared reservation table ───────────────────────────────────────────────
    # reservation[(x, y, tick)] = robotId that owns that space-time cell.
    reservation: dict[tuple[int, int, int], str] = {}

    results: dict[str, RobotPath] = {}
    width = warehouse_map.gridWidth
    height = warehouse_map.gridHeight

    # Static obstacles (never change).
    static_obstacles: frozenset[tuple[int, int]] = frozenset(
        (p.x, p.y) for p in warehouse_map.obstacles
    )
    # Runtime blocked cells.
    runtime_blocked: frozenset[tuple[int, int]] = frozenset(
        (p.x, p.y) for p in warehouse_map.blockedCells
    )
    all_blocked = static_obstacles | runtime_blocked

    version_counter = 0

    for robot_id in robot_ids:
        start, goal = start_goals[robot_id]

        # Validate cells (raises InvalidMapError on bad input).
        _validate_cell(start, "start", width, height, static_obstacles)
        _validate_cell(goal, "goal", width, height, static_obstacles)

        # Same cell: no movement needed.
        if start.x == goal.x and start.y == goal.y:
            version_counter += 1
            wp = Position(x=start.x, y=start.y, tick=0)
            results[robot_id] = RobotPath(
                robotId=robot_id,
                waypoints=[wp],
                generatedAtTick=0,
                version=version_counter,
            )
            reservation[(start.x, start.y, 0)] = robot_id
            continue

        waypoints = _astar_reserved(
            start_x=start.x,
            start_y=start.y,
            goal_x=goal.x,
            goal_y=goal.y,
            width=width,
            height=height,
            all_blocked=all_blocked,
            reservation=reservation,
        )

        if waypoints is None:
            raise PlanningFailedError(
                start, goal,
                f"robot {robot_id!r} cannot reach goal — blocked by prior reservations"
            )

        # Reserve this robot's path.
        for wp in waypoints:
            reservation[(wp.x, wp.y, wp.tick)] = robot_id

        version_counter += 1
        results[robot_id] = RobotPath(
            robotId=robot_id,
            waypoints=waypoints,
            generatedAtTick=0,
            version=version_counter,
        )

    return results


# ── Private helpers ───────────────────────────────────────────────────────────

def _validate_cell(
    pos: Position,
    label: str,
    width: int,
    height: int,
    static_obstacles: frozenset,
) -> None:
    """Raise InvalidMapError if pos is out of bounds or on a static obstacle."""
    if not (0 <= pos.x < width and 0 <= pos.y < height):
        raise InvalidMapError(
            f"{label} ({pos.x},{pos.y}) out of bounds for {width}×{height} grid."
        )
    if (pos.x, pos.y) in static_obstacles:
        raise InvalidMapError(
            f"{label} ({pos.x},{pos.y}) is on a permanent obstacle."
        )


def _astar_reserved(
    start_x: int,
    start_y: int,
    goal_x: int,
    goal_y: int,
    width: int,
    height: int,
    all_blocked: frozenset,          # frozenset[tuple[int,int]]
    reservation: dict,               # dict[tuple[int,int,int], str] — shared table
) -> Optional[list]:                 # Optional[list[Position]]
    """Space-time A* that avoids cells and edges already reserved by prior robots.

    Rejects both conflict types the referee checks: vertex conflicts (two
    robots in one cell at one tick) and edge/swap conflicts (two robots
    exchanging cells between consecutive ticks, which shares no vertex and so
    is invisible to a vertex-only reservation table).

    Waiting in place (cost +1 tick) is permitted so robots can queue behind
    earlier robots at choke points.  Max search depth: width*height*3 ticks.

    Returns None if no path exists, list[Position] with .tick set otherwise.
    """
    _MOVES = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    max_tick = width * height * 3

    start_h = abs(start_x - goal_x) + abs(start_y - goal_y)
    # open: (f, g, x, y, tick)
    open_set: list = []
    heapq.heappush(open_set, (start_h, 0, start_x, start_y, 0))

    came_from: dict[tuple, tuple] = {}
    g_score: dict[tuple, int] = {(start_x, start_y, 0): 0}

    while open_set:
        f, g, cx, cy, ct = heapq.heappop(open_set)

        if g > g_score.get((cx, cy, ct), float("inf")):
            continue  # stale entry

        if cx == goal_x and cy == goal_y:
            # Reconstruct path
            path: list[Position] = []
            cur = (cx, cy, ct)
            while cur in came_from:
                x, y, t = cur
                path.append(Position(x=x, y=y, tick=t))
                cur = came_from[cur]
            sx, sy, st = cur
            path.append(Position(x=sx, y=sy, tick=st))
            path.reverse()
            return path

        next_tick = ct + 1
        if next_tick > max_tick:
            continue

        for dx, dy in _MOVES:
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if (nx, ny) in all_blocked:
                continue
            if (nx, ny, next_tick) in reservation:
                continue  # vertex conflict: already claimed by a prior robot

            # Edge (swap) conflict: a prior robot sits in the cell we want to
            # move INTO at the current tick and moves INTO the cell we are
            # leaving on the next tick — i.e. it is coming the other way
            # through this very edge. No vertex is ever shared, so the vertex
            # check above cannot see it, yet the two robots pass through each
            # other. This is the classic MAPF edge conflict, and it is exactly
            # what simulation/referee.py's swap rule flags as a collision.
            occupant_ahead = reservation.get((nx, ny, ct))
            if occupant_ahead is not None and reservation.get((cx, cy, next_tick)) == occupant_ahead:
                continue

            new_g = g + 1
            state = (nx, ny, next_tick)
            if new_g < g_score.get(state, float("inf")):
                g_score[state] = new_g
                came_from[state] = (cx, cy, ct)
                h = abs(nx - goal_x) + abs(ny - goal_y)
                heapq.heappush(open_set, (new_g + h, new_g, nx, ny, next_tick))

        # Wait in place — allows queueing at choke points
        if (cx, cy, next_tick) not in reservation:
            new_g = g + 1
            state = (cx, cy, next_tick)
            if new_g < g_score.get(state, float("inf")):
                g_score[state] = new_g
                came_from[state] = (cx, cy, ct)
                h = abs(cx - goal_x) + abs(cy - goal_y)
                heapq.heappush(open_set, (new_g + h, new_g, cx, cy, next_tick))

    return None
