"""Scenario B — Intersection Conflict.

Two robots converge on the same intersection cell at approximately the
same tick, triggering conflict detection and deterministic priority resolution.

Owner: Member 3.
"""

from shared.python.models import Position, WarehouseMap
from simulation.scenarios import Scenario
from simulation.warehouse.demo_map import get_demo_map


def get_scenario(seed: int = 42, warehouse_map: WarehouseMap | None = None) -> Scenario:
    # Two coordinate fixtures, deliberately kept separate (see CLAUDE.md's
    # live-demo compatibility audit):
    #   1. LIVE DEMO (warehouse_map is None): the original (10,9) intersection
    #      and every original coordinate are obstacles in the real
    #      demo_map.py. Use the real chokepoint (12,7) instead - where
    #      demo_map.py's own vertical aisle B crosses its horizontal
    #      cross-aisle row 7 - with the same symmetric 4-cell approach
    #      distance the original design used, on this branch ONLY.
    #   2. EXPLICIT MAP (benchmark/tests): keep the exact original literals,
    #      unchanged.
    using_real_demo_map = warehouse_map is None
    if warehouse_map is None:
        warehouse_map = get_demo_map()

    if using_real_demo_map:
        # Intersection at (12, 7) - a real demo_map.py chokepoint.
        r1_start, r1_goal = Position(x=8, y=7), Position(x=16, y=7)
        r2_start, r2_goal = Position(x=12, y=3), Position(x=12, y=11)
    else:
        # Intersection at (10, 9)
        r1_start, r1_goal = Position(x=6, y=9), Position(x=14, y=9)
        r2_start, r2_goal = Position(x=10, y=5), Position(x=10, y=13)

    robots = [
        {
            "robotId": "R1",
            "start": r1_start,
            "goal": r1_goal,
            "priority": 3,  # Higher priority -> wins intersection
        },
        {
            "robotId": "R2",
            "start": r2_start,
            "goal": r2_goal,
            "priority": 1,  # Lower priority -> waits
        },
    ]
    return Scenario(
        scenario_id="b_intersection",
        name="Scenario B — Intersection Conflict",
        description="Two robots converging orthogonally on the intersection at (10, 9).",
        robots=robots,
        warehouse_map=warehouse_map,
        max_ticks=40,
        events=[],
    )
