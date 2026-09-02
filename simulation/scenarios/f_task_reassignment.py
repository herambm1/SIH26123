"""Scenario F — Task Reassignment.

A robot goes OFFLINE mid-task (via sensorHealth=OFFLINE fault injection).
Its in-progress task is automatically reassigned to the next available robot.

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
            "goal": Position(x=10, y=2),
            "priority": 3,
        },
        {
            "robotId": "R2",
            "start": Position(x=2, y=17),
            "goal": Position(x=2, y=17),  # Idle backup robot
            "priority": 1,
        },
    ]
    # R1 goes OFFLINE at tick 5
    fault_config = {
        "offline_robots": {"R1": 5}
    }
    return Scenario(
        scenario_id="f_task_reassignment",
        name="Scenario F — Task Reassignment",
        description="Robot R1 fails offline at tick 5, triggering task reassignment to idle peer.",
        robots=robots,
        warehouse_map=warehouse_map,
        max_ticks=40,
        events=[],
        fault_config=fault_config,
    )
