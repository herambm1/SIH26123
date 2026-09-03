"""
edge/fault_injection.py — Sensor fault injection configuration.
Owner: Member 5

This is the real deliverable of the Edge role — not decoration.
Powers the deadlock-recovery and task-reassignment demo scenarios.

Import contracts from shared.python.models — do NOT redefine them here.
"""


class SensorFaultConfig:
    """Configures noise, dropout, and offline fault modes for a sensor source.

    Used by SimulationSensorSource and (indirectly) HeartbeatMonitor to produce
    realistic faulty readings that drive the demo scenarios.

    noise_std:          Gaussian standard deviation for position jitter (cells).
    dropout_rate:       Probability [0.0, 1.0] that a reading is simply missing this tick.
    offline_after_tick: Optional tick number after which the robot goes fully dark.
                        Used to trigger task reassignment in the demo.

    Implementation: Member 5's responsibility.
    """

    def __init__(
        self,
        noise_std: float = 0.0,
        dropout_rate: float = 0.0,
        offline_after_tick: int | None = None,
    ):
        """
        Implementation: Member 5's responsibility.
        """
        if noise_std < 0:
            raise ValueError("noise_std must be non-negative")
        if not 0.0 <= dropout_rate <= 1.0:
            raise ValueError("dropout_rate must be between 0.0 and 1.0")
        if offline_after_tick is not None and offline_after_tick < 0:
            raise ValueError("offline_after_tick must be non-negative or None")
        self.noise_std = float(noise_std)
        self.dropout_rate = float(dropout_rate)
        self.offline_after_tick = offline_after_tick
