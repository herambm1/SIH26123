# 00 — Shared Contracts (Canonical Reference)

**Version: v2 — synced with `SIH_26123_Project_Overview.md` v2, 2026-08-27**

## The actual source of truth is code, not this file

For the five Python modules (`planner/`, `robot_agent/`, `collision_engine/`, `edge/`, `simulation/`), the real canonical contracts are **`shared/python/models.py`** — one importable module, used by every Python module. Don't copy these definitions into your own module's code; `import` them.

```python
from shared.python.models import (
    Position, RobotState, RobotPath, Task, TaskAssignment,
    Conflict, WarehouseMap, Telemetry, SimulationEvent, PerformanceMetric,
)
```

Java (`backend/`) and TypeScript (`dashboard/`) can't import Python code, so they carry mirrored DTOs/interfaces — see "Cross-language mirrors" below. **If any mirror ever disagrees with `shared/python/models.py`, the Python file wins** (it's the one that actually runs) — flag the mismatch to the team immediately.

---

## Field reference (mirrors `shared/python/models.py` exactly)

```text
Position       { x: int, y: int, tick: int|null }
                 # tick set on RobotPath waypoints only

RobotState     { robotId: str, position: Position, velocity: float, battery: float,
                 currentTaskId: str|null, destination: Position|null,
                 currentPath: [Position], status: str, timestamp: int }
                 status ∈ {IDLE, MOVING, WAITING, BLOCKED, CHARGING, OFFLINE}

RobotPath      { robotId: str, waypoints: [Position], generatedAtTick: int, version: int }

Task           { taskId: str, pickupPosition: Position, dropPosition: Position,
                 priority: int, status: str, createdAtTick: int }
                 status ∈ {PENDING, ASSIGNED, IN_PROGRESS, COMPLETED, REASSIGNED, FAILED}

TaskAssignment { taskId: str, robotId: str, assignedAtTick: int,
                 estimatedCompletionTick: int|null }

Conflict       { conflictId: str, robotIds: [str], type: str, predictedCell: Position,
                 predictedTick: int, severity: str, resolutionAction: str|null }
                 type ∈ {SAME_CELL, CROSSING, NARROW_AISLE_HEADON}
                 resolutionAction ∈ {CONTINUE, WAIT, YIELD, REROUTE, REASSIGN_TASK}

WarehouseMap   { gridWidth: int, gridHeight: int, obstacles: [Position],
                 chokePoints: [Position], pickupPoints: [Position],
                 dropPoints: [Position], blockedCells: [Position] }

Telemetry      { robotId: str, position: Position, battery: float,
                 obstacleDetected: bool, sensorHealth: str, tick: int }
                 sensorHealth ∈ {OK, DEGRADED, OFFLINE}

SimulationEvent{ eventId: str, type: str, tick: int, payload: dict }
                 type ∈ {AISLE_BLOCKED, ROBOT_UNAVAILABLE, TASK_CREATED,
                          CONFLICT_DETECTED, DEADLOCK_DETECTED, REROUTE, TASK_REASSIGNED}

PerformanceMetric { runId: str, scenarioId: str, mode: str, totalCompletionTicks: int,
                     avgCompletionTicks: float, collisionCount: int, deadlockCount: int,
                     rerouteCount: int, idleTicksTotal: int, messageCount: int, seed: int }
                     mode ∈ {STOP_AND_WAIT, CENTRALIZED_RESERVATION, DECENTRALIZED_PROPOSED}
```

## Example payload (RobotState, as it crosses the Python→Java boundary as JSON)

```json
{
  "robotId": "R1",
  "position": {"x": 5, "y": 8, "tick": null},
  "velocity": 1.0,
  "battery": 82.0,
  "currentTaskId": "T12",
  "destination": {"x": 15, "y": 8, "tick": null},
  "currentPath": [{"x": 6, "y": 8, "tick": 101}, {"x": 7, "y": 8, "tick": 102}],
  "status": "MOVING",
  "timestamp": 100
}
```

## Producer / Consumer Map

| Contract | Produced by | Consumed by |
|---|---|---|
| `WarehouseMap` | Member 1 (`planner/warehouse_map.py`, instantiated in `simulation/warehouse/demo_map.py`) | Everyone |
| `RobotPath` | Member 1 (`planner/astar.py`) | Member 3 (collision_engine, agent.py), Member 2 (broadcast) |
| `RobotState` | Member 3 (`robot_agent/agent.py`, assembled each tick) | Member 2, Member 6 (ingestion), Member 4 (via backend) |
| `Task` / `TaskAssignment` | Member 6 (backend) | Robot Agent (via Java REST → Python control server payload) |
| `Conflict` | Member 3 (`collision_engine/detection.py`) | Member 3 itself (`resolution.py`), logged as `SimulationEvent` |
| `Telemetry` | Member 5 (`edge/sensor_source.py`) | Member 3 (agent.py), Member 6 (ingestion) |
| `SimulationEvent` | Members 3, 5, 6 (depending on type) | Member 4 (alerts), Member 6 (persistence) |
| `PerformanceMetric` | Member 3's `simulation/runner.py` | Member 6 (storage), Member 4 (dashboard) |

## Cross-language mirrors

- **Java** (`backend/src/main/java/com/sih26123/backend/model/`): one DTO class per contract above, same field names, standard Java types. Owner: Member 6.
- **TypeScript** (`dashboard/src/types/contracts.ts`): one interface per contract above. Owner: Member 4.

Both are generated once from this document and `shared/python/models.py`, then maintained manually. If keeping three copies in sync becomes painful, code-generating the Java/TS versions from the Python dataclasses is a reasonable Phase 5+ improvement — not required for the MVP.

## Change process

Frozen contracts (`Position`, `RobotState`, `RobotPath`, `Task`, `TaskAssignment`, `Conflict`, `WarehouseMap`): changing a field requires a quick team sync — edit `shared/python/models.py` first, then this doc, then ping whoever owns the Java/TS mirrors.

Evolvable contracts (`Telemetry`, `SimulationEvent`, `PerformanceMetric`): the listed owner can extend directly but should announce new fields in the team channel.
