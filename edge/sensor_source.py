"""
edge/sensor_source.py — SensorSource interface and SimulationSensorSource.
Owner: Member 5

Import contracts from shared.python.models — do NOT redefine them here.
"""

from abc import ABC, abstractmethod
import random
import time
from typing import Callable

from edge.fault_injection import SensorFaultConfig
from edge.heartbeat import HeartbeatMonitor
from shared.python.models import Position, Telemetry


class SensorSource(ABC):
    """Abstract sensor/telemetry source interface.

    Implementations: SimulationSensorSource (default, software-only),
    and optionally HardwareSensorSource in edge/hardware/ for the bonus segment.
    HardwareSensorSource must NEVER be imported by the default simulation path.
    """

    @abstractmethod
    def read(self, robot_id: str, current_tick: int) -> "Telemetry | None":
        """Read a telemetry snapshot for the given robot at the current tick.

        Returns None (or a Telemetry with sensorHealth=OFFLINE) if dropout is
        configured or the sensor is unavailable — this is expected modeled behavior,
        not an error.
        """


class SimulationSensorSource(SensorSource):
    """Software-only sensor source that produces synthetic telemetry.

    Derives readings from the ground-truth simulation state, then applies
    configured noise/dropout on top via SensorFaultConfig.

    Implementation: Member 5's responsibility.
    """

    def __init__(self, ground_truth_provider: Callable[[str], Position], fault_config: SensorFaultConfig | None = None, *, miss_threshold: int = 3, rng: random.Random | None = None):
        """
        ground_truth_provider: a callable (robot_id: str) -> Position giving the
            'real' simulated position this tick, before noise is applied.
        fault_config: optional fault injection profile; if None, no faults are applied.

        Implementation: Member 5's responsibility.
        """
        self.ground_truth_provider = ground_truth_provider
        self.fault_config = fault_config or SensorFaultConfig()
        self.heartbeat_monitor = HeartbeatMonitor(miss_threshold)
        self._rng = rng or random.Random()

    def read(self, robot_id: str, current_tick: int) -> "Telemetry | None":
        """Produce a Telemetry reading for the given robot, applying any configured faults.

        Implementation: Member 5's responsibility.
        """
        position = self.ground_truth_provider(robot_id)
        if not isinstance(position, Position):
            raise TypeError("ground_truth_provider must return shared.python.models.Position")
        if self.fault_config.offline_after_tick is not None and current_tick >= self.fault_config.offline_after_tick:
            return self._offline_telemetry(robot_id, position, current_tick)
        if self._rng.random() < self.fault_config.dropout_rate:
            self.heartbeat_monitor.record(robot_id, None)
            if self.heartbeat_monitor.is_offline(robot_id):
                return self._offline_telemetry(robot_id, position, current_tick, already_recorded=True)
            return None
        sensor_health = "DEGRADED" if self.fault_config.noise_std > 0 else "OK"
        telemetry = Telemetry(robotId=robot_id, position=self._noisy_position(position), battery=100.0, obstacleDetected=False, sensorHealth=sensor_health, tick=current_tick)
        self.heartbeat_monitor.record(robot_id, telemetry)
        if self.heartbeat_monitor.is_offline(robot_id):
            telemetry.sensorHealth = "OFFLINE"
        return telemetry

    def _noisy_position(self, position: Position) -> Position:
        """Apply jitter while preserving the integer grid-cell contract."""
        if self.fault_config.noise_std == 0:
            return Position(position.x, position.y)
        return Position(round(position.x + self._rng.gauss(0.0, self.fault_config.noise_std)), round(position.y + self._rng.gauss(0.0, self.fault_config.noise_std)))

    def _offline_telemetry(self, robot_id: str, position: Position, current_tick: int, *, already_recorded: bool = False) -> Telemetry:
        """Emit the contract's explicit OFFLINE signal without raising an error."""
        telemetry = Telemetry(robotId=robot_id, position=Position(position.x, position.y), battery=100.0, obstacleDetected=False, sensorHealth="OFFLINE", tick=current_tick)
        if not already_recorded:
            self.heartbeat_monitor.record(robot_id, telemetry)
        return telemetry


if __name__ == "__main__":
    source = SimulationSensorSource(lambda _robot_id: Position(4, 7))
    for tick in range(5):
        print(source.read("demo-robot", tick))
        time.sleep(1)
