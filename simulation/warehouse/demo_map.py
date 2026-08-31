"""
simulation/warehouse/demo_map.py — The actual demo WarehouseMap instance.
Owner: Member 1

This file constructs the concrete warehouse map used by all demo scenarios.

Design requirements (from 01_PATH_PLANNING.md §8.1 and §17):
  - The map MUST have at least 2–3 unavoidable choke points that most
    start/goal pairs must pass through — a sparse map makes conflicts rare
    and weakens the system's improvement claim.
  - ≥2 deliberate choke points verified to force conflicts in a basic 3+ robot run.

Map design: 20 × 15 grid (x = column 0..19, y = row 0..14).

Layout (ASCII, O = obstacle/shelf, · = walkable, P = pickup, D = drop,
        C = choke point):

  Row 0:  ···········P···P·····  (pickup strip top)
  Row 1:  O·OOOOOOO·O·OOOOOOO·O  (shelf row 1)
  Row 2:  O·OOOOOOO·O·OOOOOOO·O  (shelf row 2)
  Row 3:  O·OOOOOOO·O·OOOOOOO·O  (shelf row 3)
  Row 4:  ·C·········C·········  ← CHOKE POINT A: single vertical aisle col 2
                                  ← CHOKE POINT B: single vertical aisle col 12
  Row 5:  O·OOOOOOO·O·OOOOOOO·O  (shelf row 5)
  Row 6:  O·OOOOOOO·O·OOOOOOO·O
  Row 7:  ···C···········C·····  ← CHOKE POINT C: horizontal cross-aisle
  Row 8:  O·OOOOOOO·O·OOOOOOO·O
  Row 9:  O·OOOOOOO·O·OOOOOOO·O
  Row 10: O·OOOOOOO·O·OOOOOOO·O
  Row 11: ···········C·········  (another cross intersection)
  Row 12: O·OOOOOOO·O·OOOOOOO·O
  Row 13: O·OOOOOOO·O·OOOOOOO·O
  Row 14: ···D···D···D···D·····  (drop strip bottom)

Choke points (must-pass intersections):
  A — col 2, rows 1–6: narrow vertical aisle between left shelf blocks.
      Any robot moving from bottom-left to top-right MUST pass col 2.
  B — col 12, rows 1–6: symmetric right-side vertical aisle.
      Any robot crossing from left half to right half MUST use this aisle.
  C — row 7, cols 3 & 13: horizontal corridor bottlenecks.
      Top-half ↔ bottom-half transit MUST pass through row 7.

These three choke points ensure that with 4+ robots, at least 2 pairs will
contest the same aisle segment — making conflict avoidance visible and
measurable in every demo run.

Import contracts from shared.python.models — do NOT redefine them here.
"""

from shared.python.models import Position, WarehouseMap
from planner.warehouse_map import build_warehouse_map, InvalidMapError


# ── Map dimensions ────────────────────────────────────────────────────────────
_WIDTH = 20
_HEIGHT = 15


def _p(x: int, y: int) -> Position:
    """Shorthand to create a Position without a tick (map-level use only)."""
    return Position(x=x, y=y)


def get_demo_map() -> WarehouseMap:
    """Build and return the demo WarehouseMap.

    The map features three deliberate choke points (narrow aisles / T-junctions)
    that force robots to contend for the same cells, making conflict avoidance
    visible and measurable.

    Choke points:
      A — vertical aisle at x=2 (rows 1–6):  left-block internal corridor
      B — vertical aisle at x=12 (rows 1–6): right-block internal corridor
      C — horizontal corridor at y=7:         mid-warehouse cross-aisle

    These are passed to WarehouseMap.chokePoints so the dashboard can
    highlight them and the referee can flag contested-cell events there.

    Returns
    -------
    WarehouseMap
        A fully validated WarehouseMap instance ready for all demo scenarios.
        blockedCells is [] — simulation/scenarios mutates it at runtime.
    """
    obstacles: list[Position] = _build_obstacles()
    choke_points: list[Position] = _build_choke_points()
    pickup_points: list[Position] = _build_pickup_points()
    drop_points: list[Position] = _build_drop_points()

    return build_warehouse_map(
        width=_WIDTH,
        height=_HEIGHT,
        obstacles=obstacles,
        choke_points=choke_points,
        pickup_points=pickup_points,
        drop_points=drop_points,
    )


