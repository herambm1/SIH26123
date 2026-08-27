# 05 — ECE / Edge — Implementation Specification
**Member 5 · Synced with `SIH_26123_Project_Overview.md` v2 · Canonical contracts: `docs/00_SHARED_CONTRACTS.md` / `shared/python/models.py`**

---

## 1. Module Purpose

You build sensor/telemetry abstraction and — the substantial part — a **fault-injection framework** that makes the deadlock-recovery and task-reassignment demo scenarios genuinely testable. The category is Software; the core system runs with zero physical hardware. "Edge-AI" in the problem title doesn't require an on-device neural net — decentralized, local decision-making on each robot already qualifies as edge intelligence.

## 2. System Context

```text
React Dashboard ──REST/WS──▶ Java Backend ◄──REST(telemetry push)── Python Sim Engine
                                                                              │
Inside the Python Sim Engine, per tick, per robot:
  [ YOU: Edge/SensorSource ] → RobotAgent.tick() (Member 3) → RobotState.status
```

## 3. Your Place in the Architecture

```text
Sensor / Simulation Telemetry
          ↓
   SensorSource.read() (you, includes fault injection)
          ↓
     Telemetry → folded into RobotState by RobotAgent.tick() (Member 3)
          ↓
   Backend ingestion → Dashboard alerts / task-reassignment trigger
```

## 4. What You Own

```text
edge/sensor_source.py      — SensorSource ABC, SimulationSensorSource
edge/fault_injection.py    — SensorFaultConfig
edge/heartbeat.py          — missed-heartbeat → OFFLINE logic
edge/hardware/             — optional Raspberry Pi/ESP32 HardwareSensorSource, isolated
edge/tests/
```

## 5. Reads / Consumes

Nothing from other modules to start (you're a source). Later: which `SensorFaultConfig` profile a given scenario wants (from Member 3's scenario definitions, passed in at construction time).

## 6. Produces

