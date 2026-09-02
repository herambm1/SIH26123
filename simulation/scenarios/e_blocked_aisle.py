"""Scenario E — Blocked Aisle.

An aisle becomes blocked mid-simulation (SimulationEvent AISLE_BLOCKED).
Affected robots detect the obstacle and dynamically reroute around it.

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
            "start": Position(x=2, y=9),
            "goal": Position(x=16, y=9),
            "priority": 2,
        },
    ]
    # Block cell (10, 9) at tick 4
    events = [
        {
            "tick": 4,
            "type": "AISLE_BLOCKED",
            "payload": {"cell": Position(x=10, y=9)},
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
