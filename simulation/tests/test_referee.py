"""Unit tests for independent CollisionReferee.
Owner: Member 3
"""

import sys
import unittest
from shared.python.models import Position
from simulation.referee import CollisionReferee


class TestCollisionReferee(unittest.TestCase):
    def setUp(self):
        self.referee = CollisionReferee()

    def test_no_collision(self):
        positions = {
            "R1": Position(x=0, y=0),
            "R2": Position(x=5, y=5),
            "R3": Position(x=10, y=10),
        }
        collisions = self.referee.check(positions)
        self.assertEqual(collisions, [])

    def test_same_cell_collision(self):
        positions = {
            "R1": Position(x=3, y=4),
            "R2": Position(x=3, y=4),  # Same cell!
            "R3": Position(x=10, y=10),
        }
        collisions = self.referee.check(positions)
        self.assertEqual(collisions, [("R1", "R2")])

    def test_edge_swap_collision(self):
        # Tick 1: R1 at (2, 2), R2 at (2, 3)
        t1 = {
            "R1": Position(x=2, y=2),
            "R2": Position(x=2, y=3),
        }
        self.assertEqual(self.referee.check(t1), [])

        # Tick 2: R1 moves to (2, 3), R2 moves to (2, 2) -> Swap conflict / collision!
        t2 = {
            "R1": Position(x=2, y=3),
            "R2": Position(x=2, y=2),
        }
        collisions = self.referee.check(t2)
        self.assertEqual(collisions, [("R1", "R2")])

    def test_independence_from_conflict_detector(self):
        """Verify referee does NOT import or call ConflictDetector."""
        import simulation.referee as ref_module

        # Ensure ConflictDetector or collision_engine is not in referee namespace or attributes
        self.assertNotIn("ConflictDetector", ref_module.__dict__)
        self.assertNotIn("collision_engine", ref_module.__dict__)

        # Parse AST to ensure no imports of collision_engine
        import ast
        with open(ref_module.__file__, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn("collision_engine", alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self.assertNotIn("collision_engine", node.module)


if __name__ == "__main__":
    unittest.main()
