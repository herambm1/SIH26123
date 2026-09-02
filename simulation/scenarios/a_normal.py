"""Scenario A — Normal Movement.

Robots navigate from their start positions to their goals without any scripted
conflict events. Used to verify baseline path planning and movement correctness.

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
            "start": Position(x=2, y=2),
            "goal": Position(x=8, y=2),
            "priority": 2,
        },
        {
            "robotId": "R2",
            "start": Position(x=2, y=17),
            "goal": Position(x=8, y=17),
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
