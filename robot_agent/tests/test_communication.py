"""
robot_agent/tests/test_communication.py — Unit tests for Member 2's communication module.
Owner: Member 2

Covers (per spec §6):
  A. Transport interface existence
  B. Bus initialization with multiple robots
  C. Direct send
  D. Broadcast delivery
  E. Sender does NOT receive its own broadcast
  F. Empty receive queue
  G. Unknown robot handling
  H. drop_rate = 0.0 (no drop)
  I. drop_rate = 1.0 (all dropped)
  J. Probabilistic drop/delivery behavior
  K. delay_ticks = 0 (immediate)
  L. Delayed message release timing
  M. Multiple messages
  N. Multiple robots
  O. build_intent_message()
  P. Required fields present
  Q. JSON serialization
  R. RobotState not mutated

These tests are fully standalone — no RobotAgent, no Member 3 code required.
"""

import json
import random
import unittest
from abc import ABC

from shared.python.models import Position, RobotState

from robot_agent.communication.messages import build_intent_message
from robot_agent.communication.transport import (
    InProcessBus,
    MessageFaultConfig,
    Transport,
    UnknownRobotError,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_state(
    robot_id="R1",
    x=0, y=0,
    battery=90.0,
    status="MOVING",
    timestamp=5,
    destination=None,
    current_path=None,
    task_id=None,
    task_priority=None,
):
    """Construct a minimal but valid RobotState for testing."""
    state = RobotState(
        robotId=robot_id,
        position=Position(x=x, y=y),
        velocity=1.0,
        battery=battery,
        currentTaskId=task_id,
        destination=destination,
        currentPath=current_path or [],
        status=status,
        timestamp=timestamp,
    )
    if task_priority is not None:
        state.task_priority = task_priority
    return state


REQUIRED_FIELDS = {
    "robotId", "position", "destination", "plannedPath",
    "currentTask", "priority", "battery", "status", "timestamp",
}

ROBOT_IDS = ["R1", "R2", "R3"]


# ── A. Transport interface existence ─────────────────────────────────────────

class TestTransportInterface(unittest.TestCase):
    def test_transport_is_abstract(self):
        self.assertTrue(issubclass(Transport, ABC))

    def test_transport_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            Transport()  # type: ignore[abstract]

    def test_transport_has_send(self):
        self.assertTrue(hasattr(Transport, "send"))

    def test_transport_has_broadcast(self):
        self.assertTrue(hasattr(Transport, "broadcast"))

    def test_transport_has_receive(self):
        self.assertTrue(hasattr(Transport, "receive"))

    def test_inprocessbus_is_subclass(self):
        self.assertTrue(issubclass(InProcessBus, Transport))


# ── B. Bus initialization ────────────────────────────────────────────────────

class TestBusInitialization(unittest.TestCase):
    def test_init_with_multiple_robots(self):
        bus = InProcessBus(ROBOT_IDS)
        self.assertIsInstance(bus, InProcessBus)

    def test_init_empty_raises(self):
        with self.assertRaises(ValueError):
            InProcessBus([])

    def test_init_duplicate_ids_raises(self):
        with self.assertRaises(ValueError):
            InProcessBus(["R1", "R1"])

    def test_init_with_fault_config(self):
        cfg = MessageFaultConfig(drop_rate=0.5, delay_ticks=2)
        bus = InProcessBus(ROBOT_IDS, fault_config=cfg)
        self.assertIsInstance(bus, InProcessBus)

    def test_init_fault_config_none(self):
        bus = InProcessBus(ROBOT_IDS, fault_config=None)
        self.assertIsInstance(bus, InProcessBus)


# ── C. Direct send ───────────────────────────────────────────────────────────

class TestDirectSend(unittest.TestCase):
    def setUp(self):
        self.bus = InProcessBus(ROBOT_IDS)

    def test_send_delivers_to_recipient(self):
        msg = {"robotId": "R1", "data": "hello"}
        self.bus.send("R2", msg)
        received = self.bus.receive("R2")
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["data"], "hello")

    def test_send_does_not_deliver_to_other_robots(self):
        msg = {"robotId": "R1", "data": "hello"}
        self.bus.send("R2", msg)
        self.assertEqual(self.bus.receive("R1"), [])
        self.assertEqual(self.bus.receive("R3"), [])

    def test_send_clears_queue_on_receive(self):
        self.bus.send("R2", {"robotId": "R1"})
        self.bus.receive("R2")
        self.assertEqual(self.bus.receive("R2"), [])


