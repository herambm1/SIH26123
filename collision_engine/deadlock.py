"""
collision_engine/deadlock.py — DeadlockDetector.
Owner: Member 3

Simplified N-tick stall heuristic (not full wait-for-graph cycle detection).
Full cycle detection is an optional Phase 4+ enhancement.

Import contracts from shared.python.models — do NOT redefine them here.
"""


class DeadlockDetector:
    """Detects deadlock via a simplified stall heuristic.

    If a robot has made no progress for N ticks while waiting on a specific peer,
    it triggers a forced yield on the lower-priority robot. This covers the 2-robot
    and typical 3-robot deadlocks in the demo scenarios.

    Full wait-for-graph cycle detection is a Phase 4+ optional enhancement.

    Implementation: Member 3's responsibility.
    """

    def __init__(self, stall_threshold: int = 5):
        """
        stall_threshold: number of ticks without progress before deadlock is declared.
        Implementation: Member 3's responsibility.
        """
        raise NotImplementedError

    def check(
        self,
        robot_id: str,
        stall_ticks: int,
        waiting_on: str | None,
    ) -> bool:
        """Return True if this robot should be forced to yield due to suspected deadlock.

        robot_id: the robot being checked.
        stall_ticks: how many consecutive ticks this robot has made no progress.
        waiting_on: robot_id of the peer this robot is waiting on, or None.

        Implementation: Member 3's responsibility.
        """
        raise NotImplementedError
