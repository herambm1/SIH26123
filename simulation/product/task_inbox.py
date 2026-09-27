"""simulation/product/task_inbox.py — thread-safe inboxes for Product-mode
sessions.

The FastAPI routes in simulation/runner.py (POST /control/task,
POST /control/inject) run on FastAPI's event loop thread; the session's own
tick loop runs on a separate background thread (ProductSession._run). This
is the single, small, lock-guarded hand-off point between them — routes only
ever append, the tick loop only ever drains, so contention is a single short
lock per call, never held across a whole tick.
"""

from __future__ import annotations

import threading


class TaskInbox:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._assignments: list[dict] = []
        self._injections: list[dict] = []
        self._releases: list[dict] = []
        self._recoveries: list[dict] = []

    # ── Producers (called from the FastAPI route handlers) ─────────────────

    def submit_assignment(self, body: dict) -> None:
        """Queue a Java-originated task assignment (POST /control/task).

        Shape matches SimulationClient.toPythonAssignment on the Java side
        (see backend/.../service/SimulationClient.java) and the existing
        task_assignments list SimulationRunner._apply_task_assignment
        already consumes at scenario run-start: {robotId, taskId,
        pickupPosition:{x,y}, dropPosition:{x,y}, priority}. Applied at the
        next tick boundary by ProductSession — never mid-tick.
        """
        with self._lock:
            self._assignments.append(dict(body))

    def submit_release(self, body: dict) -> None:
        """Queue a Java-originated robot RELEASE (POST /control/release).

        Sent by ProductSessionService when it abandons a task whose robot has
        made no progress for a long time (see that class's STALL_ABANDON_TICKS):
        shape {robotId, taskId}. Applied at the next tick boundary by
        ProductSession._apply_release, which re-checks that the robot is still
        on that task before touching it.
        """
        with self._lock:
            self._releases.append(dict(body))

    def submit_recover(self, body: dict) -> None:
        """Queue a manual recovery of a broken-down robot (POST /control/recover); shape {robotId}. Applied at the next
        tick boundary by ProductSession._apply_recover, which re-checks the robot really is broken down."""
        with self._lock:
            self._recoveries.append(dict(body))

    def submit_injection(self, body: dict) -> dict:
        """Queue a world-fault injection request (POST /control/inject).

        Shape: {kind: "AISLE_BLOCK"|"ROBOT_OFFLINE"|"COMM_DELAY", cell?:
        {x,y}, robotId?: str}. Guard checks (cooldown, feasibility, etc.)
        happen when the tick loop actually applies it — not here — so the
        HTTP response only confirms the request was queued, never that it
        was accepted; the real accept/reject decision (and, if rejected,
        why) is reported back as a SYSTEM event on the live feed, which is
        what the frontend must show, not this HTTP response.
        """
        with self._lock:
            self._injections.append(dict(body))
        return {"queued": True}

    # ── Consumer (called once per tick from ProductSession._run) ───────────

    def drain_assignments(self) -> list[dict]:
        with self._lock:
            items, self._assignments = self._assignments, []
        return items

    def drain_releases(self) -> list[dict]:
        with self._lock:
            items, self._releases = self._releases, []
        return items

    def drain_recoveries(self) -> list[dict]:
        with self._lock:
            items, self._recoveries = self._recoveries, []
        return items

    def drain_injections(self) -> list[dict]:
        with self._lock:
            items, self._injections = self._injections, []
        return items
