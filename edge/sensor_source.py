"""
edge/sensor_source.py — SensorSource interface and SimulationSensorSource.
Owner: Member 5

Import contracts from shared.python.models — do NOT redefine them here.
"""

from abc import ABC, abstractmethod

from shared.python.models import Telemetry


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

    def __init__(self, ground_truth_provider, fault_config: "SensorFaultConfig | None" = None):
        """
        ground_truth_provider: a callable (robot_id: str) -> Position giving the
            'real' simulated position this tick, before noise is applied.
        fault_config: optional fault injection profile; if None, no faults are applied.

        Implementation: Member 5's responsibility.
        """
        raise NotImplementedError

    def read(self, robot_id: str, current_tick: int) -> "Telemetry | None":
        """Produce a Telemetry reading for the given robot, applying any configured faults.

        Implementation: Member 5's responsibility.
        """
        raise NotImplementedError
