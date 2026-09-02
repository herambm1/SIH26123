"""Unit tests for DeadlockDetector.
Owner: Member 3
"""

import unittest
from collision_engine.deadlock import DeadlockDetector


class TestDeadlockDetector(unittest.TestCase):
    def setUp(self):
        self.detector = DeadlockDetector(stall_threshold=5)

    def test_no_stall(self):
        # stall_ticks = 0 -> False
        self.assertFalse(self.detector.check("R1", stall_ticks=0, waiting_on="R2"))

    def test_stall_below_threshold(self):
        # stall_ticks = 4 (< 5) -> False
        self.assertFalse(self.detector.check("R1", stall_ticks=4, waiting_on="R2"))

    def test_stall_at_threshold(self):
        # stall_ticks = 5 (== 5) with waiting_on -> True
        self.assertTrue(self.detector.check("R1", stall_ticks=5, waiting_on="R2"))

    def test_stall_above_threshold(self):
        # stall_ticks = 8 (> 5) with waiting_on -> True
        self.assertTrue(self.detector.check("R1", stall_ticks=8, waiting_on="R2"))

    def test_stall_without_waiting_on(self):
        # Even if stalled, if not waiting on a specific peer -> False
        self.assertFalse(self.detector.check("R1", stall_ticks=10, waiting_on=None))


if __name__ == "__main__":
    unittest.main()
