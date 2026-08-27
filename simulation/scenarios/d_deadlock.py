"""Scenario D — Deadlock.

Multiple robots form a circular wait: each is waiting for the next to move,
and none can proceed. Tests the deadlock detection and forced-yield recovery.
Paired with MessageFaultConfig to simulate degraded communication.

Owner: Member 3. Implementation: Member 3's responsibility.
"""
