"""Scenario E — Blocked Aisle.

An aisle becomes blocked mid-simulation (SimulationEvent AISLE_BLOCKED).
Affected robots detect the obstacle and dynamically reroute around it.

Owner: Member 3.
"""

from shared.python.models import Position, WarehouseMap
from simulation.scenarios import Scenario
from simulation.warehouse.demo_map import get_demo_map


def get_scenario(seed: int = 42, warehouse_map: WarehouseMap | None = None) -> Scenario:
    # Two coordinate fixtures, deliberately kept separate (see CLAUDE.md's
    # live-demo compatibility audit):
    #   1. LIVE DEMO (warehouse_map is None): the original goal (16,9) and
    #      the original blocked cell (10,9) are obstacles in the real
    #      demo_map.py. Use the open cross-aisle row 7 for the full
    #      traversal, with the blocked cell at the same relative midpoint
    #      (10,7), on this branch ONLY. Row 7 is only 1 cell wide between
    #      the vertical aisle columns, so blocking it still forces a real
    #      detour (via column 2 or 12), not a trivial sidestep.
    #   2. EXPLICIT MAP (benchmark/tests): keep the exact original literals,
    #      unchanged.
    using_real_demo_map = warehouse_map is None
    if warehouse_map is None:
        warehouse_map = get_demo_map()

    if using_real_demo_map:
        r1_start, r1_goal = Position(x=1, y=7), Position(x=18, y=7)
        blocked_cell = Position(x=10, y=7)
    else:
        r1_start, r1_goal = Position(x=2, y=9), Position(x=16, y=9)
        blocked_cell = Position(x=10, y=9)

    robots = [
        {
            "robotId": "R1",
            "start": r1_start,
            "goal": r1_goal,
            "priority": 2,
        },
    ]
    # Block the aisle cell at tick 4 (tick/type unchanged)
    events = [
        {
            "tick": 4,
            "type": "AISLE_BLOCKED",
            "payload": {"cell": blocked_cell},
        }
    ]
    return Scenario(
        scenario_id="e_blocked_aisle",
        name="Scenario E — Blocked Aisle",
        description="Dynamic obstacle appears at tick 4, forcing dynamic rerouting.",
        robots=robots,
        warehouse_map=warehouse_map,
        max_ticks=50,
        events=events,
    )