# ── D. Broadcast delivery ────────────────────────────────────────────────────

class TestBroadcast(unittest.TestCase):
    def setUp(self):
        self.bus = InProcessBus(ROBOT_IDS)

    def test_broadcast_reaches_all_others(self):
        msg = {"robotId": "R1", "info": "broadcast"}
        self.bus.broadcast(msg)
        for rid in ["R2", "R3"]:
            msgs = self.bus.receive(rid)
            self.assertEqual(len(msgs), 1)
            self.assertEqual(msgs[0]["info"], "broadcast")

    # E. Sender does NOT receive its own broadcast
    def test_broadcast_sender_excluded(self):
        msg = {"robotId": "R1", "info": "self-check"}
        self.bus.broadcast(msg)
        self.assertEqual(self.bus.receive("R1"), [])

    def test_broadcast_message_content_preserved(self):
        payload = {"robotId": "R2", "status": "MOVING", "battery": 75.0}
        self.bus.broadcast(payload)
        received = self.bus.receive("R1")
        self.assertEqual(received[0]["battery"], 75.0)
        self.assertEqual(received[0]["status"], "MOVING")


# ── F. Empty receive queue ───────────────────────────────────────────────────

class TestEmptyReceive(unittest.TestCase):
    def test_empty_queue_returns_list(self):
        bus = InProcessBus(ROBOT_IDS)
        result = bus.receive("R1")
        self.assertIsInstance(result, list)
        self.assertEqual(result, [])

    def test_receive_after_empty_does_not_raise(self):
        bus = InProcessBus(["R1"])
        bus.receive("R1")   # first call
        bus.receive("R1")   # second call — must not raise


# ── G. Unknown robot handling ────────────────────────────────────────────────

class TestUnknownRobot(unittest.TestCase):
    def setUp(self):
        self.bus = InProcessBus(["R1", "R2"])

    def test_send_unknown_recipient_raises(self):
        with self.assertRaises(UnknownRobotError):
            self.bus.send("UNKNOWN", {"robotId": "R1"})

    def test_broadcast_unknown_sender_raises(self):
        with self.assertRaises(UnknownRobotError):
            self.bus.broadcast({"robotId": "GHOST"})

    def test_receive_unknown_raises(self):
        with self.assertRaises(UnknownRobotError):
            self.bus.receive("UNKNOWN")

    def test_error_message_contains_robot_id(self):
        try:
            self.bus.send("BAD_ID", {})
        except UnknownRobotError as e:
            self.assertIn("BAD_ID", str(e))

    def test_unknown_robot_error_is_exception(self):
        self.assertTrue(issubclass(UnknownRobotError, Exception))


# ── MessageFaultConfig validation ────────────────────────────────────────────

class TestMessageFaultConfig(unittest.TestCase):
    def test_default_values(self):
        cfg = MessageFaultConfig()
        self.assertEqual(cfg.drop_rate, 0.0)
        self.assertEqual(cfg.delay_ticks, 0)

    def test_valid_config(self):
        cfg = MessageFaultConfig(drop_rate=0.3, delay_ticks=2)
        self.assertEqual(cfg.drop_rate, 0.3)
        self.assertEqual(cfg.delay_ticks, 2)

    def test_drop_rate_too_high_raises(self):
        with self.assertRaises(ValueError):
            MessageFaultConfig(drop_rate=1.1)

    def test_drop_rate_negative_raises(self):
        with self.assertRaises(ValueError):
            MessageFaultConfig(drop_rate=-0.1)

    def test_delay_ticks_negative_raises(self):
        with self.assertRaises(ValueError):
            MessageFaultConfig(delay_ticks=-1)

    def test_drop_rate_exactly_zero_ok(self):
        cfg = MessageFaultConfig(drop_rate=0.0)
        self.assertEqual(cfg.drop_rate, 0.0)

    def test_drop_rate_exactly_one_ok(self):
        cfg = MessageFaultConfig(drop_rate=1.0)
        self.assertEqual(cfg.drop_rate, 1.0)


