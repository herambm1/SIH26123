"""Scenario D — Deadlock.

Multiple robots face each other in a corridor and wait on each other.
Tests deadlock detection (5-tick stall heuristic) and forced-yield recovery.

Owner: Member 3.
"""

from shared.python.models import Position, WarehouseMap
from simulation.scenarios import Scenario
from simulation.warehouse.demo_map import get_demo_map


def get_scenario(seed: int = 42, warehouse_map: WarehouseMap | None = None) -> Scenario:
    if warehouse_map is None:
        warehouse_map = get_demo_map()

    robots = [
        {
            "robotId": "R1",
            "start": Position(x=8, y=9),
            "goal": Position(x=12, y=9),
            "priority": 2,
        },
        {
            "robotId": "R2",
            "start": Position(x=12, y=9),
            "goal": Position(x=8, y=9),
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
