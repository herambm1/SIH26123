"""Unit tests for ConflictResolver.
Owner: Member 3
"""

import unittest
from collision_engine.resolution import ConflictResolver
from shared.python.models import Conflict, Position, RobotState


class TestConflictResolver(unittest.TestCase):
    def setUp(self):
        self.resolver = ConflictResolver()

    def _create_state(
        self,
        robot_id: str,
        x: int,
        y: int,
        priority: int = 1,
        status: str = "MOVING",
        rerouting_cost: int | None = None,
    ) -> RobotState:
        state = RobotState(
            robotId=robot_id,
            position=Position(x=x, y=y),
            velocity=1.0,
            battery=100.0,
            currentTaskId="task1",
            destination=Position(x=10, y=10),
            currentPath=[Position(x=x + 1, y=y, tick=1)],
            status=status,
            timestamp=1,
        )
        state.task_priority = priority  # type: ignore
        if rerouting_cost is not None:
            state.reroutingCost = rerouting_cost  # type: ignore
        return state

    def test_rule1_emergency_task_wins(self):
        # Priority 5 is emergency/high-priority task
        conflict = Conflict(
            conflictId="c1",
            robotIds=["R1", "R2"],
            type="SAME_CELL",
            predictedCell=Position(x=3, y=3),
            predictedTick=3,
            severity="HIGH",
        )
        state_r1 = self._create_state("R1", 0, 0, priority=5)
        peer_intents = [{"robotId": "R2", "priority": 2, "plannedPath": [Position(x=3, y=3)]}]

        action = self.resolver.resolve(conflict, state_r1, peer_intents)
        self.assertEqual(action, "CONTINUE")

        # R2 perspective (lower priority -> WAIT)
        state_r2 = self._create_state("R2", 5, 5, priority=2)
        peer_intents_r2 = [{"robotId": "R1", "priority": 5, "plannedPath": []}]
        action_r2 = self.resolver.resolve(conflict, state_r2, peer_intents_r2)
        self.assertEqual(action_r2, "WAIT")

    def test_rule2_higher_task_priority_wins(self):
        conflict = Conflict(
            conflictId="c2",
            robotIds=["R1", "R2"],
            type="SAME_CELL",
            predictedCell=Position(x=2, y=2),
            predictedTick=2,
            severity="HIGH",
        )
        state_r1 = self._create_state("R1", 0, 0, priority=4)
        peer_intents = [{"robotId": "R2", "priority": 2, "plannedPath": [Position(x=2, y=2)]}]

        action = self.resolver.resolve(conflict, state_r1, peer_intents)
        self.assertEqual(action, "CONTINUE")

    def test_rule3_already_inside_contested_cell(self):
        conflict = Conflict(
            conflictId="c3",
            robotIds=["R1", "R2"],
            type="SAME_CELL",
            predictedCell=Position(x=2, y=2),
            predictedTick=2,
            severity="HIGH",
        )
        # Both priority 2, but R1 is already inside (2, 2)
        state_r1 = self._create_state("R1", 2, 2, priority=2)
        peer_intents = [
            {"robotId": "R2", "priority": 2, "position": Position(x=1, y=2), "plannedPath": []}
        ]

        action = self.resolver.resolve(conflict, state_r1, peer_intents)
        self.assertEqual(action, "CONTINUE")

    def test_rule4_lower_reroute_cost(self):
        conflict = Conflict(
            conflictId="c4",
            robotIds=["R1", "R2"],
            type="SAME_CELL",
            predictedCell=Position(x=5, y=5),
            predictedTick=3,
            severity="HIGH",
        )
        # Both priority 2, neither in cell, but explicit reroute cost is lower for R1 (2 vs 8)
        state_r1 = self._create_state("R1", 0, 0, priority=2, rerouting_cost=2)
        peer_intents = [
            {
                "robotId": "R2",
                "priority": 2,
                "position": Position(x=0, y=1),
                "reroutingCost": 8,
                "plannedPath": [],
            }
        ]
        action = self.resolver.resolve(conflict, state_r1, peer_intents)
        self.assertEqual(action, "CONTINUE")

    def test_rule5_tie_breaker_robot_id(self):
        conflict = Conflict(
            conflictId="c5",
            robotIds=["R1", "R2"],
            type="SAME_CELL",
            predictedCell=Position(x=3, y=3),
            predictedTick=3,
            severity="HIGH",
        )
        # Identical priorities: lexicographic "R1" < "R2"
        state_r1 = self._create_state("R1", 0, 0, priority=2)
        peer_intents_for_r1 = [{"robotId": "R2", "priority": 2, "plannedPath": []}]
        self.assertEqual(self.resolver.resolve(conflict, state_r1, peer_intents_for_r1), "CONTINUE")

        state_r2 = self._create_state("R2", 0, 0, priority=2)
        peer_intents_for_r2 = [{"robotId": "R1", "priority": 2, "plannedPath": []}]
        self.assertEqual(self.resolver.resolve(conflict, state_r2, peer_intents_for_r2), "WAIT")

    def test_narrow_aisle_headon_yield(self):
        conflict = Conflict(
            conflictId="c6",
            robotIds=["R1", "R2"],
            type="NARROW_AISLE_HEADON",
            predictedCell=Position(x=4, y=1),
            predictedTick=2,
            severity="HIGH",
        )
        # R2 has higher priority -> R1 must YIELD
        state_r1 = self._create_state("R1", 1, 1, priority=1)
        peer_intents = [{"robotId": "R2", "priority": 3, "plannedPath": [Position(x=4, y=1)]}]
        action = self.resolver.resolve(conflict, state_r1, peer_intents)
        self.assertEqual(action, "YIELD")

    def test_offline_reassign_task(self):
        conflict = Conflict(
            conflictId="c7",
            robotIds=["R1", "R2"],
            type="SAME_CELL",
            predictedCell=Position(x=2, y=2),
            predictedTick=2,
            severity="HIGH",
        )
        state_r1 = self._create_state("R1", 0, 0, priority=1, status="OFFLINE")
        peer_intents = [{"robotId": "R2", "priority": 3, "plannedPath": []}]
        action = self.resolver.resolve(conflict, state_r1, peer_intents)
        self.assertEqual(action, "REASSIGN_TASK")


if __name__ == "__main__":
    unittest.main()
