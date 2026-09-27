"""Product mode: at most ONE robot broken down (ROBOT_OFFLINE) at a time. A guard/parameter on WorldFaultGenerator (same category as the
existing cooldown and max_concurrent limits): applies to auto-generated and manual injections alike, and "Mark as fixed" frees the slot."""
import time
import types
import unittest
from unittest import mock

from simulation.product.session import ProductSession
from simulation.product.world_faults import FaultGuardRejected, WorldFaultGenerator


def _agents(*ids):
    return {
        rid: types.SimpleNamespace(
            state=types.SimpleNamespace(status="MOVING", destination=object(), currentPath=[]),
            sensor=types.SimpleNamespace(fault_config=types.SimpleNamespace(offline_after_tick=None)),
        )
        for rid in ids
    }


class TestOfflineCap(unittest.TestCase):
    def test_default_is_one_broken_robot_at_a_time(self):
        self.assertEqual(WorldFaultGenerator(seed=1).max_concurrent_offline, 1)

    def test_a_second_breakdown_is_rejected_until_the_first_is_freed(self):
        wf = WorldFaultGenerator(seed=1)
        agents = _agents("PR1", "PR2")
        wf.try_apply_robot_offline(100, "PR1", agents)
        self.assertEqual(wf.active_offline_robots, {"PR1"})
        with self.assertRaises(FaultGuardRejected) as ctx:
            wf.try_apply_robot_offline(200, "PR2", agents)   # cooldown long over: it is the cap that rejects
        self.assertIn("max concurrent broken-down robots", str(ctx.exception))
        self.assertIsNone(agents["PR2"].sensor.fault_config.offline_after_tick)
        # "Mark as fixed" (ProductSession._apply_recover) discards the robot from the set: the slot is free again
        wf.active_offline_robots.discard("PR1")
        wf.try_apply_robot_offline(300, "PR2", agents)
        self.assertEqual(wf.active_offline_robots, {"PR2"})

    def test_the_cap_is_a_parameter(self):
        wf = WorldFaultGenerator(seed=1, max_concurrent_offline=2)
        agents = _agents("PR1", "PR2", "PR3")
        wf.try_apply_robot_offline(100, "PR1", agents)
        wf.try_apply_robot_offline(200, "PR2", agents)
        with self.assertRaises(FaultGuardRejected):
            wf.try_apply_robot_offline(300, "PR3", agents)   # the combined max_concurrent (2) still applies

    def test_auto_generation_never_breaks_a_second_robot_and_stays_quiet_when_capped(self):
        wf = WorldFaultGenerator(seed=1, generation_probability=1.0, cooldown_ticks=0, max_concurrent=5)
        agents = _agents("PR1", "PR2", "PR3")
        wf.try_apply_robot_offline(1, "PR1", agents)
        with mock.patch.object(wf._rng, "choice", return_value="ROBOT_OFFLINE"):
            for tick in range(10, 60):
                self.assertIsNone(wf.maybe_generate(tick, agents, {}, None, None))   # no attempt, no "fault skipped" event
        self.assertEqual(wf.active_offline_robots, {"PR1"})


class TestManualInjectionInARealSession(unittest.TestCase):
    def test_second_manual_breakdown_is_refused_with_a_system_event_and_the_robot_keeps_working(self):
        with mock.patch.object(ProductSession, "_push_to_backend", lambda self, *a, **k: None), \
                mock.patch("simulation.product.world_faults.WorldFaultGenerator.maybe_generate", lambda self, *a, **k: None):
            s = ProductSession(backend_url="http://127.0.0.1:1")

            def injections():
                if s.current_tick == 5:
                    return [{"kind": "ROBOT_OFFLINE", "robotId": "PR1"}]
                if s.current_tick == 40:                       # well past the 15-tick cooldown
                    return [{"kind": "ROBOT_OFFLINE", "robotId": "PR2"}]
                return []

            s.task_inbox.drain_assignments = lambda: []
            s.task_inbox.drain_injections = injections
            s.start(seed=3, speed="BATCH", config={"robotCount": 5, "maxTicks": 60})
            while s.running:
                time.sleep(0.005)
        self.assertEqual(s._world_faults.active_offline_robots, {"PR1"})
        self.assertLess(s.agents["PR1"].sensor.fault_config.offline_after_tick or 10**9, 10**9)
        self.assertIsNone(s.agents["PR2"].sensor.fault_config.offline_after_tick)
        reasons = [e.payload.get("reason", "") for e in s.events if e.type == "SYSTEM"]
        self.assertTrue(any("max concurrent broken-down robots" in r for r in reasons), reasons)


if __name__ == "__main__":
    unittest.main()
