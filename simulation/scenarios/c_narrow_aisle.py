"""Scenario C — Narrow Aisle Head-On.

Two robots enter a single-file narrow aisle from opposite ends, creating a
NARROW_AISLE_HEADON conflict that must be resolved by one robot yielding.

Owner: Member 3.
"""

from shared.python.models import Position, WarehouseMap
from simulation.scenarios import Scenario
from simulation.warehouse.demo_map import get_demo_map


def get_scenario(seed: int = 42, warehouse_map: WarehouseMap | None = None) -> Scenario:
    # Two coordinate fixtures, deliberately kept separate (see CLAUDE.md's
    # live-demo compatibility audit):
    #   1. LIVE DEMO (warehouse_map is None): the original y=9, x=5..13 aisle
    #      is entirely obstacle cells in the real demo_map.py. Reuse
    #      demo_map.py's own explicitly-documented single-file vertical
    #      aisle (column 2, "Choke A") for a real head-on approach instead,
    #      on this branch ONLY.
    #   2. EXPLICIT MAP (benchmark/tests): keep the exact original literals,
    #      unchanged.
    using_real_demo_map = warehouse_map is None
    if warehouse_map is None:
        warehouse_map = get_demo_map()

    if using_real_demo_map:
        # Single-file vertical aisle at column 2 (demo_map.py's "Choke A").
        r1_start, r1_goal = Position(x=2, y=1), Position(x=2, y=13)
        r2_start, r2_goal = Position(x=2, y=13), Position(x=2, y=1)
    else:
        # Aisle along y=9 from x=5 to x=13
        r1_start, r1_goal = Position(x=5, y=9), Position(x=13, y=9)
        r2_start, r2_goal = Position(x=13, y=9), Position(x=5, y=9)

    robots = [
        {
            "robotId": "R1",
            "start": r1_start,
            "goal": r1_goal,
            "priority": 2,  # Higher priority
        },
        {
            "robotId": "R2",
            "start": r2_start,
            "goal": r2_goal,
            "priority": 1,  # Lower priority -> yields / reroutes
        },
    ]
    return Scenario(
        scenario_id="c_narrow_aisle",
        name="Scenario C — Narrow Aisle Head-On",
        description="Head-on conflict along a single-file aisle with forced yield.",
        robots=robots,
        warehouse_map=warehouse_map,
        max_ticks=50,
        events=[],
    )
