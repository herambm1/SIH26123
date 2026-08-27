"""
shared/python/models.py — CANONICAL DATA CONTRACTS.

This is the single, real, importable source of truth for every data
structure shared between planner/, robot_agent/, collision_engine/,
edge/, and simulation/. Do not redefine any of these classes anywhere
else in the Python codebase — import them from here.

Frozen at Phase 0 (changing a field requires a team sync, not a solo PR):
    Position, RobotState, RobotPath, Task, TaskAssignment, Conflict, WarehouseMap

Evolvable after Phase 0 (owner may extend, should still announce it):
    Telemetry (Member 5), SimulationEvent (Member 3/6), PerformanceMetric (Member 6)

The Java backend and the TypeScript dashboard cannot import this file directly
(different languages) — they carry their own mirrored copies. If this file
and docs/00_SHARED_CONTRACTS.md ever disagree, this file (the code that
actually runs) is what's true; fix the doc to match, not the other way round.
"""

from dataclasses import dataclass, field
from typing import Optional


# ── Frozen contracts ─────────────────────────────────────────────────────

@dataclass
class Position:
    """A grid cell. tick is set on RobotPath waypoints (space-time), absent
    on 'current position' snapshots inside RobotState."""
    x: int
    y: int
    tick: Optional[int] = None


@dataclass
class RobotState:
    """Producer: RobotAgent.tick(), assembled fresh every tick from Edge +
    Planner + Coordination outputs. Consumers: robot_agent/communication
    (builds intent messages), backend (ingestion), collision_engine
    (own + peer states)."""
    robotId: str
    position: Position
    velocity: float                       # cells/tick; 0 or 1 in the MVP
    battery: float                        # 0-100
    currentTaskId: Optional[str]
    destination: Optional[Position]
    currentPath: list                     # list[Position], remaining waypoints
    status: str                           # IDLE|MOVING|WAITING|BLOCKED|CHARGING|OFFLINE
    timestamp: int                        # simulation tick of this snapshot


@dataclass
class RobotPath:
    """Producer: Planner.plan(). Consumers: collision_engine (conflict
    prediction), RobotAgent (movement), communication (broadcast as
    intent), simulation runner (actually moves the robot)."""
    robotId: str
    waypoints: list                       # list[Position], each with .tick set
    generatedAtTick: int
    version: int                          # increments every replan


@dataclass
class Task:
    """Producer: Backend. Consumers: RobotAgent (via TaskAssignment),
    Planner (pickup/drop used as start/goal), Dashboard."""
    taskId: str
    pickupPosition: Position
    dropPosition: Position
    priority: int                         # 1 (low) .. 5 (high)
    status: str                           # PENDING|ASSIGNED|IN_PROGRESS|COMPLETED|REASSIGNED|FAILED
    createdAtTick: int


@dataclass
class TaskAssignment:
    """Producer: Backend's task allocator. Consumer: RobotAgent."""
    taskId: str
    robotId: str
    assignedAtTick: int
    estimatedCompletionTick: Optional[int] = None


@dataclass
class Conflict:
    """Producer: collision_engine's ConflictDetector. Consumer:
    collision_engine's own ConflictResolver, then logged as a
    SimulationEvent for backend/dashboard."""
    conflictId: str
    robotIds: list                        # list[str], exactly 2 in the MVP
    type: str                             # SAME_CELL|CROSSING|NARROW_AISLE_HEADON
    predictedCell: Position
    predictedTick: int
    severity: str                         # LOW|MEDIUM|HIGH
    resolutionAction: Optional[str] = None  # CONTINUE|WAIT|YIELD|REROUTE|REASSIGN_TASK


@dataclass
class WarehouseMap:
    """Producer: Planner/simulation, loaded once at sim start. Consumer:
    everyone."""
    gridWidth: int
    gridHeight: int
    obstacles: list = field(default_factory=list)      # list[Position]
    chokePoints: list = field(default_factory=list)     # list[Position], deliberate — see 01_PATH_PLANNING.md
    pickupPoints: list = field(default_factory=list)    # list[Position]
    dropPoints: list = field(default_factory=list)      # list[Position]
    blockedCells: list = field(default_factory=list)    # list[Position], mutable at runtime


# ── Evolvable contracts ──────────────────────────────────────────────────

@dataclass
class Telemetry:
    """Producer: Edge's SensorSource. Consumer: RobotAgent (folds into
    RobotState), Backend (ingestion/dashboard alerts). Owner: Member 5,
    may extend — announce new fields to the team."""
    robotId: str
    position: Position
    battery: float
    obstacleDetected: bool
    sensorHealth: str                     # OK|DEGRADED|OFFLINE
    tick: int


@dataclass
class SimulationEvent:
    """Producer: collision_engine (conflict/deadlock/reroute), edge
    (robot unavailable), backend (task created/reassigned), simulation
    (aisle blocked). Consumer: Backend (persists/broadcasts), Dashboard
    (alerts feed)."""
    eventId: str
    type: str      # AISLE_BLOCKED|ROBOT_UNAVAILABLE|TASK_CREATED|CONFLICT_DETECTED
                   # |DEADLOCK_DETECTED|REROUTE|TASK_REASSIGNED
    tick: int
    payload: dict = field(default_factory=dict)   # type-specific


@dataclass
class PerformanceMetric:
    """Producer: simulation runner, pushed to Backend at end of a run.
    Consumer: Backend (storage), Dashboard (performance panel)."""
    runId: str
    scenarioId: str
    mode: str                              # STOP_AND_WAIT|CENTRALIZED_RESERVATION|DECENTRALIZED_PROPOSED
    totalCompletionTicks: int
    avgCompletionTicks: float
    collisionCount: int                    # from the independent referee — never the collision_engine's own count
    deadlockCount: int
    rerouteCount: int
    idleTicksTotal: int
    messageCount: int
    seed: int
