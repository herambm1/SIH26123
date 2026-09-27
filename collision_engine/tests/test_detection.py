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


class TestStationaryPeerOccupancy(unittest.TestCase):
    """Regression tests for the referee-verified collisions found by the
    benchmark in scenarios d_deadlock and g_high_load: a robot drove straight
    into a peer that had stopped moving.

    A stopped robot pops its current cell off currentPath when it arrives
    there, so that cell appears in NO planned path and the path-vs-path
    checks were structurally blind to it.
    """

    def setUp(self):
        self.detector = ConflictDetector()

    def _own(self, robot_id="R1", x=10, y=9):
        return RobotState(
            robotId=robot_id, position=Position(x=x, y=y), velocity=1.0, battery=100.0,
            currentTaskId="t1", destination=Position(x=x + 2, y=y), currentPath=[],
            status="MOVING", timestamp=3,
        )

    def test_waiting_peer_standing_on_our_next_cell_is_detected(self):
        """Reproduces d_deadlock: R2 sits WAITING at (11,9) with a stale path
        pointing elsewhere; R1's next waypoint is (11,9)."""
        own_state = self._own()
        own_path = RobotPath(
            robotId="R1",
            waypoints=[Position(x=11, y=9, tick=3), Position(x=12, y=9, tick=4)],
            generatedAtTick=2, version=1,
        )
        peer_intents = [{
            "robotId": "R2",
            "position": {"x": 11, "y": 9, "tick": None},   # where R2 actually is
            "plannedPath": [{"x": 10, "y": 9, "tick": 2}],  # stale, and NOT its own cell
            "status": "WAITING",
            "priority": 1,
            "timestamp": 2,
        }]

        conflict = self.detector.detect(own_state, own_path, peer_intents)

        self.assertIsNotNone(conflict, "stationary peer on our path must raise a conflict")
        self.assertEqual(conflict.type, "SAME_CELL")
        self.assertEqual((conflict.predictedCell.x, conflict.predictedCell.y), (11, 9))
        self.assertCountEqual(conflict.robotIds, ["R1", "R2"])

    def test_parked_peer_with_empty_path_is_detected(self):
        """Reproduces g_high_load: a peer parked at its goal broadcasts an
        EMPTY plannedPath, which used to skip that peer entirely."""
        own_state = self._own()
        own_path = RobotPath(
            robotId="R1",
            waypoints=[Position(x=11, y=9, tick=3), Position(x=12, y=9, tick=4)],
            generatedAtTick=2, version=1,
        )
        peer_intents = [{
            "robotId": "R2",
            "position": {"x": 12, "y": 9, "tick": None},
            "plannedPath": [],           # parked — nothing planned at all
            "status": "IDLE",
            "priority": 1,
            "timestamp": 2,
        }]

        conflict = self.detector.detect(own_state, own_path, peer_intents)

        self.assertIsNotNone(conflict, "peer parked on our path must raise a conflict")
        self.assertEqual(conflict.type, "SAME_CELL")
        self.assertEqual((conflict.predictedCell.x, conflict.predictedCell.y), (12, 9))

    def test_moving_peer_on_our_path_is_not_flagged_as_occupancy(self):
        """A peer that is MOVING will vacate — flagging it would make every
        robot refuse to follow another down a corridor."""
        own_state = self._own()
        own_path = RobotPath(
            robotId="R1",
            waypoints=[Position(x=11, y=9, tick=3)],
            generatedAtTick=2, version=1,
        )
        peer_intents = [{
            "robotId": "R2",
            "position": {"x": 11, "y": 9, "tick": None},
            "plannedPath": [{"x": 11, "y": 8, "tick": 3}],  # moving away
            "status": "MOVING",
            "priority": 1,
            "timestamp": 2,
        }]

        conflict = self.detector.detect(own_state, own_path, peer_intents)
        self.assertIsNone(conflict)

    def test_stationary_peer_not_on_our_path_is_not_flagged(self):
        own_state = self._own()
        own_path = RobotPath(
            robotId="R1",
            waypoints=[Position(x=11, y=9, tick=3)],
            generatedAtTick=2, version=1,
        )
        peer_intents = [{
            "robotId": "R2",
            "position": {"x": 4, "y": 2, "tick": None},   # nowhere near us
            "plannedPath": [],
            "status": "IDLE",
            "priority": 1,
            "timestamp": 2,
        }]

        conflict = self.detector.detect(own_state, own_path, peer_intents)
        self.assertIsNone(conflict)

    def test_offline_peer_still_ignored_by_negotiation(self):
        """detect() deliberately keeps ignoring OFFLINE peers — physical
        safety around a dead robot is RobotAgent's movement guard's job, not
        conflict negotiation's."""
        own_state = self._own()
        own_path = RobotPath(
            robotId="R1",
            waypoints=[Position(x=11, y=9, tick=3)],
            generatedAtTick=2, version=1,
        )
        peer_intents = [{
            "robotId": "R2",
            "position": {"x": 11, "y": 9, "tick": None},
            "plannedPath": [],
            "status": "OFFLINE",
            "priority": 1,
            "timestamp": 2,
        }]

        conflict = self.detector.detect(own_state, own_path, peer_intents)
        self.assertIsNone(conflict)


if __name__ == "__main__":
    unittest.main()
