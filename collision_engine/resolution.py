"""
collision_engine/resolution.py — ConflictResolver.
Owner: Member 3

Applies deterministic priority rules to resolve a detected conflict.

Import contracts from shared.python.models — do NOT redefine them here.
"""

from shared.python.models import Conflict, RobotState


class ConflictResolver:
    """Applies deterministic priority rules to choose a conflict resolution action.

    Priority order (highest wins):
        1. Emergency/high-priority task
        2. Higher Task.priority
        3. Robot already inside the contested cell/critical section
        4. Lower estimated rerouting cost
        5. robotId as final tie-breaker (lexicographic)

    Returns one of: CONTINUE | WAIT | YIELD | REROUTE | REASSIGN_TASK

    Implementation: Member 3's responsibility.
    """

    def resolve(
        self,
        conflict: Conflict,
        own_state: RobotState,
        peer_intents: list,    # list[dict]
    ) -> str:
        """Return one of CONTINUE | WAIT | YIELD | REROUTE | REASSIGN_TASK.

        Implementation: Member 3's responsibility.
        """
        raise NotImplementedError
