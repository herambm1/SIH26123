"""
edge/heartbeat.py — Heartbeat / health-check monitor.
Owner: Member 5

Tracks consecutive missed/degraded readings per robot and marks robots OFFLINE
after a configurable miss threshold. The OFFLINE signal propagates through
RobotAgent.tick() → RobotState.status → backend task reassignment trigger.

Import contracts from shared.python.models — do NOT redefine them here.
"""

from shared.python.models import Telemetry


class HeartbeatMonitor:
    """Tracks sensor heartbeats and declares robots OFFLINE after missed readings.

    Implementation: Member 5's responsibility.
    """

    def __init__(self, miss_threshold: int = 3):
        """
        miss_threshold: number of consecutive missed/degraded readings before
            is_offline() returns True.

        Implementation: Member 5's responsibility.
        """
        raise NotImplementedError

    def record(self, robot_id: str, telemetry: "Telemetry | None") -> None:
        """Record one tick's reading for a robot.

        telemetry=None means a dropped/missing reading this tick.
        A reading with sensorHealth=DEGRADED or sensorHealth=OFFLINE counts
        toward the miss threshold.

        Implementation: Member 5's responsibility.
        """
        raise NotImplementedError

    def is_offline(self, robot_id: str) -> bool:
        """Return True if robot_id has exceeded the miss threshold.

        Implementation: Member 5's responsibility.
        """
        raise NotImplementedError
