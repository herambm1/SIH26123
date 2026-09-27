"""Backlog-freeze fix, Python side: ProductSession._apply_release / TaskInbox release queue.

Java's ProductSessionService abandons a task whose robot has not moved for STALL_ABANDON_TICKS and asks Python (POST /control/release) to release
the robot. These tests cover the Python half: what a release does, and every case in which it must leave the robot alone. Product-mode only —
nothing here touches robot_agent/, collision_engine/, the scenarios or the benchmark.
"""
import time
import types
import unittest
from unittest import mock

from shared.python.models import Position
from simulation.product.session import ProductSession
from simulation.product.task_inbox import TaskInbox


def _fake_agent(status="MOVING", task_id="t1", offline_after=None):
    state = types.SimpleNamespace(
        status=status, currentTaskId=task_id, destination=Position(x=9, y=9), currentPath=[Position(x=1, y=1)], velocity=1.0,
    )
    return types.SimpleNamespace(
        state=state,
        sensor=types.SimpleNamespace(fault_config=types.SimpleNamespace(offline_after_tick=offline_after)),
        _temporary_avoid_cells=[Position(x=2, y=2), Position(x=3, y=3)],
        _waiting_on="PR2", _blocked_by_peer="PR2", _stall_ticks=4, _replan_requested=True,
    )


def _session_with(agent):
    s = ProductSession(backend_url="http://127.0.0.1:1")
    s.agents = {"PR1": agent}
    s._deferred_assignments = {"PR1": {"robotId": "PR1"}}
    s._robot_idle_since = {}
    return s


def _reasons(s):
    return [e.payload.get("reason", "") for e in s.events if e.type == "SYSTEM"]


class TestTaskInboxReleases(unittest.TestCase):
    def test_release_queue_is_separate_and_drains_once(self):
        inbox = TaskInbox()
        inbox.submit_release({"robotId": "PR1", "taskId": "t1"})
        inbox.submit_assignment({"robotId": "PR2"})
        self.assertEqual(inbox.drain_releases(), [{"robotId": "PR1", "taskId": "t1"}])
        self.assertEqual(inbox.drain_releases(), [])
        self.assertEqual(inbox.drain_assignments(), [{"robotId": "PR2"}])


class TestApplyRelease(unittest.TestCase):
    def test_stalled_robot_is_released_to_a_clean_idle_state(self):
        agent = _fake_agent()
        s = _session_with(agent)
        s._apply_release({"robotId": "PR1", "taskId": "t1"}, tick=50)
        self.assertEqual(agent.state.status, "IDLE")
        self.assertIsNone(agent.state.currentTaskId)
        self.assertIsNone(agent.state.destination)
        self.assertEqual(agent.state.currentPath, [])
        self.assertEqual(agent._temporary_avoid_cells, [])
        self.assertIsNone(agent._waiting_on)
        self.assertIsNone(agent._blocked_by_peer)
        self.assertEqual(agent._stall_ticks, 0)
        self.assertFalse(agent._replan_requested)
        self.assertNotIn("PR1", s._deferred_assignments)
        self.assertEqual(s._robot_idle_since["PR1"], 50)
        self.assertTrue(any("released from stalled task" in r for r in _reasons(s)))

    def _assert_untouched(self, agent, s):
        self.assertEqual(len(agent._temporary_avoid_cells), 2)
        self.assertEqual(agent._waiting_on, "PR2")
        self.assertEqual(s._robot_idle_since, {})
        self.assertTrue(any("release ignored" in r for r in _reasons(s)))

    def test_offline_robot_is_never_released(self):
        agent = _fake_agent(status="OFFLINE")
        s = _session_with(agent)
        s._apply_release({"robotId": "PR1", "taskId": "t1"}, tick=50)
        self._assert_untouched(agent, s)
        self.assertEqual(agent.state.status, "OFFLINE")

    def test_sensor_dead_robot_whose_status_is_not_offline_is_never_resurrected(self):
        # A dead robot's agent status is not sticky (a REASSIGN_TASK verdict can leave it BLOCKED).
        agent = _fake_agent(status="BLOCKED", offline_after=10)
        s = _session_with(agent)
        s._apply_release({"robotId": "PR1", "taskId": "t1"}, tick=50)
        self._assert_untouched(agent, s)
        self.assertEqual(agent.state.status, "BLOCKED")

    def test_already_idle_robot_is_left_alone(self):
        agent = _fake_agent(status="IDLE", task_id=None)
        s = _session_with(agent)
        s._apply_release({"robotId": "PR1", "taskId": "t1"}, tick=50)
        self.assertEqual(len(agent._temporary_avoid_cells), 2)
        self.assertTrue(any("already IDLE" in r for r in _reasons(s)))

    def test_robot_that_moved_on_to_a_different_task_is_left_alone(self):
        agent = _fake_agent(task_id="t2")
        s = _session_with(agent)
        s._apply_release({"robotId": "PR1", "taskId": "t1"}, tick=50)
        self._assert_untouched(agent, s)
        self.assertEqual(agent.state.currentTaskId, "t2")

    def test_unknown_robot_is_rejected(self):
        s = _session_with(_fake_agent())
        s._apply_release({"robotId": "PR9", "taskId": "t1"}, tick=50)
        self.assertTrue(any("unknown robotId" in r for r in _reasons(s)))


class TestReleaseEndToEnd(unittest.TestCase):
    """A real ProductSession tick loop: a robot is given a task, then released mid-way."""

    def test_released_robot_becomes_idle_and_emits_no_task_completed(self):
        with mock.patch.object(ProductSession, "_push_to_backend", lambda self, *a, **k: None), \
                mock.patch("simulation.product.world_faults.WorldFaultGenerator.maybe_generate", lambda self, *a, **k: None):
            s = ProductSession(backend_url="http://127.0.0.1:1")
            state = {"assigned": False, "released": False}

            def drain_assignments():
                if state["assigned"]:
                    return []
                state["assigned"] = True
                wm = next(iter(s.agents.values())).planner.warehouse_map
                far = max(wm.dropPoints, key=lambda p: abs(p.x - s.agents["PR1"].state.position.x) + abs(p.y - s.agents["PR1"].state.position.y))
                return [{"robotId": "PR1", "taskId": "x_1", "dropPosition": {"x": far.x, "y": far.y}, "priority": 3}]

            def drain_releases():
                if s.current_tick == 6 and not state["released"]:
                    state["released"] = True
                    return [{"robotId": "PR1", "taskId": "x_1"}]
                return []

            s.task_inbox.drain_assignments = drain_assignments
            s.task_inbox.drain_releases = drain_releases
            s.task_inbox.drain_injections = lambda: []
            s.start(seed=7, speed="BATCH", config={"robotCount": 5, "maxTicks": 12})
            while s.running:
                time.sleep(0.005)

        a = s.agents["PR1"]
        self.assertEqual(a.state.status, "IDLE")
        self.assertIsNone(a.state.currentTaskId)
        self.assertTrue(any("released from stalled task" in r for r in _reasons(s)))
        self.assertFalse([e for e in s.events if e.type == "TASK_COMPLETED" and e.payload.get("taskId") == "x_1"])
        self.assertEqual(s.collision_count, 0)


if __name__ == "__main__":
    unittest.main()
