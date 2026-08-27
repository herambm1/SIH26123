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

    def check(self, all_positions: dict) -> list:   # dict[str, Position] -> list[tuple[str, str]]
        """Check for collisions in the current tick's actual robot positions.

        all_positions: {robotId: Position} — ground-truth positions this tick.

        Returns a list of colliding robot ID pairs, e.g. [("R1", "R2")].
        Returns an empty list if no collisions occurred.

        Implementation: Member 3's responsibility.
        """
        raise NotImplementedError