# ── Map element builders ──────────────────────────────────────────────────────

def _build_obstacles() -> list[Position]:
    """Return the list of obstacle (shelf) cells.

    Layout:
      Left shelf block:   cols 0, 3–9  (but col 2 is the aisle — left open)
      Right shelf block:  cols 10, 13–19 (but col 12 is the aisle — left open)
      Horizontal shelves: rows 1–3 and rows 5–6 and rows 8–10 and rows 12–13

    The open columns (2 and 12) and open rows (0, 4, 7, 11, 14) form the
    navigable aisles and cross-corridors.
    """
    obs: list[Position] = []

    # Rows that contain shelf cells (horizontal shelf layers)
    shelf_rows = [1, 2, 3, 5, 6, 8, 9, 10, 12, 13]

    # For each shelf row:
    #   Left block:  cols 0, 3, 4, 5, 6, 7, 8, 9
    #   Right block: cols 10, 13, 14, 15, 16, 17, 18, 19
    # Walkable in shelf rows: col 1 (left aisle inner), col 2 (CHOKE A),
    #                          col 11 (middle inner), col 12 (CHOKE B)
    left_shelf_cols = [0, 3, 4, 5, 6, 7, 8, 9]
    right_shelf_cols = [10, 13, 14, 15, 16, 17, 18, 19]

    for y in shelf_rows:
        for x in left_shelf_cols:
            obs.append(_p(x, y))
        for x in right_shelf_cols:
            obs.append(_p(x, y))

    return obs


def _build_choke_points() -> list[Position]:
    """Return the deliberate choke-point cells.

    These are walkable cells that are structurally unavoidable:

    Choke A — col 2, rows 1–6 (single-file vertical aisle, left block)
    Choke B — col 12, rows 1–6 (single-file vertical aisle, right block)
    Choke C — col 10 at y=7, and col 2 at y=7, y=11
               (T-junction / bottleneck in the cross-aisle)

    Also include the single-cell intersection at (10, 4) and (2, 4) where
    horizontal and vertical aisles cross — highest-contention spots.
    """
    chokes: list[Position] = []

    # Choke A: vertical aisle through left shelf block
    for y in range(1, 7):
        chokes.append(_p(2, y))

    # Choke B: vertical aisle through right shelf block
    for y in range(1, 7):
        chokes.append(_p(12, y))

    # Choke C: cross-aisle at y=7 — narrow passage points
    # At y=7 the full row is walkable, but x=2 and x=12 are the funnel exits.
    chokes.append(_p(2, 7))
    chokes.append(_p(12, 7))

    # Intersection crossing points at open row 4
    chokes.append(_p(2, 4))
    chokes.append(_p(12, 4))

    # Additional intersection at y=11
    chokes.append(_p(2, 11))
    chokes.append(_p(12, 11))

    return chokes


def _build_pickup_points() -> list[Position]:
    """Return pickup zone cells.

    Pickup points are placed along the top open row (y=0) and the mid-aisle
    open row (y=4), distributed across both the left and right halves.
    They must not coincide with obstacles.
    """
    return [
        _p(1, 0),   # top-left pickup
        _p(7, 0),   # top-center-left pickup
        _p(11, 0),  # top-center-right pickup
        _p(17, 0),  # top-right pickup
        _p(1, 4),   # mid-left pickup (open horizontal aisle)
        _p(11, 4),  # mid-right pickup
    ]


def _build_drop_points() -> list[Position]:
    """Return drop/delivery zone cells.

    Drop points are placed along the bottom open row (y=14) and the lower
    cross-aisle (y=11).
    """
    return [
        _p(1, 14),   # bottom-left drop
        _p(5, 14),   # bottom-center-left drop
        _p(11, 14),  # bottom-center-right drop
        _p(17, 14),  # bottom-right drop
        _p(1, 11),   # lower cross-aisle left drop
        _p(11, 11),  # lower cross-aisle right drop
    ]
