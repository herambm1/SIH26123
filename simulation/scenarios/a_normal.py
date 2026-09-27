"""Scenario A — Normal Movement.

Robots navigate from their start positions to their goals without any scripted
conflict events. Used to verify baseline path planning and movement correctness.

Owner: Member 3.
"""

from shared.python.models import Position, WarehouseMap
from simulation.scenarios import Scenario
from simulation.warehouse.demo_map import get_demo_map


def get_scenario(seed: int = 42, warehouse_map: WarehouseMap | None = None) -> Scenario:
    # Two coordinate fixtures, deliberately kept separate:
    #   1. LIVE DEMO (warehouse_map is None -> the real demo_map.py fallback):
    #      the original (2,2)/(8,2)/(2,17)/(8,17) coordinates are invalid
    #      against demo_map.py's real obstacle layout (see CLAUDE.md's live-
    #      demo compatibility audit) - (8,2) is a shelf obstacle and y=17 is
    #      out of the real 15-row map entirely. Use demo-map-compatible
    #      coordinates on this branch ONLY.
    #   2. EXPLICIT MAP (benchmark/tests always pass their own map): keep the
    #      exact original literals below, unchanged - this is what every
    #      benchmark run and test has always used and must keep using.
    using_real_demo_map = warehouse_map is None
    if warehouse_map is None:
        warehouse_map = get_demo_map()

    if using_real_demo_map:
        # Row 4 / row 11: demo_map.py's own open cross-aisle rows, full
        # width walkable - two independent, non-touching lanes.
        r1_start, r1_goal = Position(x=1, y=4), Position(x=17, y=4)
        r2_start, r2_goal = Position(x=1, y=11), Position(x=17, y=11)
    else:
        r1_start, r1_goal = Position(x=2, y=2), Position(x=8, y=2)
        r2_start, r2_goal = Position(x=2, y=17), Position(x=8, y=17)

    robots = [
        {
            "robotId": "R1",
            "start": r1_start,
            "goal": r1_goal,
            "priority": 2,
        },
        {
            "robotId": "R2",
            "start": r2_start,
            "goal": r2_goal,
            "priority": 2,
        },
    ]
    return Scenario(
        scenario_id="a_normal",
        name="Scenario A — Normal Movement",
        description="Two robots navigating on independent, non-conflicting paths.",
        robots=robots,
        warehouse_map=warehouse_map,
        max_ticks=40,
        events=[],
    )
