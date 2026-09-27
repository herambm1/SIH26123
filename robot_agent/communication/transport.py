"""
robot_agent/communication/transport.py — Transport interface and InProcessBus implementation.
Owner: Member 2

Provides:
  Transport        — abstract interface (send / broadcast / receive)
  MessageFaultConfig — fault injection config (drop_rate, delay_ticks)
  InProcessBus     — default in-process pub-sub bus with fault injection
  UnknownRobotError — raised on unregistered robot IDs

Thread-safety assumption (documented, per §8.1):
  InProcessBus is designed for a SINGLE-THREADED tick loop (the MVP simulation
  model). The queues and delay buffers are plain Python dicts/lists — no locking.
  If the simulation is ever made concurrent (agents in threads), replace the
  internal collections with thread-safe equivalents (e.g. queue.Queue) without
  changing the public API.

Import contracts from shared.python.models — do NOT redefine them here.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections import deque
from typing import Optional


# ── Custom exceptions ────────────────────────────────────────────────────────

class UnknownRobotError(Exception):
    """Raised when send()/broadcast() is called with an unregistered robot ID.

    Message includes both the offending robot ID and the set of valid IDs so
    callers can diagnose the problem quickly.
    """


# ── Abstract interface ────────────────────────────────────────────────────────

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
        Raises UnknownRobotError if msg['robotId'] is not a registered robot ID.
        """

    @abstractmethod
    def receive(self, robot_id: str) -> list:   # list[dict]
        """Return and clear all pending messages for robot_id this tick.

        Returns an empty list if no messages are pending — this is a normal,
        expected state, not an error.
        """


# ── Fault injection config ────────────────────────────────────────────────────

class MessageFaultConfig:
    """Fault injection configuration for the message bus.

    Powers the deadlock-recovery and resilience demo scenarios.

    Attributes:
        drop_rate   : float in [0.0, 1.0].  0.0 = normal; 1.0 = every message dropped.
        delay_ticks : non-negative int. 0 = immediate; N = message released after N
                      calls to InProcessBus.advance_tick().

    Validation is strict — invalid values raise ValueError immediately so bugs
    are caught at configuration time, not silently at message-delivery time.
    """

    def __init__(self, drop_rate: float = 0.0, delay_ticks: int = 0):
        """
        Args:
            drop_rate:   Probability [0.0, 1.0] that any given message is dropped.
            delay_ticks: Number of simulation ticks to hold a message before delivery.
                         Uses discrete tick counting — no real sleep or time.time().

        Raises:
            ValueError: if drop_rate is outside [0.0, 1.0] or delay_ticks < 0.
        """
        if not (0.0 <= drop_rate <= 1.0):
            raise ValueError(
                f"drop_rate must be in [0.0, 1.0], got {drop_rate!r}"
            )
        if not isinstance(delay_ticks, int) or delay_ticks < 0:
            raise ValueError(
                f"delay_ticks must be a non-negative integer, got {delay_ticks!r}"
            )
        self.drop_rate: float = drop_rate
        self.delay_ticks: int = delay_ticks

    def __repr__(self) -> str:
        return (
            f"MessageFaultConfig(drop_rate={self.drop_rate}, "
            f"delay_ticks={self.delay_ticks})"
        )


# ── In-process bus ────────────────────────────────────────────────────────────

