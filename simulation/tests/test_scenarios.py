"""Scenario test suite: verifies all 8 demo scenarios execute cleanly without crashing.
Owner: Member 3
"""

import unittest
from simulation.runner import SimulationRunner
from simulation.scenarios import list_scenarios
from shared.python.models import Position, WarehouseMap


def _create_test_warehouse_map(width: int = 20, height: int = 20) -> WarehouseMap:
    """Isolated test fixture mock map for Member 3 scenario testing."""
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


class TestAllScenarios(unittest.TestCase):
    def setUp(self):
        self.runner = SimulationRunner(backend_url="http://127.0.0.1:59999")
        self.test_map = _create_test_warehouse_map()

    def test_all_scenarios_execute_to_completion(self):
        scenarios = list_scenarios()
        self.assertEqual(len(scenarios), 8)

        for sid in scenarios:
            with self.subTest(scenario=sid):
                metric = self.runner.run(
                    sid,
                    mode="DECENTRALIZED_PROPOSED",
                    speed="BATCH",
                    warehouse_map=self.test_map,
                )
                self.assertIsNotNone(metric)
                self.assertEqual(metric.scenarioId, sid)
                self.assertGreater(metric.totalCompletionTicks, 0)

    def test_negative_control_zero_collisions(self):
        """Scenario H (negative control) must verify zero collisions and zero spurious errors."""
        metric = self.runner.run(
            "h_negative_control",
            mode="DECENTRALIZED_PROPOSED",
            speed="BATCH",
            warehouse_map=self.test_map,
        )
        self.assertEqual(metric.collisionCount, 0)
        self.assertEqual(metric.deadlockCount, 0)


if __name__ == "__main__":
    unittest.main()
