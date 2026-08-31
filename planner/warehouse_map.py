"""
planner/warehouse_map.py — Warehouse map builder.
Owner: Member 1

Builds WarehouseMap instances from grid parameters.  The map is a 2-D grid
where each cell is either walkable or an obstacle.  choke_points are specific
cells deliberately marked as narrow single-file aisles or intersections — they
are passed through to WarehouseMap so that other modules (dashboard, referee)
can highlight them without re-deriving them.

Import contracts from shared.python.models — do NOT redefine them here.
"""

from shared.python.models import Position, WarehouseMap


class InvalidMapError(Exception):
    """Raised when the warehouse map configuration is invalid.

    Examples:
    - Non-positive grid dimensions.
    - A Position whose x or y is outside the grid bounds.
    - An obstacle placed on a pickup, drop, or choke point.
    - A choke point or pickup/drop point that is out of bounds.
    """


# ── Helpers ──────────────────────────────────────────────────────────────────

def _in_bounds(pos: Position, width: int, height: int) -> bool:
    """Return True iff pos falls within the [0, width) × [0, height) grid."""
    return 0 <= pos.x < width and 0 <= pos.y < height


def _validate_positions(
    positions: list,  # list[Position]
    label: str,
    width: int,
    height: int,
) -> None:
    """Raise InvalidMapError if any Position in *positions* is out of bounds."""
    for pos in positions:
        if not _in_bounds(pos, width, height):
            raise InvalidMapError(
                f"{label} position ({pos.x}, {pos.y}) is out of bounds "
                f"for a {width}×{height} grid."
            )


# ── Public API ────────────────────────────────────────────────────────────────

def build_warehouse_map(
    width: int,
    height: int,
    obstacles: list,        # list[Position]
    choke_points: list,     # list[Position]
    pickup_points: list,    # list[Position]
    drop_points: list,      # list[Position]
) -> WarehouseMap:
    """Build and return a WarehouseMap from the given grid parameters.

    Validates that the map is well-formed and raises InvalidMapError if not:
    - width and height must be positive integers.
    - All obstacle, choke_point, pickup_point, and drop_point Positions must
      be within [0, width) × [0, height).
    - Pickup and drop points must not lie on obstacle cells.
    - Choke points must not lie on obstacle cells (they are walkable by
      definition — they are contested, not blocked).

    Does NOT validate start/goal positions — that is the Planner's job at
    plan-time, since start and goal come from TaskAssignment, not the map.

    Returns a WarehouseMap with blockedCells=[] (runtime-mutable by
    simulation/scenarios).
    """
    # ── Dimension validation ─────────────────────────────────────────────────
    if not isinstance(width, int) or not isinstance(height, int):
        raise InvalidMapError(
            f"Grid dimensions must be integers, got width={width!r}, height={height!r}."
        )
    if width <= 0 or height <= 0:
        raise InvalidMapError(
            f"Grid dimensions must be positive, got width={width}, height={height}."
        )

    # ── Bounds validation ────────────────────────────────────────────────────
    _validate_positions(obstacles, "obstacle", width, height)
    _validate_positions(choke_points, "choke_point", width, height)
    _validate_positions(pickup_points, "pickup_point", width, height)
    _validate_positions(drop_points, "drop_point", width, height)

    # ── Cross-field validation ───────────────────────────────────────────────
    obstacle_set: set[tuple[int, int]] = {(p.x, p.y) for p in obstacles}

    for pos in pickup_points:
        if (pos.x, pos.y) in obstacle_set:
            raise InvalidMapError(
                f"Pickup point ({pos.x}, {pos.y}) coincides with an obstacle cell."
            )
    for pos in drop_points:
        if (pos.x, pos.y) in obstacle_set:
            raise InvalidMapError(
                f"Drop point ({pos.x}, {pos.y}) coincides with an obstacle cell."
            )
    for pos in choke_points:
        if (pos.x, pos.y) in obstacle_set:
            raise InvalidMapError(
                f"Choke point ({pos.x}, {pos.y}) coincides with an obstacle cell. "
                "Choke points must be walkable (contested, not blocked)."
            )

    return WarehouseMap(
        gridWidth=width,
        gridHeight=height,
        obstacles=list(obstacles),
        chokePoints=list(choke_points),
        pickupPoints=list(pickup_points),
        dropPoints=list(drop_points),
        blockedCells=[],          # mutable at runtime by simulation/scenarios
    )