# ── H. drop_rate = 0.0 ───────────────────────────────────────────────────────

class TestDropRateZero(unittest.TestCase):
    def test_no_drop_at_zero(self):
        cfg = MessageFaultConfig(drop_rate=0.0)
        bus = InProcessBus(["R1", "R2"], fault_config=cfg)
        for i in range(20):
            bus.broadcast({"robotId": "R1", "seq": i})
        received = bus.receive("R2")
        self.assertEqual(len(received), 20)


# ── I. drop_rate = 1.0 ───────────────────────────────────────────────────────

class TestDropRateOne(unittest.TestCase):
    def test_all_dropped_at_one(self):
        cfg = MessageFaultConfig(drop_rate=1.0)
        bus = InProcessBus(["R1", "R2"], fault_config=cfg)
        for i in range(20):
            bus.broadcast({"robotId": "R1", "seq": i})
        received = bus.receive("R2")
        self.assertEqual(received, [])

    def test_send_all_dropped(self):
        cfg = MessageFaultConfig(drop_rate=1.0)
        bus = InProcessBus(["R1", "R2"], fault_config=cfg)
        bus.send("R2", {"robotId": "R1", "data": "x"})
        self.assertEqual(bus.receive("R2"), [])


# ── J. Probabilistic drop/delivery ──────────────────────────────────────────

class TestProbabilisticDrop(unittest.TestCase):
    """Uses a seeded RNG for deterministic results."""

    def _run_with_rate(self, drop_rate, n=1000):
        rng = random.Random(42)
        cfg = MessageFaultConfig(drop_rate=drop_rate)
        bus = InProcessBus(["R1", "R2"], fault_config=cfg, rng=rng)
        for i in range(n):
            bus.send("R2", {"robotId": "R1", "seq": i})
        return len(bus.receive("R2"))

    def test_partial_drop_some_delivered(self):
        # With drop_rate=0.5 and n=1000, expect roughly 500 ± 100 delivered
        delivered = self._run_with_rate(0.5, 1000)
        self.assertGreater(delivered, 350)
        self.assertLess(delivered, 650)

    def test_low_drop_rate_mostly_delivered(self):
        delivered = self._run_with_rate(0.1, 100)
        # Expect at least 70 of 100 delivered
        self.assertGreaterEqual(delivered, 70)

    def test_high_drop_rate_mostly_dropped(self):
        delivered = self._run_with_rate(0.9, 100)
        # Expect at most 30 of 100 delivered
        self.assertLessEqual(delivered, 30)


# ── K. delay_ticks = 0 ───────────────────────────────────────────────────────

class TestDelayZero(unittest.TestCase):
    def test_immediate_delivery_without_advance(self):
        cfg = MessageFaultConfig(delay_ticks=0)
        bus = InProcessBus(["R1", "R2"], fault_config=cfg)
        bus.send("R2", {"robotId": "R1", "v": 1})
        # No advance_tick() needed
        msgs = bus.receive("R2")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["v"], 1)


# ── L. Delayed message release timing ────────────────────────────────────────

class TestDelayedDelivery(unittest.TestCase):
    def test_delay_1_not_visible_before_advance(self):
        cfg = MessageFaultConfig(delay_ticks=1)
        bus = InProcessBus(["R1", "R2"], fault_config=cfg)
        bus.send("R2", {"robotId": "R1", "msg": "delayed"})
        # No advance_tick yet — should not be visible
        self.assertEqual(bus.receive("R2"), [])

    def test_delay_1_visible_after_one_advance(self):
        cfg = MessageFaultConfig(delay_ticks=1)
        bus = InProcessBus(["R1", "R2"], fault_config=cfg)
        bus.send("R2", {"robotId": "R1", "msg": "delayed"})
        bus.advance_tick()
        msgs = bus.receive("R2")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["msg"], "delayed")

    def test_delay_3_not_visible_after_two_advances(self):
        cfg = MessageFaultConfig(delay_ticks=3)
        bus = InProcessBus(["R1", "R2"], fault_config=cfg)
        bus.send("R2", {"robotId": "R1", "msg": "triple-delay"})
        bus.advance_tick()
        bus.advance_tick()
        self.assertEqual(bus.receive("R2"), [])

    def test_delay_3_visible_after_three_advances(self):
        cfg = MessageFaultConfig(delay_ticks=3)
        bus = InProcessBus(["R1", "R2"], fault_config=cfg)
        bus.send("R2", {"robotId": "R1", "msg": "triple-delay"})
        bus.advance_tick()
        bus.advance_tick()
        bus.advance_tick()
        msgs = bus.receive("R2")
        self.assertEqual(len(msgs), 1)

    def test_delay_broadcast_timing(self):
        cfg = MessageFaultConfig(delay_ticks=2)
        bus = InProcessBus(["R1", "R2", "R3"], fault_config=cfg)
        bus.broadcast({"robotId": "R1", "data": "bc"})
        bus.advance_tick()
        # After 1/2 ticks — not yet
        self.assertEqual(bus.receive("R2"), [])
        bus.advance_tick()
        # After 2/2 ticks — now visible
        self.assertEqual(len(bus.receive("R2")), 1)
        self.assertEqual(len(bus.receive("R3")), 1)