class InProcessBus(Transport):
    """Default in-process publish/subscribe bus.

    Deterministic and immune to venue Wi-Fi issues while still enforcing
    that agents only see each other through explicit messages — no shared
    global state.

    Thread-safety: single-threaded MVP (see module docstring).

    Internal structures:
        _queues         : dict[robot_id -> deque[dict]]   — ready-to-receive messages
        _delay_buffers  : dict[robot_id -> deque[(ticks_remaining, msg)]]
                          — messages held until their delay expires
    """

    def __init__(
        self,
        robot_ids: list,          # list[str]
        fault_config: Optional[MessageFaultConfig] = None,
        *,
        rng: Optional[random.Random] = None,
    ):
        """
        Args:
            robot_ids:    All robot IDs participating in this simulation run.
                          Must be a non-empty list of unique strings.
            fault_config: Optional fault injection; if None, no faults are applied.
            rng:          Optional seeded Random instance for deterministic tests.
                          If None, a fresh random.Random() is used (non-deterministic).

        Raises:
            ValueError: if robot_ids is empty or contains duplicates.
        """
        if not robot_ids:
            raise ValueError("robot_ids must not be empty")
        unique_ids = list(dict.fromkeys(robot_ids))   # preserves order, removes dups
        if len(unique_ids) != len(robot_ids):
            raise ValueError(
                f"robot_ids contains duplicates: {robot_ids!r}"
            )

        self._robot_ids: frozenset[str] = frozenset(unique_ids)
        self._fault: Optional[MessageFaultConfig] = fault_config
        self._rng: random.Random = rng if rng is not None else random.Random()

        # Per-robot ready queues: messages available to receive() this tick
        self._queues: dict[str, deque] = {rid: deque() for rid in unique_ids}

        # Per-robot delay buffers: list of (ticks_remaining, msg) tuples
        # ticks_remaining counts down; reaches 0 → message promoted to _queues
        self._delay_buffers: dict[str, list] = {rid: [] for rid in unique_ids}

    # ── Private helpers ───────────────────────────────────────────────────────

    def _assert_registered(self, robot_id: str, *, context: str) -> None:
        """Raise UnknownRobotError with a helpful message if robot_id unknown."""
        if robot_id not in self._robot_ids:
            raise UnknownRobotError(
                f"{context}: robot_id {robot_id!r} is not registered on this bus. "
                f"Registered IDs: {sorted(self._robot_ids)}"
            )

    def _should_drop(self) -> bool:
        """Return True if the current message should be dropped per fault config."""
        if self._fault is None or self._fault.drop_rate == 0.0:
            return False
        if self._fault.drop_rate >= 1.0:
            return True
        return self._rng.random() < self._fault.drop_rate

    def _enqueue(self, robot_id: str, msg: dict) -> None:
        """Enqueue a single message for robot_id, respecting fault config."""
        if self._should_drop():
            return  # message silently dropped (fault injection)

        delay = self._fault.delay_ticks if self._fault is not None else 0

        if delay <= 0:
            # Deliver immediately into the ready queue
            self._queues[robot_id].append(msg)
        else:
            # Hold in the delay buffer; ticks_remaining starts at delay
            self._delay_buffers[robot_id].append([delay, msg])

    # ── Public API ────────────────────────────────────────────────────────────

    def send(self, to: str, msg: dict) -> None:
        """Send a targeted message to a single robot.

        Raises UnknownRobotError if `to` is not in robot_ids.
        """
        self._assert_registered(to, context="send()")
        self._enqueue(to, msg)

    def broadcast(self, msg: dict) -> None:
        """Broadcast to all robots except the sender (identified by msg['robotId']).

        Raises UnknownRobotError if msg['robotId'] is not registered.
        The sender robot does NOT receive its own broadcast.
        """
        sender_id = msg.get("robotId")
        if sender_id is not None:
            self._assert_registered(sender_id, context="broadcast()")

        for rid in self._robot_ids:
            if rid == sender_id:
                continue    # sender excluded
            self._enqueue(rid, msg)

    def receive(self, robot_id: str) -> list:   # list[dict]
        """Return and clear all pending (ready) messages for robot_id.

        Returns an empty list if no messages are pending — this is a normal,
        expected state (per §13), not an error.
        Raises UnknownRobotError if robot_id is not a registered robot ID.
        """
        self._assert_registered(robot_id, context="receive()")
        q = self._queues[robot_id]
        messages = list(q)
        q.clear()
        return messages

    def advance_tick(self) -> None:
        """Call once per simulation tick to release delayed messages.

        Decrements the ticks_remaining counter on every delayed message.
        When ticks_remaining reaches 0, the message is promoted to the
        robot's ready queue so it becomes visible in the NEXT receive() call.

        Timing semantics (deterministic):
            - delay_ticks=1: message becomes visible after 1 advance_tick() call.
            - delay_ticks=N: message becomes visible after N advance_tick() calls.
        """
        for rid, buffer in self._delay_buffers.items():
            still_delayed = []
            for entry in buffer:
                ticks_remaining, msg = entry
                ticks_remaining -= 1
                if ticks_remaining <= 0:
                    self._queues[rid].append(msg)   # now ready
                else:
                    still_delayed.append([ticks_remaining, msg])
            self._delay_buffers[rid] = still_delayed
