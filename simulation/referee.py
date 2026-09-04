"""
simulation/referee.py — Independent collision referee.
Owner: Member 3

Ground-truth bounding-box/cell-overlap checker.

CRITICAL DESIGN CONSTRAINT: This referee must NEVER import from or call into
collision_engine/detection.py. The two must remain fully independent so that
"zero collisions" is verified externally, not assumed by construction.

Import contracts from shared.python.models — do NOT redefine them here.
"""

from shared.python.models import Position


class CollisionReferee:
    """Independent ground-truth collision checker.

    Reads actual robot positions directly — does NOT use ConflictDetector.
    Called every tick by simulation/runner.py; results tallied into
    PerformanceMetric.collisionCount.

    Implementation: Member 3's responsibility.
    """

    def __init__(self):
        self._prev_positions: dict[str, tuple[int, int]] = {}

    def check(self, all_positions: dict) -> list:   # dict[str, Position] -> list[tuple[str, str]]
        """Check for collisions in the current tick's actual robot positions.

        all_positions: {robotId: Position} — ground-truth positions this tick.

        Returns a list of colliding robot ID pairs, e.g. [("R1", "R2")].
        Returns an empty list if no collisions occurred.
        """
        collisions: set[tuple[str, str]] = set()

        # Extract coordinate tuples (x, y) for all active positions
        curr_coords: dict[str, tuple[int, int]] = {}
        for rid, pos in all_positions.items():
            if pos is not None:
                if isinstance(pos, Position):
                    curr_coords[rid] = (pos.x, pos.y)
                elif isinstance(pos, dict):
                    curr_coords[rid] = (pos.get("x", 0), pos.get("y", 0))
                elif isinstance(pos, (tuple, list)) and len(pos) >= 2:
                    curr_coords[rid] = (pos[0], pos[1])

        robot_ids = sorted(curr_coords.keys())

        # 1. Check for same-cell vertex collision
        for i in range(len(robot_ids)):
            for j in range(i + 1, len(robot_ids)):
                r1, r2 = robot_ids[i], robot_ids[j]
                if curr_coords[r1] == curr_coords[r2]:
                    collisions.add((r1, r2))

        # 2. Check for edge-swap collisions between previous tick and current tick
        for i in range(len(robot_ids)):
            for j in range(i + 1, len(robot_ids)):
                r1, r2 = robot_ids[i], robot_ids[j]
                if r1 in self._prev_positions and r2 in self._prev_positions:
                    prev1 = self._prev_positions[r1]
                    prev2 = self._prev_positions[r2]
                    curr1 = curr_coords[r1]
                    curr2 = curr_coords[r2]
                    if prev1 == curr2 and curr1 == prev2 and prev1 != curr1:
                        collisions.add((r1, r2))

        # Update previous tick positions
        self._prev_positions = curr_coords
        return sorted(list(collisions))
