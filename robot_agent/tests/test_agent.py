"""Integration tests for RobotAgent orchestration loop.
Owner: Member 3
"""

import unittest
from shared.python.models import Position, RobotPath, RobotState, Telemetry
from collision_engine.deadlock import DeadlockDetector
from collision_engine.detection import ConflictDetector
from collision_engine.resolution import ConflictResolver
from robot_agent.agent import RobotAgent


class MockPlanner:
    def __init__(self, waypoints=None):
        self.waypoints = waypoints or [Position(x=1, y=0, tick=1), Position(x=2, y=0, tick=2)]

    def plan(self, start, goal, blocked_cells=None, avoid_intervals=None, start_tick=0):
        return RobotPath(
            robotId="R1",
            waypoints=list(self.waypoints),
            generatedAtTick=start_tick,
            version=1,
        )


class MockTransport:
    def __init__(self):
        self.broadcasted = []
        self.incoming = []

    def broadcast(self, msg):
        self.broadcasted.append(msg)

    def send(self, to, msg):
        pass

    def receive(self, robot_id):
        return list(self.incoming)


class MockSensor:
    def __init__(self, pos=None, health="OK"):
        self.pos = pos or Position(x=0, y=0)
        self.health = health

    def read(self, robot_id, current_tick):
        return Telemetry(
            robotId=robot_id,
            position=self.pos,
            battery=95.0,
            obstacleDetected=False,
            sensorHealth=self.health,
            tick=current_tick,
        )


class TestRobotAgent(unittest.TestCase):
    def setUp(self):
        self.planner = MockPlanner()
        self.transport = MockTransport()
        self.sensor = MockSensor()
        self.detector = ConflictDetector()
        self.resolver = ConflictResolver()
        self.deadlock = DeadlockDetector(stall_threshold=5)

        self.agent = RobotAgent(
            robot_id="R1",
            planner=self.planner,
            transport=self.transport,
            sensor=self.sensor,
            detector=self.detector,
            resolver=self.resolver,
            deadlock=self.deadlock,
        )

    def test_tick_advances_robot_state(self):
        self.agent.state = RobotState(
            robotId="R1",
            position=Position(x=0, y=0),
            velocity=1.0,
            battery=100.0,
            currentTaskId="task1",
            destination=Position(x=2, y=0),
            currentPath=[Position(x=1, y=0, tick=1), Position(x=2, y=0, tick=2)],
            status="MOVING",
            timestamp=0,
        )

        state = self.agent.tick(1)
        self.assertEqual(state.timestamp, 1)
        self.assertEqual(state.position.x, 1)
        self.assertEqual(state.position.y, 0)
        self.assertEqual(len(self.transport.broadcasted), 1)

    def test_tick_reaches_goal_becomes_idle(self):
        self.agent.state = RobotState(
            robotId="R1",
            position=Position(x=1, y=0),
            velocity=1.0,
            battery=100.0,
            currentTaskId="task1",
            destination=Position(x=2, y=0),
            currentPath=[Position(x=2, y=0, tick=2)],
            status="MOVING",
            timestamp=1,
        )

        state = self.agent.tick(2)
        self.assertEqual(state.position.x, 2)
        self.assertEqual(state.position.y, 0)
        self.assertEqual(state.status, "IDLE")
        self.assertEqual(state.velocity, 0.0)

    def test_tick_waiting_on_conflict(self):
        self.agent.state = RobotState(
            robotId="R1",
            position=Position(x=0, y=0),
            velocity=1.0,
            battery=100.0,
            currentTaskId="task1",
            destination=Position(x=2, y=0),
            currentPath=[Position(x=1, y=0, tick=1), Position(x=2, y=0, tick=2)],
            status="MOVING",
            timestamp=0,
        )
        setattr(self.agent.state, "task_priority", 1)

        # Peer R2 with higher priority claiming (1, 0) at tick 1
        self.transport.incoming = [
            {
                "robotId": "R2",
                "priority": 5,
                "plannedPath": [Position(x=1, y=0, tick=1)],
                "status": "MOVING",
                "timestamp": 0,
            }
        ]

        state = self.agent.tick(1)
        self.assertEqual(state.status, "WAITING")
        self.assertEqual(state.position.x, 0)  # Did not advance into contested cell
        self.assertEqual(self.agent._waiting_on, "R2")

    def test_sensor_offline_marks_robot_offline(self):
        self.sensor.health = "OFFLINE"
        self.agent.state = RobotState(
            robotId="R1",
            position=Position(x=0, y=0),
            velocity=1.0,
            battery=100.0,
            currentTaskId="task1",
            destination=Position(x=2, y=0),
            currentPath=[Position(x=1, y=0, tick=1)],
            status="MOVING",
            timestamp=0,
        )

        state = self.agent.tick(1)
        self.assertEqual(state.status, "OFFLINE")
        self.assertEqual(state.velocity, 0.0)


if __name__ == "__main__":
    unittest.main()
