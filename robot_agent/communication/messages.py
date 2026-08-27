"""
robot_agent/communication/messages.py — Intent message builder.
Owner: Member 2

Builds a JSON-serializable intent dict from a RobotState.
The intent message is NOT a new named contract type — it is a subset of RobotState,
derived to avoid duplicating contract definitions.

Import contracts from shared.python.models — do NOT redefine them here.
"""

from shared.python.models import RobotState


def build_intent_message(state: RobotState) -> dict:
    """Extract an intent message from a RobotState.

    Returns a JSON-serializable dict with keys:
        robotId, position, destination, plannedPath, currentTask,
        priority (from the current task), battery, status, timestamp.

    `plannedPath` carries RobotPath.waypoints (space-time positions) so that
    receivers can perform windowed-replanning-style conflict prediction.

    Implementation: Member 2's responsibility.
    """
    raise NotImplementedError
