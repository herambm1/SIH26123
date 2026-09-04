"""
collision_engine/resolution.py — ConflictResolver.
Owner: Member 3

Applies deterministic priority rules to resolve a detected conflict.

Import contracts from shared.python.models — do NOT redefine them here.
"""

from shared.python.models import Conflict, RobotState


class ConflictResolver:
    """Applies deterministic priority rules to choose a conflict resolution action.

    Priority order (highest wins):
        1. Emergency/high-priority task
        2. Higher Task.priority
        3. Robot already inside the contested cell/critical section
        4. Lower estimated rerouting cost
        5. robotId as final tie-breaker (lexicographic)

    Returns one of: CONTINUE | WAIT | YIELD | REROUTE | REASSIGN_TASK

    Implementation: Member 3's responsibility.
    """

    def resolve(
        self,
        conflict: Conflict,
        own_state: RobotState,
        peer_intents: list,    # list[dict]
    ) -> str:
        """Return one of CONTINUE | WAIT | YIELD | REROUTE | REASSIGN_TASK.
        """
        # Determine peer robot ID from the conflict
        peer_id = next((rid for rid in conflict.robotIds if rid != own_state.robotId), None)
        peer = next((p for p in peer_intents if p.get("robotId") == peer_id), {}) if peer_id else {}

        own_wins = self._evaluate_priority(conflict, own_state, peer, peer_id)

        if own_wins:
            action = "CONTINUE"
        else:
            action = self._select_yielding_action(conflict, own_state, peer)

        conflict.resolutionAction = action
        return action

    def _evaluate_priority(
        self, conflict: Conflict, own_state: RobotState, peer: dict, peer_id: str | None
    ) -> bool:
        """Apply the 5 deterministic priority rules in strict order.
        Returns True if own robot wins priority, False if peer wins.
        """
        # 1. Emergency/high-priority task (Task.priority == 5)
        own_priority = self._get_task_priority(own_state)
        peer_priority = peer.get("priority", 1)
        own_emergency = (own_priority == 5)
        peer_emergency = (peer_priority == 5)

        if own_emergency != peer_emergency:
            return own_emergency

        # 2. Higher Task.priority (1..5)
        if own_priority != peer_priority:
            return own_priority > peer_priority

        # 3. Robot already inside the contested cell/critical section
        target_cell = conflict.predictedCell
        own_in_cell = (
            own_state.position.x == target_cell.x and own_state.position.y == target_cell.y
        )
        peer_pos = peer.get("position")
        peer_in_cell = False
        if peer_pos:
            px = getattr(peer_pos, "x", peer_pos.get("x") if isinstance(peer_pos, dict) else None)
            py = getattr(peer_pos, "y", peer_pos.get("y") if isinstance(peer_pos, dict) else None)
            peer_in_cell = (px == target_cell.x and py == target_cell.y)

        if own_in_cell != peer_in_cell:
            return own_in_cell

        # 4. Lower estimated rerouting cost (evaluated when explicit costs are available)
        own_cost = getattr(own_state, "reroutingCost", getattr(own_state, "rerouteCost", None))
        peer_cost = peer.get("reroutingCost", peer.get("rerouteCost"))
        if own_cost is not None and peer_cost is not None and own_cost != peer_cost:
            return own_cost < peer_cost

        # 5. robotId as final tie-breaker (lexicographic: lower string ID wins)
        if peer_id:
            return own_state.robotId < peer_id
        return True

    def _get_task_priority(self, state: RobotState) -> int:
        """Extract task priority (1..5) from state if available."""
        if hasattr(state, "task_priority") and state.task_priority is not None:
            return int(state.task_priority)
        if hasattr(state, "priority") and state.priority is not None:
            return int(state.priority)
        return 1

    def _select_yielding_action(
        self, conflict: Conflict, own_state: RobotState, peer: dict
    ) -> str:
        """Choose appropriate yielding action for the lower-priority robot."""
        # Robot in OFFLINE status triggers task reassignment
        if own_state.status == "OFFLINE":
            return "REASSIGN_TASK"

        # Narrow aisle head-on conflict -> YIELD
        if conflict.type == "NARROW_AISLE_HEADON":
            return "YIELD"

        # Default for SAME_CELL / CROSSING conflicts -> WAIT
        return "WAIT"
