"""
collision_engine/detection.py — ConflictDetector.
Owner: Member 3

Detects same-cell, crossing, and narrow-aisle head-on conflicts from broadcast
peer intents. Works from what robots tell each other (not ground truth).

Import contracts from shared.python.models — do NOT redefine them here.
"""

from shared.python.models import Conflict, RobotPath, RobotState


class ConflictDetector:
    """Detects conflicts between a robot's planned path and peers' broadcast intents.

    Conflict types detected (per docs/00_SHARED_CONTRACTS.md):
        SAME_CELL         — two robots planning to occupy the same cell at the same tick
        CROSSING          — two robots' paths cross each other within the window
        NARROW_AISLE_HEADON — two robots approaching each other in a single-file aisle

    Implementation: Member 3's responsibility.
    """

    def detect(
        self,
        own_state: RobotState,
        own_path: RobotPath,
        peer_intents: list,    # list[dict] — dicts from build_intent_message()
    ) -> Conflict | None:
        """Compare own path against peer intents and return the highest-priority conflict,
        or None if no conflict is detected.

        Implementation: Member 3's responsibility.
        """
        raise NotImplementedError
