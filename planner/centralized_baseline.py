"""
planner/centralized_baseline.py — Centralized reservation-table baseline planner.
Owner: Member 1

This module implements the CENTRALIZED_RESERVATION comparison mode used by
simulation/runner.py to benchmark against the decentralized approach.

Import contracts from shared.python.models — do NOT redefine them here.
"""

from shared.python.models import Position, RobotPath, WarehouseMap


def plan_centralized(
    start_goals: dict,       # dict[str, tuple[Position, Position]]  — {robotId: (start, goal)}
    warehouse_map: WarehouseMap,
    seed: int,
) -> dict:                   # dict[str, RobotPath]
    """Sequential prioritized A* against one shared space-time reservation table.

    Plans each robot in a seed-determined order. Each robot's chosen path reserves
    its (cell, tick) pairs before the next robot plans — no two robots claim the
    same cell at the same tick.

    This is what CENTRALIZED_RESERVATION mode uses: a strong, realistic baseline,
    not the weak stop-and-wait strawman.

    Implementation: Member 1's responsibility (Phase 4+).
    """
    raise NotImplementedError