# ── M. Multiple messages ──────────────────────────────────────────────────────

class TestMultipleMessages(unittest.TestCase):
    def test_multiple_sends_accumulate(self):
        bus = InProcessBus(["R1", "R2"])
        for i in range(5):
            bus.send("R2", {"robotId": "R1", "seq": i})
        msgs = bus.receive("R2")
        self.assertEqual(len(msgs), 5)
        seqs = [m["seq"] for m in msgs]
        self.assertEqual(sorted(seqs), list(range(5)))

    def test_receive_clears_queue(self):
        bus = InProcessBus(["R1", "R2"])
        bus.send("R2", {"robotId": "R1"})
        bus.receive("R2")
        self.assertEqual(bus.receive("R2"), [])


# ── N. Multiple robots ────────────────────────────────────────────────────────

class TestMultipleRobots(unittest.TestCase):
    def test_four_robots_broadcast(self):
        ids = ["R1", "R2", "R3", "R4"]
        bus = InProcessBus(ids)
        bus.broadcast({"robotId": "R1", "info": "hello"})
        for rid in ["R2", "R3", "R4"]:
            self.assertEqual(len(bus.receive(rid)), 1)
        self.assertEqual(bus.receive("R1"), [])

    def test_each_robot_independent_queue(self):
        ids = ["RA", "RB", "RC"]
        bus = InProcessBus(ids)
        bus.send("RB", {"robotId": "RA", "v": 1})
        bus.send("RC", {"robotId": "RA", "v": 2})
        self.assertEqual(len(bus.receive("RB")), 1)
        self.assertEqual(len(bus.receive("RC")), 1)
        self.assertEqual(bus.receive("RA"), [])


# ── O. build_intent_message() ─────────────────────────────────────────────────

class TestBuildIntentMessage(unittest.TestCase):
    def test_returns_dict(self):
        state = make_state()
        result = build_intent_message(state)
        self.assertIsInstance(result, dict)

    def test_wrong_type_raises(self):
        with self.assertRaises(TypeError):
            build_intent_message("not-a-state")  # type: ignore[arg-type]

    def test_with_full_state(self):
        dest = Position(x=10, y=5)
        path = [Position(x=1, y=0, tick=6), Position(x=2, y=0, tick=7)]
        state = make_state(
            robot_id="R2",
            x=0, y=0,
            battery=80.0,
            status="MOVING",
            timestamp=5,
            destination=dest,
            current_path=path,
            task_id="T42",
            task_priority=3,
        )
        msg = build_intent_message(state)
        self.assertEqual(msg["robotId"], "R2")
        self.assertEqual(msg["battery"], 80.0)
        self.assertEqual(msg["status"], "MOVING")
        self.assertEqual(msg["timestamp"], 5)
        self.assertEqual(msg["currentTask"], "T42")
        self.assertEqual(msg["priority"], 3)

    def test_destination_none(self):
        state = make_state(destination=None)
        msg = build_intent_message(state)
        self.assertIsNone(msg["destination"])

    def test_planned_path_empty(self):
        state = make_state(current_path=[])
        msg = build_intent_message(state)
        self.assertEqual(msg["plannedPath"], [])

    def test_planned_path_contains_waypoints(self):
        path = [Position(x=1, y=2, tick=10), Position(x=3, y=4, tick=11)]
        state = make_state(current_path=path)
        msg = build_intent_message(state)
        self.assertEqual(len(msg["plannedPath"]), 2)
        self.assertEqual(msg["plannedPath"][0], {"x": 1, "y": 2, "tick": 10})
        self.assertEqual(msg["plannedPath"][1], {"x": 3, "y": 4, "tick": 11})

    def test_priority_defaults_to_1(self):
        # RobotState has no task_priority attribute by default
        state = make_state()
        msg = build_intent_message(state)
        self.assertEqual(msg["priority"], 1)

    def test_position_serialized_as_dict(self):
        state = make_state(x=3, y=7)
        msg = build_intent_message(state)
        self.assertIsInstance(msg["position"], dict)
        self.assertEqual(msg["position"]["x"], 3)
        self.assertEqual(msg["position"]["y"], 7)


