"""Scenario F — Task Reassignment.

A robot goes OFFLINE mid-task (via sensorHealth=OFFLINE fault injection).
Its in-progress task is automatically reassigned to the next available robot.

Owner: Member 3.
"""

from shared.python.models import Position, WarehouseMap
from simulation.scenarios import Scenario
from simulation.warehouse.demo_map import get_demo_map


def get_scenario(seed: int = 42, warehouse_map: WarehouseMap | None = None) -> Scenario:
    # Two coordinate fixtures, deliberately kept separate (see CLAUDE.md's
    # live-demo compatibility audit):
    #   1. LIVE DEMO (warehouse_map is None): R1's original goal (10,2) is an
    #      obstacle, and R2's original idle position (2,17) is out of bounds,
    #      in the real demo_map.py. Give R1 a real, full-width in-progress
    #      trip along open row 4, and R2 an idle position on a different
    #      open row (11) - not on R1's path - on this branch ONLY.
    #   2. EXPLICIT MAP (benchmark/tests): keep the exact original literals,
    #      unchanged.
    using_real_demo_map = warehouse_map is None
    if warehouse_map is None:
        warehouse_map = get_demo_map()

    if using_real_demo_map:
        r1_start, r1_goal = Position(x=1, y=4), Position(x=17, y=4)
        r2_idle = Position(x=1, y=11)
    else:
        r1_start, r1_goal = Position(x=2, y=2), Position(x=10, y=2)
        r2_idle = Position(x=2, y=17)

    robots = [
        {
            "robotId": "R1",
            "start": r1_start,
            "goal": r1_goal,
            "priority": 3,
        },
        {
            "robotId": "R2",
            "start": r2_idle,
            "goal": r2_idle,  # Idle backup robot
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
