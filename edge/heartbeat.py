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
        if miss_threshold < 1:
            raise ValueError("miss_threshold must be at least 1")
        self.miss_threshold = miss_threshold
        self._misses_by_robot: dict[str, int] = {}

    def record(self, robot_id: str, telemetry: "Telemetry | None") -> None:
        """Record one tick's reading for a robot.

        telemetry=None means a dropped/missing reading this tick — counts
        toward the miss threshold, as does an explicit sensorHealth=OFFLINE
        report. A sensorHealth=DEGRADED reading does NOT count as a miss: the
        robot IS still reporting in (a heartbeat was received), the reading is
        just noisy/imprecise — noise and dropout are independent fault modes
        (see edge/fault_injection.py), so a present-but-noisy reading resets
        the miss streak exactly like an OK reading rather than accumulating
        toward OFFLINE. (Fixed: previously DEGRADED was treated the same as a
        dropped reading, so any nonzero noise_std alone — with no dropout and
        no offline_after_tick — would eventually force a robot OFFLINE.)

        Implementation: Member 5's responsibility.
        """
        health = None if telemetry is None else telemetry.sensorHealth
        if health is None or health == "OFFLINE":
            self._misses_by_robot[robot_id] = self._misses_by_robot.get(robot_id, 0) + 1
        else:
            self._misses_by_robot[robot_id] = 0

    def is_offline(self, robot_id: str) -> bool:
        """Return True if robot_id has exceeded the miss threshold.

        Implementation: Member 5's responsibility.
        """
        return self._misses_by_robot.get(robot_id, 0) >= self.miss_threshold
