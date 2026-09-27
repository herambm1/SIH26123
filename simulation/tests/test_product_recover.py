"""Manual recovery of a broken-down robot: ProductSession._apply_recover / TaskInbox recovery queue.

"Mark as fixed" (Java: POST /api/product/robot/{id}/fix -> Python POST /control/recover). Product-mode only; nothing here touches robot_agent/,
collision_engine/, the scenarios or the benchmark. The end-to-end tests document WHY Python has to act: without the recovery a fresh assignment to
a ROBOT_OFFLINE robot is rejected and the robot stays OFFLINE.
"""
import time
import types
import unittest
from unittest import mock

from shared.python.models import Position
from simulation.product.session import ProductSession
from simulation.product.task_inbox import TaskInbox


def _dead_agent(status="OFFLINE", offline_after=5, task_id="t1"):
    state = types.SimpleNamespace(
        status=status, currentTaskId=task_id, destination=Position(x=9, y=9), currentPath=[Position(x=1, y=1)], velocity=0.0,
        position=Position(x=4, y=6),
    )
    return types.SimpleNamespace(
        state=state,
        sensor=types.SimpleNamespace(fault_config=types.SimpleNamespace(offline_after_tick=offline_after)),
        _temporary_avoid_cells=[Position(x=2, y=2)],
        _waiting_on="PR2", _blocked_by_peer="PR2", _stall_ticks=4, _replan_requested=True,
    )


def _session_with(agent, active_offline=("PR1",)):
    s = ProductSession(backend_url="http://127.0.0.1:1")
    s.agents = {"PR1": agent}
    s._deferred_assignments = {"PR1": {"robotId": "PR1"}}
    s._robot_idle_since = {}
    s._world_faults = types.SimpleNamespace(active_offline_robots=set(active_offline))
    return s


def _reasons(s):
    return [e.payload.get("reason", "") for e in s.events if e.type == "SYSTEM"]


class TestTaskInboxRecoveries(unittest.TestCase):
    def test_recovery_queue_is_separate_and_drains_once(self):
        inbox = TaskInbox()
        inbox.submit_recover({"robotId": "PR1"})
        inbox.submit_release({"robotId": "PR2"})
        self.assertEqual(inbox.drain_recoveries(), [{"robotId": "PR1"}])
        self.assertEqual(inbox.drain_recoveries(), [])
        self.assertEqual(inbox.drain_releases(), [{"robotId": "PR2"}])


class TestApplyRecover(unittest.TestCase):
    def test_dead_robot_is_recovered_in_place(self):
        agent = _dead_agent()
        s = _session_with(agent)
        s._apply_recover({"robotId": "PR1"}, tick=40)
        self.assertIsNone(agent.sensor.fault_config.offline_after_tick)
        self.assertNotIn("PR1", s._world_faults.active_offline_robots)
        self.assertEqual(agent.state.status, "IDLE")
        self.assertIsNone(agent.state.currentTaskId)
        self.assertIsNone(agent.state.destination)
        self.assertEqual(agent.state.currentPath, [])
        self.assertEqual(agent._temporary_avoid_cells, [])
        self.assertIsNone(agent._waiting_on)
        self.assertFalse(agent._replan_requested)
        self.assertEqual(s._robot_idle_since["PR1"], 40)
        # position is never touched
        self.assertEqual((agent.state.position.x, agent.state.position.y), (4, 6))
        self.assertTrue(any("recovered (marked as fixed)" in r for r in _reasons(s)))

    def test_dead_robot_whose_status_is_not_sticky_is_still_recovered(self):
        # A dead robot's end-of-tick status can be BLOCKED (a REASSIGN_TASK verdict): the sensor fault is what proves it is dead.
        agent = _dead_agent(status="BLOCKED")
        s = _session_with(agent)
        s._apply_recover({"robotId": "PR1"}, tick=40)
        self.assertEqual(agent.state.status, "IDLE")
        self.assertIsNone(agent.sensor.fault_config.offline_after_tick)

    def test_robot_that_is_not_broken_down_is_left_untouched(self):
        agent = _dead_agent(status="MOVING", offline_after=None)
        s = _session_with(agent, active_offline=())
        s._apply_recover({"robotId": "PR1"}, tick=40)
        self.assertEqual(agent.state.status, "MOVING")
        self.assertEqual(agent.state.currentTaskId, "t1")
        self.assertEqual(len(agent._temporary_avoid_cells), 1)
        self.assertTrue(any("is not broken down" in r for r in _reasons(s)))

    def test_a_fault_scheduled_for_the_future_is_not_yet_a_breakdown(self):
        agent = _dead_agent(status="MOVING", offline_after=100)
        s = _session_with(agent)
        s._apply_recover({"robotId": "PR1"}, tick=40)
        self.assertEqual(agent.state.status, "MOVING")
        self.assertEqual(agent.sensor.fault_config.offline_after_tick, 100)

    def test_unknown_robot_is_rejected(self):
        s = _session_with(_dead_agent())
        s._apply_recover({"robotId": "PR9"}, tick=40)
        self.assertTrue(any("unknown robotId" in r for r in _reasons(s)))


