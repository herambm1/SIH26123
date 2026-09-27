"""simulation/product/envelope.py — event tagging + wire-shape helpers for
Product-mode sessions.

Deliberately payload-only: SimulationEvent (shared/python/models.py) already
carries a free-form `payload: dict`, so a session id and an origin tag ride
inside it rather than requiring any change to the frozen SimulationEvent
contract. No Tier A change.

origin values (all real, never fabricated):
  ROBOT_DECISION         — a RobotAgent/ConflictResolver outcome (NEGOTIATION)
  PRODUCT_INJECTED_FAULT — a world fault this driver (auto or manual) applied
  JAVA_TASK              — a task assignment that arrived via POST /control/task
  SYSTEM                 — an engine-observed fact (task completion, stall,
                            a fault that was SKIPPED and why)
"""

from __future__ import annotations

from shared.python.models import SimulationEvent

ORIGIN_ROBOT_DECISION = "ROBOT_DECISION"
ORIGIN_PRODUCT_INJECTED_FAULT = "PRODUCT_INJECTED_FAULT"
ORIGIN_JAVA_TASK = "JAVA_TASK"
ORIGIN_SYSTEM = "SYSTEM"


def tagged_event(event_id: str, event_type: str, tick: int, payload: dict, *, session_id: str, origin: str) -> SimulationEvent:
    """Build a SimulationEvent with sessionId/origin folded into payload, and
    the eventId ALWAYS prefixed with session_id.

    The prefix matters beyond convenience: simulation/runner.py's scenario
    path pushes events to the same Java `events` table (EventEntity, PK =
    eventId) using the exact same naming convention this package's event
    ids were built with (e.g. "neg_{tick}_{rid}_{action}",
    "coll_{tick}_{r1}_{r2}") — found by reading TaskAllocationService/
    EventEntity directly during Phase 2 design. Without this prefix, a live
    scenario run and a product session could silently overwrite each
    other's rows on save() (JPA upserts by primary key). The session_id
    already embeds a unix timestamp + random suffix (see
    ProductSession.__init__), so this also makes two different product
    sessions' events collision-free with each other.

    payload is copied, never mutated in place — the caller's dict (which
    may be reused/logged elsewhere) is left untouched.
    """
    full_payload = dict(payload or {})
    full_payload["sessionId"] = session_id
    full_payload["origin"] = origin
    return SimulationEvent(eventId=f"{session_id}_{event_id}", type=event_type, tick=tick, payload=full_payload)


def event_to_wire(e: SimulationEvent) -> dict:
    """Same shape simulation/runner.py already sends to POST /api/events —
    no contract change, just reused verbatim for the product push path."""
    return {"eventId": e.eventId, "type": e.type, "tick": e.tick, "payload": e.payload}


def state_to_wire(state) -> dict:
    """Identical shape to SimulationRunner._state_to_dict — duplicated here
    (not imported) only because that method is a bound instance method on
    SimulationRunner, not a free function; the shape itself is copied
    verbatim, not reinterpreted."""
    return {
        "robotId": state.robotId,
        "position": {"x": state.position.x, "y": state.position.y, "tick": state.position.tick},
        "velocity": state.velocity,
        "battery": state.battery,
        "currentTaskId": state.currentTaskId,
        "destination": (
            {"x": state.destination.x, "y": state.destination.y} if state.destination else None
        ),
        "currentPath": [{"x": p.x, "y": p.y, "tick": p.tick} for p in state.currentPath],
        "status": state.status,
        "timestamp": state.timestamp,
    }
