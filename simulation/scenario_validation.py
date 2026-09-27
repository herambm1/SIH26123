"""simulation/scenario_validation.py — generic, reusable scenario-position
validator. Owner: Member 3.

Added after a live-demo compatibility audit (see CLAUDE.md) found 8 of 9
scenarios had start/goal/scripted-event-cell coordinates that were invalid
(out of bounds, on an obstacle, or unreachable) against the real
demo_map.py fallback map used by the live Java-driven path. This module is
a read-only CHECKER, not a repair mechanism: it never modifies a Scenario,
a WarehouseMap, or simulation behavior, and it is not called anywhere in
the live tick loop (simulation/runner.py) or in get_scenario() itself.
It exists purely so a test can fail clearly and precisely if a future
scenario edit (or a future map edit) reintroduces this exact class of bug.

Reuses the SAME GridAStarPlanner already used everywhere else in the
simulation (simulation/runner.py) for the real path-existence check -
no reimplementation of pathfinding logic.
"""

from __future__ import annotations

from shared.python.models import Position


def validate_scenario_positions(scenario) -> list[str]:
    """Return a list of human-readable problems with `scenario`'s own
    start/goal/scripted-event-cell positions against its own
    `scenario.warehouse_map` - empty list means everything checked out.

    Checks, per robot: start/goal in bounds, not on an obstacle cell, and
    (for a genuine start != goal pair) that GridAStarPlanner can actually
    find a path between them. Also checks any scripted event payload that
    carries a `cell` (e.g. AISLE_BLOCKED) is itself a valid, in-bounds,
    non-obstacle cell.

    Never raises for an invalid scenario - invalid input is reported back
    as a problem string, exactly like any other finding here.
    """
    # Imported lazily to avoid a module-load cycle (simulation.runner also
    # imports scenario machinery indirectly via demo scenarios/tests).
    from simulation.runner import GridAStarPlanner

    problems: list[str] = []
    wm = scenario.warehouse_map
    obstacles = {(p.x, p.y) for p in wm.obstacles}
    width, height = wm.gridWidth, wm.gridHeight

    def in_bounds(p: Position) -> bool:
        return 0 <= p.x < width and 0 <= p.y < height

    def check_point(label: str, p: Position) -> bool:
        """Returns True if `p` is a valid, walkable cell."""
        if not in_bounds(p):
            problems.append(f"{label} {(p.x, p.y)} is out of bounds for a {width}x{height} map")
            return False
        if (p.x, p.y) in obstacles:
            problems.append(f"{label} {(p.x, p.y)} is on an obstacle cell")
            return False
        return True

    planner = GridAStarPlanner(wm)
    for robot in scenario.robots:
        rid = robot.get("robotId", "<unknown>")
        start, goal = robot["start"], robot["goal"]
        start_ok = check_point(f"{rid}.start", start)
        goal_ok = check_point(f"{rid}.goal", goal)
        if not (start_ok and goal_ok):
            continue
        if start.x == goal.x and start.y == goal.y:
            continue  # a deliberately idle robot (start == goal) needs no path
        try:
            result = planner.plan(start, goal, start_tick=0)
            waypoints = result.waypoints if hasattr(result, "waypoints") else result
            if not waypoints:
                problems.append(f"{rid}: no path found from start to goal")
        except Exception as e:  # noqa: BLE001 - reported as a finding, not raised
            problems.append(f"{rid}: planner raised {e!r} while planning start->goal")

    for event in scenario.events:
        cell = event.get("payload", {}).get("cell")
        if cell is not None:
            check_point(f"scripted event {event.get('type', '<unknown>')!r} cell", cell)

    return problems
