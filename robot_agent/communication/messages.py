"""
robot_agent/communication/messages.py — Intent message builder.
Owner: Member 2

Builds a JSON-serializable intent dict from a RobotState.
The intent message is NOT a new named contract type — it is a JSON-serializable
subset of RobotState, derived to avoid duplicating contract definitions.

Import contracts from shared.python.models — do NOT redefine them here.

Compatibility note (2026-09-04):
    RobotState (shared/python/models.py) does NOT carry a `priority` field.
    Priority belongs to Task (Task.priority). agent.py accesses task priority
    via the optional attribute `task_priority` (set dynamically on the state
    object) with a fallback of 1.  build_intent_message() mirrors this
    convention: it reads getattr(state, 'task_priority', 1) so the intent
    message always contains a valid `priority` value without crashing and
    without modifying the canonical RobotState dataclass.

    If a dedicated `priority` field is ever added to RobotState in a future
    team sync, replace the getattr fallback with a direct attribute access.
"""

from __future__ import annotations

from typing import Any, Optional

from shared.python.models import Position, RobotState


def _position_to_dict(pos: Optional[Position]) -> Optional[dict]:
    """Convert a Position dataclass to a JSON-serializable dict.

    Returns None if pos is None.
    The `tick` field is included (may be None) — receivers use it for
    space-time conflict prediction on planned-path waypoints.
    """
    if pos is None:
        return None
    return {"x": pos.x, "y": pos.y, "tick": pos.tick}


def _path_to_list(path: Any) -> list:
    """Convert a list of Position objects to a list of JSON-serializable dicts.

    Accepts an empty list, None, or a list[Position]. Returns [] for None/empty.
    Does NOT mutate the original list.
    """
    if not path:
        return []
    return [_position_to_dict(wp) for wp in path]


def build_intent_message(state: RobotState) -> dict:
    """Extract an intent message from a RobotState.

    Returns a JSON-serializable dict with exactly these keys:
        robotId      — str, from state.robotId
        position     — dict {x, y, tick} or null, from state.position
        destination  — dict {x, y, tick} or null, from state.destination
        plannedPath  — list[{x, y, tick}], from state.currentPath (remaining
                       path waypoints, each with .tick set for space-time
                       conflict prediction by the collision engine)
        currentTask  — str or null, from state.currentTaskId
        priority     — int, from state.task_priority if present, else 1
                       (see module-level compatibility note above)
        battery      — float (0–100), from state.battery
        status       — str, from state.status
        timestamp    — int (simulation tick), from state.timestamp

    Contract guarantees:
        - The original RobotState is NOT mutated.
        - The returned dict is fully JSON-serializable (all values are
          Python primitives: str, int, float, bool, None, dict, list).
        - Field names match the spec in docs/02_ROBOT_COMMUNICATION.md §8.2
          exactly, so downstream consumers (ConflictDetector, Planner) can
          read them without any field-name adaptation.

    Args:
        state: A RobotState instance produced by RobotAgent.tick().

    Returns:
        A plain dict (not a dataclass) ready for JSON serialisation.

    Raises:
        TypeError: if state is not a RobotState instance.
    """
    if not isinstance(state, RobotState):
        raise TypeError(
            f"build_intent_message() expects a RobotState, got {type(state).__name__!r}"
        )

    # priority: RobotState has no `priority` field — see module docstring.
    priority: int = int(getattr(state, "task_priority", 1))

    return {
        "robotId": state.robotId,
        "position": _position_to_dict(state.position),
        "destination": _position_to_dict(state.destination),
        # plannedPath = remaining waypoints from currentPath (space-time positions)
        "plannedPath": _path_to_list(state.currentPath),
        "currentTask": state.currentTaskId,
        "priority": priority,
        "battery": state.battery,
        "status": state.status,
        "timestamp": state.timestamp,
    }
