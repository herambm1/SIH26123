"""
planner/warehouse_map.py — Warehouse map builder.
Owner: Member 1

Import contracts from shared.python.models — do NOT redefine them here.
"""

from shared.python.models import Position, WarehouseMap


class InvalidMapError(Exception):
    """Raised when the warehouse map configuration is invalid (e.g., start/goal on an obstacle cell)."""


def build_warehouse_map(
    width: int,
    height: int,
    obstacles: list,           # list[Position]
    choke_points: list,        # list[Position]
    pickup_points: list,       # list[Position]
    drop_points: list,         # list[Position]
) -> WarehouseMap:
    """Build and return a WarehouseMap from the given grid parameters.

    Validates that the map is well-formed (non-zero dimensions, obstacle cells are
    within bounds, etc.) and raises InvalidMapError if not.

    Implementation: Member 1's responsibility.
    """
    raise NotImplementedError
