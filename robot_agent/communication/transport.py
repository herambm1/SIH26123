"""
robot_agent/communication/transport.py — Transport interface and InProcessBus implementation.
Owner: Member 2

Import contracts from shared.python.models — do NOT redefine them here.
"""

from abc import ABC, abstractmethod


class UnknownRobotError(Exception):
    """Raised when send()/broadcast() is called with an unregistered robot ID."""


class Transport(ABC):
    """Abstract transport interface.

    Implementations: InProcessBus (default, deterministic, in-process),
    and optionally UDPTransport / WebSocketTransport for hardware bonus.
    All callers depend on this interface — keep send/broadcast/receive stable.
    """

    @abstractmethod
    def send(self, to: str, msg: dict) -> None:
        """Send a message to a specific robot.

        Raises UnknownRobotError if `to` is not a registered robot ID.
        """

    @abstractmethod
    def broadcast(self, msg: dict) -> None:
        """Broadcast a message to all registered robots except the sender.

        The sender robot ID must be embedded in msg (as 'robotId') so the bus
        can exclude it from delivery.
        """

    @abstractmethod
    def receive(self, robot_id: str) -> list:   # list[dict]
        """Return and clear all pending messages for robot_id this tick.

        Returns an empty list if no messages are pending — this is a normal,
        expected state, not an error.
        """


class MessageFaultConfig:
    """Fault injection configuration for the message bus.

    Powers the deadlock-recovery and resilience demo scenarios.
    """

    def __init__(self, drop_rate: float = 0.0, delay_ticks: int = 0):
        """
        drop_rate: probability [0.0, 1.0] that any given message is silently dropped.
        delay_ticks: number of ticks a message is held before delivery.

        Implementation: Member 2's responsibility.
        """
        raise NotImplementedError


class InProcessBus(Transport):
    """Default in-process publish/subscribe bus.

    Deterministic and immune to venue Wi-Fi issues while still enforcing
    that agents only see each other through explicit messages — no shared
    global state.

    Thread safety: document your assumption clearly (single-threaded tick
    loop is fine for MVP — see docs/02_ROBOT_COMMUNICATION.md §8.1).
    """

    def __init__(self, robot_ids: list, fault_config: MessageFaultConfig | None = None):
        """
        robot_ids: all robot IDs participating in this simulation run.
        fault_config: optional fault injection; if None, no faults are injected.

        Implementation: Member 2's responsibility.
        """
        raise NotImplementedError

    def send(self, to: str, msg: dict) -> None:
        """Send a targeted message to a single robot.

        Raises UnknownRobotError if `to` is not in robot_ids.
        Implementation: Member 2's responsibility.
        """
        raise NotImplementedError

    def broadcast(self, msg: dict) -> None:
        """Broadcast to all robots except the sender (identified by msg['robotId']).

        Implementation: Member 2's responsibility.
        """
        raise NotImplementedError

    def receive(self, robot_id: str) -> list:   # list[dict]
        """Return and clear pending messages for robot_id.

        Implementation: Member 2's responsibility.
        """
        raise NotImplementedError

    def advance_tick(self) -> None:
        """Call once per simulation tick to release delayed messages.

        Implementation: Member 2's responsibility.
        """
        raise NotImplementedError