`Telemetry`, read by `RobotAgent.tick()` (Member 3) every tick, and reported onward (via Member 3's runner) to the Java backend for dashboard alerts and task-reassignment triggers.

## 7. Must Not Modify

`robot_agent/agent.py`, `collision_engine/`, `planner/`, `robot_agent/communication/`, `backend/`, `dashboard/`.

## 8. Complete Responsibilities & Implementation Requirements

**8.1 `SensorSource` interface and default implementation.** `SimulationSensorSource` produces synthetic position/battery/obstacle readings derived from the ground-truth simulation state (it's not literally random — it should reflect what the robot "actually" is doing, then apply configured noise on top).

**8.2 Fault injection — the real deliverable of this role.** `SensorFaultConfig`: `noise_std` (Gaussian position jitter), `dropout_rate` (probability a reading is simply missing this tick), `offline_after_tick` (optional: the robot goes fully dark after a given tick, for testing task reassignment). This isn't decoration — it's what makes the deadlock-recovery and reassignment scenarios meaningful to run, and it's real, substantial software engineering ownership on its own.

**8.3 Heartbeat / health-check.** Track consecutive missed/degraded readings per robot; after a configurable threshold, mark `sensorHealth = OFFLINE` in the `Telemetry` and let `RobotAgent.tick()` (Member 3) propagate that into `RobotState.status = OFFLINE`, which is what should trigger backend-side task reassignment.

**8.4 Explicitly not your job.** Robot chassis, motor control/actuation, SLAM, computer vision. Don't attach hardware just to have something physical — §8.2 above is substantial, real ownership on its own.

**8.5 Optional: hardware bonus.** `HardwareSensorSource`, behind the identical `SensorSource` interface, reading one real sensor (e.g. an ultrasonic distance sensor on an ESP32/Raspberry Pi) and mapping it into a `Telemetry` reading. Isolated in `edge/hardware/`, never imported by the default simulation path — its absence or failure cannot affect the core demo.

## 9. Exact Interfaces

```python
# edge/sensor_source.py
from abc import ABC, abstractmethod

class SensorSource(ABC):
    @abstractmethod
    def read(self, robot_id: str, current_tick: int) -> Telemetry: ...

class SimulationSensorSource(SensorSource):
    def __init__(self, ground_truth_provider, fault_config: "SensorFaultConfig | None" = None):
        """ground_truth_provider: a callable robot_id -> Position giving the
        'real' simulated position this tick, before noise is applied."""

# edge/fault_injection.py
class SensorFaultConfig:
    def __init__(self, noise_std: float = 0.0, dropout_rate: float = 0.0,
                 offline_after_tick: int | None = None): ...

# edge/heartbeat.py
class HeartbeatMonitor:
    def __init__(self, miss_threshold: int = 3): ...
    def record(self, robot_id: str, telemetry: Telemetry | None) -> None:
        """telemetry=None means a dropped/missing reading this tick."""
    def is_offline(self, robot_id: str) -> bool: ...
```

## 10. How My Module Affects Other Modules

```text
ECE / Edge
    ↓
Telemetry → RobotAgent.tick() (Member 3): folded into RobotState every tick
    ↓
sensorHealth=OFFLINE / HeartbeatMonitor.is_offline() → RobotState.status=OFFLINE
    → SimulationEvent(ROBOT_UNAVAILABLE) → Backend → triggers task reassignment
    → Dashboard: alert + robot rendered distinctly
```

## 11. How Other Modules Affect My Module

```text
Ground-truth robot position (from the simulation state each tick)
    → the input your SimulationSensorSource perturbs with noise/dropout
Scenario fault-injection profile (Member 3's scenario definitions)
    → which SensorFaultConfig to construct for a given demo scenario
```

## 12. Integration Points

| My Module | Other Module | Data/Interface | Direction | Purpose |
|---|---|---|---|---|
| Edge | Robot Agent | `Telemetry` | Edge → Robot Agent | Sensor/state updates each tick |
| Edge | Robot Agent | `sensorHealth`/offline signal | Edge → Robot Agent | Triggers `RobotState.status=OFFLINE` |
| Scenarios | Edge | `SensorFaultConfig` | Scenarios → Edge | Per-scenario fault profile |

## 13. Failure / Missing-Dependency Behavior

- **No ground-truth provider wired yet** (Robot Agent not built): test standalone with a fabricated callable returning a fixed `Position`.
- **`read()` itself "fails"** (i.e., dropout triggers): don't raise an exception — return `None` or a `Telemetry` with `sensorHealth=OFFLINE`/stale flag; this is expected, modeled behavior, not an error condition for the caller to handle defensively.
- **Hardware source unavailable**: `HardwareSensorSource` failing to connect must never affect `SimulationSensorSource` — they're fully independent implementations of the same interface.

## 14. Mock-First Development

| Real dependency | Mock while developing | Integration replacement |
|---|---|---|
| Real ground-truth position from the simulation | A fabricated callable returning a fixed/incrementing `Position` | Swap the `ground_truth_provider` argument only |
| Real scenario fault profiles | Manually construct `SensorFaultConfig` in a test | Same constructor, different config source |

You need nothing from anyone else to build and fully test this module — it can be developed and demonstrated entirely standalone.

## 15. Testing Strategy

- `SimulationSensorSource` with `noise_std=0` returns exactly the ground-truth position; with `dropout_rate=1.0` always returns a missing/degraded reading.
- `HeartbeatMonitor`: feed a sequence of missed readings, confirm `is_offline()` flips true exactly at `miss_threshold`.
- Standalone run: `python -m edge.sensor_source` printing fake telemetry at 1Hz to console — no other module needed.

## 16. AI Coding Boundary

> You own `edge/`. Do not modify `robot_agent/agent.py`, `collision_engine/`, `planner/`, `robot_agent/communication/`, `backend/`, or `dashboard/`. Import contracts from `shared/python/models.py`; you may extend `Telemetry` with new fields but announce it to the team rather than assuming consumers will notice. Keep all hardware-specific code isolated in `edge/hardware/`, never imported by the default simulation path. Inspect existing code before modifying. Show diffs. Write tests, especially for the fault-injection modes. Don't restructure the repository.

## 17. Definition of Done

- `SimulationSensorSource` reliably emits `Telemetry` matching the contract, with configurable noise/dropout, tested.
- `HeartbeatMonitor` correctly flips offline status at the configured threshold, tested.
- At least the deadlock and task-reassignment demo scenarios are wired to a real `SensorFaultConfig` profile.
- (Optional) hardware sensor source works in isolation behind the same interface, and its absence changes nothing about the core system's behavior.
