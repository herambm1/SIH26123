"""
simulation/warehouse/demo_map.py — The actual demo WarehouseMap instance.
Owner: Member 1

This file constructs the concrete warehouse map used by all demo scenarios.
Design requirement: the map MUST have at least 2–3 unavoidable choke points
that most start/goal pairs must pass through — a sparse map makes conflicts
rare and weakens the system's improvement claim.

Import contracts from shared.python.models — do NOT redefine them here.
"""

from shared.python.models import WarehouseMap
from planner.warehouse_map import build_warehouse_map, InvalidMapError


def get_demo_map() -> WarehouseMap:
    """Build and return the demo WarehouseMap.

    The map must feature deliberate choke points (narrow aisles / intersections)
    that force robots to contend for the same cells, making conflict avoidance
    visible and measurable.

    Implementation: Member 1's responsibility.
    """
    raise NotImplementedError
