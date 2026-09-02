"""Scenario G — High Fleet Load.

Maximum number of robots (6 AMRs) operating simultaneously on the dense demo map.
Tests throughput and conflict-resolution performance under high concurrency.

Owner: Member 3.
"""

from shared.python.models import Position, WarehouseMap
from simulation.scenarios import Scenario
from simulation.warehouse.demo_map import get_demo_map


def get_scenario(seed: int = 42, warehouse_map: WarehouseMap | None = None) -> Scenario:
    if warehouse_map is None:
        warehouse_map = get_demo_map()

    robots = [
        {"robotId": "R1", "start": Position(x=2, y=2), "goal": Position(x=17, y=2), "priority": 3},
        {"robotId": "R2", "start": Position(x=17, y=2), "goal": Position(x=2, y=2), "priority": 2},
        {"robotId": "R3", "start": Position(x=2, y=17), "goal": Position(x=17, y=17), "priority": 2},
        {"robotId": "R4", "start": Position(x=17, y=17), "goal": Position(x=2, y=17), "priority": 1},
        {"robotId": "R5", "start": Position(x=10, y=2), "goal": Position(x=10, y=17), "priority": 3},
        {"robotId": "R6", "start": Position(x=10, y=17), "goal": Position(x=10, y=2), "priority": 1},
    ]
    return Scenario(
        scenario_id="g_high_load",
        name="Scenario G — High Fleet Load",
        description="6 AMRs crossing intersecting warehouse aisles concurrently.",
        robots=robots,
        warehouse_map=warehouse_map,
        max_ticks=60,
        events=[],
    )
