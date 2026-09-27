import random
import unittest

from edge.fault_injection import SensorFaultConfig
from edge.heartbeat import HeartbeatMonitor
from edge.sensor_source import SimulationSensorSource
from shared.python.models import Position, Telemetry


class SensorFaultConfigTests(unittest.TestCase):
    def test_rejects_invalid_values(self):
        with self.assertRaises(ValueError): SensorFaultConfig(noise_std=-0.1)
        with self.assertRaises(ValueError): SensorFaultConfig(dropout_rate=1.1)
        with self.assertRaises(ValueError): SensorFaultConfig(offline_after_tick=-1)


class SimulationSensorSourceTests(unittest.TestCase):
    def setUp(self): self.position = Position(4, 7)
    def test_no_noise_returns_exact_ground_truth_position(self):
        telemetry = SimulationSensorSource(lambda _robot_id: self.position).read("R1", 12)
        self.assertEqual(Position(4, 7), telemetry.position); self.assertEqual("OK", telemetry.sensorHealth); self.assertEqual(100.0, telemetry.battery); self.assertFalse(telemetry.obstacleDetected); self.assertEqual(12, telemetry.tick)
    def test_dropout_becomes_offline_at_heartbeat_threshold(self):
        source = SimulationSensorSource(lambda _robot_id: self.position, SensorFaultConfig(dropout_rate=1.0), miss_threshold=3)
        self.assertIsNone(source.read("R1", 0)); self.assertIsNone(source.read("R1", 1)); telemetry = source.read("R1", 2)
        self.assertEqual("OFFLINE", telemetry.sensorHealth); self.assertTrue(source.heartbeat_monitor.is_offline("R1"))
    def test_offline_after_tick_emits_offline_telemetry(self):
        source = SimulationSensorSource(lambda _robot_id: self.position, SensorFaultConfig(offline_after_tick=4))
        self.assertEqual("OK", source.read("R1", 3).sensorHealth); self.assertEqual("OFFLINE", source.read("R1", 4).sensorHealth)
    def test_noise_marks_reading_degraded_and_keeps_grid_positions(self):
        telemetry = SimulationSensorSource(lambda _robot_id: self.position, SensorFaultConfig(noise_std=0.5), rng=random.Random(7)).read("R1", 0)
        self.assertEqual("DEGRADED", telemetry.sensorHealth); self.assertIsInstance(telemetry.position.x, int); self.assertIsInstance(telemetry.position.y, int)
    def test_sustained_noise_alone_never_drives_robot_offline(self):
        """Regression test for the noise/dropout conflation bug: noise_std>0
        with no dropout_rate and no offline_after_tick must never accumulate
        into an OFFLINE status, however many ticks are read."""
        source = SimulationSensorSource(lambda _robot_id: self.position, SensorFaultConfig(noise_std=1.0), miss_threshold=3, rng=random.Random(1))
        for tick in range(20):
            telemetry = source.read("R1", tick)
            self.assertIsNotNone(telemetry)
            self.assertEqual("DEGRADED", telemetry.sensorHealth)
        self.assertFalse(source.heartbeat_monitor.is_offline("R1"))


class HeartbeatMonitorTests(unittest.TestCase):
    def test_flips_offline_exactly_at_threshold_and_recovers_on_ok_reading(self):
        monitor = HeartbeatMonitor(3); ok = Telemetry("R1", Position(0, 0), 100.0, False, "OK", 3)
        monitor.record("R1", None); monitor.record("R1", None); self.assertFalse(monitor.is_offline("R1")); monitor.record("R1", None); self.assertTrue(monitor.is_offline("R1")); monitor.record("R1", ok); self.assertFalse(monitor.is_offline("R1"))
    def test_degraded_reading_does_not_count_as_a_miss_and_resets_streak(self):
        """noise != dropout: a present-but-noisy (DEGRADED) reading is a
        received heartbeat, not a missed one — it must not accumulate toward
        OFFLINE, and must reset any prior miss streak exactly like an OK
        reading."""
        monitor = HeartbeatMonitor(3)
        degraded = Telemetry("R1", Position(0, 0), 100.0, False, "DEGRADED", 0)
        monitor.record("R1", None); monitor.record("R1", None)
        monitor.record("R1", degraded)  # resets the streak — not a miss
        self.assertFalse(monitor.is_offline("R1"))
        monitor.record("R1", None); monitor.record("R1", None)
        self.assertFalse(monitor.is_offline("R1"))  # only 2 consecutive real misses since the reset
    def test_offline_reading_still_counts_as_a_miss(self):
        monitor = HeartbeatMonitor(2)
        offline = Telemetry("R1", Position(0, 0), 100.0, False, "OFFLINE", 0)
        monitor.record("R1", offline); monitor.record("R1", offline)
        self.assertTrue(monitor.is_offline("R1"))
    def test_rejects_zero_threshold(self):
        with self.assertRaises(ValueError): HeartbeatMonitor(0)
