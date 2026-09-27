"""Scenario D — Deadlock.

Multiple robots face each other in a corridor and wait on each other.
Tests deadlock detection (5-tick stall heuristic) and forced-yield recovery.

Owner: Member 3.
"""

from shared.python.models import Position, WarehouseMap
from simulation.scenarios import Scenario
from simulation.warehouse.demo_map import get_demo_map


def get_scenario(seed: int = 42, warehouse_map: WarehouseMap | None = None) -> Scenario:
    # Two coordinate fixtures, deliberately kept separate (see CLAUDE.md's
    # live-demo compatibility audit):
    #   1. LIVE DEMO (warehouse_map is None): R1's original start (8,9) and
    #      R2's original goal (8,9) are obstacle cells in the real
    #      demo_map.py. Use the OTHER real vertical aisle (column 12) over
    #      the same 4-cell separation, on this branch ONLY - the short
    #      head-on approach combined with the unchanged delay_ticks=1 fault
    #      below is what actually produces the genuine mutual-wait/deadlock,
    #      not the specific column chosen.
    #   2. EXPLICIT MAP (benchmark/tests): keep the exact original literals,
    #      unchanged.
    using_real_demo_map = warehouse_map is None
    if warehouse_map is None:
        warehouse_map = get_demo_map()

    if using_real_demo_map:
        # Column 12 (demo_map.py's "Choke B"), short 4-cell head-on span.
        r1_start, r1_goal = Position(x=12, y=4), Position(x=12, y=8)
        r2_start, r2_goal = Position(x=12, y=8), Position(x=12, y=4)
    else:
        r1_start, r1_goal = Position(x=8, y=9), Position(x=12, y=9)
        r2_start, r2_goal = Position(x=12, y=9), Position(x=8, y=9)

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
            "priority": 1,
        },
    ]
    return Scenario(
        scenario_id="d_deadlock",
        name="Scenario D — Deadlock",
        description="Deadlock situation resolving via N-tick stall and forced yield.",
        robots=robots,
        warehouse_map=warehouse_map,
        max_ticks=50,
        events=[],
        fault_config={"delay_ticks": 1},
    )
