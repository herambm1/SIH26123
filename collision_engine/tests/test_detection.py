"""Unit tests for ConflictDetector.
Owner: Member 3
"""

import unittest
from collision_engine.detection import ConflictDetector
from shared.python.models import Position, RobotPath, RobotState


class TestConflictDetector(unittest.TestCase):
    def setUp(self):
        self.detector = ConflictDetector()

    def _create_state(self, robot_id: str, x: int, y: int, tick: int = 0) -> RobotState:
        return RobotState(
            robotId=robot_id,
            position=Position(x=x, y=y),
            velocity=1.0,
            battery=100.0,
            currentTaskId="task1",
            destination=Position(x=x + 5, y=y),
            currentPath=[],
            status="MOVING",
            timestamp=tick,
        )

    def test_no_conflict(self):
        own_state = self._create_state("R1", 0, 0, 0)
        own_path = RobotPath(
            robotId="R1",
            waypoints=[Position(x=1, y=0, tick=1), Position(x=2, y=0, tick=2)],
            generatedAtTick=0,
            version=1,
        )
        peer_intents = [
            {
                "robotId": "R2",
                "position": Position(x=0, y=5),
                "plannedPath": [Position(x=1, y=5, tick=1), Position(x=2, y=5, tick=2)],
                "status": "MOVING",
                "timestamp": 0,
            }
        ]
        conflict = self.detector.detect(own_state, own_path, peer_intents)
        self.assertIsNone(conflict)

    def test_same_cell_conflict(self):
        own_state = self._create_state("R1", 0, 0, 0)
        own_path = RobotPath(
            robotId="R1",
            waypoints=[
                Position(x=1, y=0, tick=1),
                Position(x=2, y=0, tick=2),
                Position(x=3, y=0, tick=3),
            ],
            generatedAtTick=0,
            version=1,
        )
        peer_intents = [
            {
                "robotId": "R2",
                "position": Position(x=2, y=2),
                "plannedPath": [
                    Position(x=2, y=1, tick=1),
                    Position(x=2, y=0, tick=2),  # Overlaps with R1 at (2, 0) at tick 2
                    Position(x=2, y=-1, tick=3),
                ],
                "status": "MOVING",
                "timestamp": 0,
            }
        ]
        conflict = self.detector.detect(own_state, own_path, peer_intents)
        self.assertIsNotNone(conflict)
        self.assertEqual(conflict.type, "SAME_CELL")
        self.assertEqual(conflict.predictedCell.x, 2)
        self.assertEqual(conflict.predictedCell.y, 0)
        self.assertEqual(conflict.predictedTick, 2)
        self.assertIn("R1", conflict.robotIds)
        self.assertIn("R2", conflict.robotIds)

    def test_crossing_conflict_edge_swap(self):
        own_state = self._create_state("R1", 0, 0, 0)
        own_path = RobotPath(
            robotId="R1",
            waypoints=[
                Position(x=1, y=0, tick=1),
                Position(x=2, y=0, tick=2),
            ],
            generatedAtTick=0,
            version=1,
        )
        peer_intents = [
            {
                "robotId": "R2",
                "position": Position(x=3, y=0),
                "plannedPath": [
                    Position(x=2, y=0, tick=1),
                    Position(x=1, y=0, tick=2),  # Swaps (1,0) and (2,0) with R1
                ],
                "status": "MOVING",
                "timestamp": 0,
            }
        ]
        conflict = self.detector.detect(own_state, own_path, peer_intents)
        self.assertIsNotNone(conflict)
        self.assertEqual(conflict.type, "CROSSING")
        self.assertEqual(conflict.predictedTick, 2)

    def test_narrow_aisle_headon(self):
        own_state = self._create_state("R1", 1, 1, 0)
        own_path = RobotPath(
            robotId="R1",
            waypoints=[
                Position(x=2, y=1, tick=1),
                Position(x=3, y=1, tick=2),
                Position(x=4, y=1, tick=3),
            ],
            generatedAtTick=0,
            version=1,
        )
        peer_intents = [
            {
                "robotId": "R2",
                "position": Position(x=5, y=1),
                "plannedPath": [
                    Position(x=4, y=1, tick=1),
                    Position(x=3, y=1, tick=2),
                    Position(x=2, y=1, tick=3),
                ],
                "status": "MOVING",
                "timestamp": 0,
            }
        ]
        conflict = self.detector.detect(own_state, own_path, peer_intents)
        self.assertIsNotNone(conflict)
        self.assertIn(conflict.type, ["SAME_CELL", "NARROW_AISLE_HEADON", "CROSSING"])

    def test_ignore_offline_peer(self):
        own_state = self._create_state("R1", 0, 0, 0)
        own_path = RobotPath(
            robotId="R1",
            waypoints=[Position(x=1, y=0, tick=1)],
            generatedAtTick=0,
            version=1,
        )
        peer_intents = [
            {
                "robotId": "R2",
                "position": Position(x=2, y=0),
                "plannedPath": [Position(x=1, y=0, tick=1)],
                "status": "OFFLINE",  # Should be ignored
                "timestamp": 0,
            }
        ]
        conflict = self.detector.detect(own_state, own_path, peer_intents)
        self.assertIsNone(conflict)


if __name__ == "__main__":
    unittest.main()