def _run_probe(recover: bool, seed: int = 3):
    """Kill PR1 at tick 5; at tick 15 (optionally recover it first, then) assign it a fresh task. Returns (session, PR1 statuses per tick)."""
    statuses = {}
    from robot_agent.agent import RobotAgent
    orig_tick = RobotAgent.tick

    def tick(self, t):
        st = orig_tick(self, t)
        if self.robot_id == "PR1":
            statuses[t] = st.status
        return st

    with mock.patch.object(ProductSession, "_push_to_backend", lambda self, *a, **k: None), \
            mock.patch("simulation.product.world_faults.WorldFaultGenerator.maybe_generate", lambda self, *a, **k: None), \
            mock.patch.object(RobotAgent, "tick", tick):
        s = ProductSession(backend_url="http://127.0.0.1:1")

        def drain_assignments():
            a1 = s.agents["PR1"]
            wm = a1.planner.warehouse_map
            p = a1.state.position
            if s.current_tick == 1:
                far = max(wm.dropPoints, key=lambda q: abs(q.x - p.x) + abs(q.y - p.y))
                return [{"robotId": "PR1", "taskId": "t_far", "dropPosition": {"x": far.x, "y": far.y}, "priority": 3}]
            if s.current_tick == 16:
                near = min((q for q in wm.dropPoints if (q.x, q.y) != (p.x, p.y)), key=lambda q: abs(q.x - p.x) + abs(q.y - p.y))
                return [{"robotId": "PR1", "taskId": "t_near", "dropPosition": {"x": near.x, "y": near.y}, "priority": 3}]
            return []

        def drain_recoveries():
            return [{"robotId": "PR1"}] if (recover and s.current_tick == 15) else []

        s.task_inbox.drain_assignments = drain_assignments
        s.task_inbox.drain_recoveries = drain_recoveries
        s.task_inbox.drain_injections = lambda: [{"kind": "ROBOT_OFFLINE", "robotId": "PR1"}] if s.current_tick == 5 else []
        s.start(seed=seed, speed="BATCH", config={"robotCount": 5, "maxTicks": 30})
        while s.running:
            time.sleep(0.005)
    return s, statuses


class TestRecoverEndToEnd(unittest.TestCase):
    def test_without_recovery_a_fresh_assignment_is_rejected_and_the_robot_stays_offline(self):
        s, statuses = _run_probe(recover=False)
        self.assertEqual(statuses[6], "OFFLINE")
        self.assertEqual(statuses[30], "OFFLINE")
        self.assertTrue(any("is OFFLINE" in r and "rejected" in r for r in _reasons(s)))

    def test_with_recovery_the_robot_leaves_offline_and_accepts_the_assignment(self):
        s, statuses = _run_probe(recover=True)
        self.assertEqual(statuses[14], "OFFLINE")
        for t in range(16, 31):
            self.assertNotEqual(statuses[t], "OFFLINE", f"tick {t}")
        self.assertFalse(any("rejected" in r for r in _reasons(s)))
        self.assertTrue(any(e.type == "TASK_ASSIGNED" and e.payload.get("taskId") == "t_near" for e in s.events))
        self.assertIsNone(s.agents["PR1"].sensor.fault_config.offline_after_tick)
        self.assertEqual(s.collision_count, 0)


if __name__ == "__main__":
    unittest.main()
