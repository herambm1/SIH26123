"""Integration tests for SimulationRunner and multi-mode benchmarking.
Owner: Member 3
"""

import unittest
from simulation.runner import SimulationRunner
from shared.python.models import PerformanceMetric, Position, WarehouseMap


def _create_test_warehouse_map(width: int = 20, height: int = 20) -> WarehouseMap:
    """Isolated test fixture mock map for Member 3 runner tests."""
    obstacles = []
    for x in range(width):
        obstacles.append(Position(x=x, y=0))
        obstacles.append(Position(x=x, y=height - 1))
    for y in range(height):
        obstacles.append(Position(x=0, y=y))
        obstacles.append(Position(x=width - 1, y=y))
    for rack_x in [4, 7, 12, 15]:
        for y in range(3, 17):
            if y not in (9, 10):
                obstacles.append(Position(x=rack_x, y=y))
    return WarehouseMap(
        gridWidth=width,
        gridHeight=height,
        obstacles=obstacles,
        chokePoints=[Position(x=10, y=9)],
    )


class TestSimulationRunner(unittest.TestCase):
    def setUp(self):
        # Point to unreachable port to verify resilient offline behavior
        self.runner = SimulationRunner(backend_url="http://127.0.0.1:59999")
        self.test_map = _create_test_warehouse_map()

    def test_run_decentralized_proposed_mode(self):
        metric = self.runner.run(
            "a_normal",
            mode="DECENTRALIZED_PROPOSED",
            speed="BATCH",
            max_ticks=20,
            warehouse_map=self.test_map,
        )
        self.assertIsInstance(metric, PerformanceMetric)
        self.assertEqual(metric.scenarioId, "a_normal")
        self.assertEqual(metric.mode, "DECENTRALIZED_PROPOSED")
        self.assertEqual(metric.collisionCount, 0)
        self.assertGreater(metric.totalCompletionTicks, 0)

    def test_run_stop_and_wait_mode(self):
        metric = self.runner.run(
            "a_normal",
            mode="STOP_AND_WAIT",
            speed="BATCH",
            max_ticks=20,
            warehouse_map=self.test_map,
        )
        self.assertIsInstance(metric, PerformanceMetric)
        self.assertEqual(metric.mode, "STOP_AND_WAIT")
        self.assertEqual(metric.collisionCount, 0)

    def test_run_centralized_reservation_mode(self):
        metric = self.runner.run(
            "a_normal",
            mode="CENTRALIZED_RESERVATION",
            speed="BATCH",
            max_ticks=20,
            warehouse_map=self.test_map,
        )
        self.assertIsInstance(metric, PerformanceMetric)
        self.assertEqual(metric.mode, "CENTRALIZED_RESERVATION")
        self.assertEqual(metric.collisionCount, 0)

    def test_stop_control(self):
        self.runner.stop()
        self.assertFalse(self.runner.running)


if __name__ == "__main__":
    unittest.main()
