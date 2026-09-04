"""Scenario H — Negative Control.

A scenario with no possible conflicts: robots have non-overlapping routes
and sufficient space to reach their goals without contention.

Purpose: preempt the judge question "did you cherry-pick scenarios where
your system looks good?" by demonstrating that the system correctly reports
zero conflicts when none are structurally possible.

Owner: Member 3.
"""

from shared.python.models import Position, WarehouseMap
from simulation.scenarios import Scenario
from simulation.warehouse.demo_map import get_demo_map


def get_scenario(seed: int = 42, warehouse_map: WarehouseMap | None = None) -> Scenario:
    if warehouse_map is None:
        warehouse_map = get_demo_map()

    # 3 robots operating in parallel, widely separated corridors
    robots = [
        {"robotId": "R1", "start": Position(x=1, y=1), "goal": Position(x=10, y=1), "priority": 1},
        {"robotId": "R2", "start": Position(x=1, y=10), "goal": Position(x=10, y=10), "priority": 1},
        {"robotId": "R3", "start": Position(x=1, y=18), "goal": Position(x=10, y=18), "priority": 1},
    ]
    return Scenario(
        scenario_id="h_negative_control",
        name="Scenario H — Negative Control",
        description="Non-overlapping parallel trajectories verifying zero false positive conflicts.",
        robots=robots,
        warehouse_map=warehouse_map,
        max_ticks=30,
        events=[],
    )
