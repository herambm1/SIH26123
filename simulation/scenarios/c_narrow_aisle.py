"""Scenario C — Narrow Aisle Head-On.

Two robots enter a single-file narrow aisle from opposite ends, creating a
NARROW_AISLE_HEADON conflict that must be resolved by one robot yielding.

Owner: Member 3.
"""

from shared.python.models import Position, WarehouseMap
from simulation.scenarios import Scenario
from simulation.warehouse.demo_map import get_demo_map


def get_scenario(seed: int = 42, warehouse_map: WarehouseMap | None = None) -> Scenario:
    if warehouse_map is None:
        warehouse_map = get_demo_map()

    # Aisle along y=9 from x=5 to x=13
    robots = [
        {
            "robotId": "R1",
            "start": Position(x=5, y=9),
            "goal": Position(x=13, y=9),
            "priority": 2,  # Higher priority
        },
        {
            "robotId": "R2",
            "start": Position(x=13, y=9),
            "goal": Position(x=5, y=9),
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