# ── P. Required fields present ────────────────────────────────────────────────

class TestRequiredFields(unittest.TestCase):
    def test_all_required_fields_present(self):
        state = make_state()
        msg = build_intent_message(state)
        for field in REQUIRED_FIELDS:
            self.assertIn(field, msg, f"Missing field: {field}")

    def test_no_extra_unexpected_fields(self):
        state = make_state()
        msg = build_intent_message(state)
        extras = set(msg.keys()) - REQUIRED_FIELDS
        self.assertEqual(extras, set(), f"Unexpected extra fields: {extras}")


# ── Q. JSON serialization ─────────────────────────────────────────────────────

class TestJsonSerialization(unittest.TestCase):
    def test_serializable_basic(self):
        state = make_state()
        msg = build_intent_message(state)
        json_str = json.dumps(msg)
        self.assertIsInstance(json_str, str)

    def test_serializable_with_path_and_destination(self):
        dest = Position(x=5, y=5)
        path = [Position(x=1, y=0, tick=6)]
        state = make_state(destination=dest, current_path=path, task_id="T1")
        msg = build_intent_message(state)
        json_str = json.dumps(msg)
        parsed = json.loads(json_str)
        self.assertEqual(parsed["robotId"], state.robotId)
        self.assertEqual(parsed["destination"]["x"], 5)
        self.assertEqual(parsed["plannedPath"][0]["tick"], 6)

    def test_round_trip_preserves_values(self):
        state = make_state(robot_id="R99", x=3, y=7, battery=55.5, timestamp=42)
        msg = build_intent_message(state)
        parsed = json.loads(json.dumps(msg))
        self.assertEqual(parsed["robotId"], "R99")
        self.assertEqual(parsed["battery"], 55.5)
        self.assertEqual(parsed["timestamp"], 42)


# ── R. RobotState is not mutated ──────────────────────────────────────────────

class TestRobotStateNotMutated(unittest.TestCase):
    def test_state_unchanged_after_build(self):
        path = [Position(x=1, y=2, tick=5)]
        dest = Position(x=10, y=10)
        state = make_state(
            robot_id="R1",
            x=0, y=0,
            battery=88.0,
            status="MOVING",
            timestamp=3,
            destination=dest,
            current_path=path,
            task_id="T5",
            task_priority=2,
        )
        # Capture before-state
        before = {
            "robotId": state.robotId,
            "battery": state.battery,
            "status": state.status,
            "timestamp": state.timestamp,
            "currentTaskId": state.currentTaskId,
            "path_len": len(state.currentPath),
        }
        build_intent_message(state)
        # Assert nothing changed
        self.assertEqual(state.robotId, before["robotId"])
        self.assertEqual(state.battery, before["battery"])
        self.assertEqual(state.status, before["status"])
        self.assertEqual(state.timestamp, before["timestamp"])
        self.assertEqual(state.currentTaskId, before["currentTaskId"])
        self.assertEqual(len(state.currentPath), before["path_len"])

    def test_path_list_not_modified(self):
        path = [Position(x=1, y=0, tick=1), Position(x=2, y=0, tick=2)]
        state = make_state(current_path=path)
        original_path = list(state.currentPath)
        build_intent_message(state)
        self.assertEqual(state.currentPath, original_path)


if __name__ == "__main__":
    unittest.main()
