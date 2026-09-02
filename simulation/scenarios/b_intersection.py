"""Scenario B — Intersection Conflict.

Two robots converge on the same intersection cell at approximately the
same tick, triggering conflict detection and deterministic priority resolution.

Owner: Member 3.
"""

from shared.python.models import Position, WarehouseMap
from simulation.scenarios import Scenario
from simulation.warehouse.demo_map import get_demo_map


def get_scenario(seed: int = 42, warehouse_map: WarehouseMap | None = None) -> Scenario:
    if warehouse_map is None:
        warehouse_map = get_demo_map()

    # Intersection at (10, 9)
    robots = [
        {
            "robotId": "R1",
            "start": Position(x=6, y=9),
            "goal": Position(x=14, y=9),
            "priority": 3,  # Higher priority -> wins intersection
        },
        {
            "robotId": "R2",
            "start": Position(x=10, y=5),
            "goal": Position(x=10, y=13),
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
