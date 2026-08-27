// dashboard/src/types/contracts.ts
// Owner: Member 4
// Source of truth: docs/00_SHARED_CONTRACTS.md / shared/python/models.py
//
// These are REAL type declarations, not stubs. They mirror the Python contracts
// exactly. If any backend response disagrees with these interfaces, that is a
// bug to report — not something to silently adapt around.

/**
 * A grid cell. tick is set on RobotPath waypoints (space-time); null on
 * current-position snapshots inside RobotState.
 */
export interface Position {
  x: number;
  y: number;
  tick?: number | null;
}

/**
 * status ∈ {IDLE, MOVING, WAITING, BLOCKED, CHARGING, OFFLINE}
 * OFFLINE must be rendered visually unmistakable — it's a key demo moment.
 */
export interface RobotState {
  robotId: string;
  position: Position;
  velocity: number;
  battery: number;
  currentTaskId: string | null;
  destination: Position | null;
  currentPath: Position[];
  status: 'IDLE' | 'MOVING' | 'WAITING' | 'BLOCKED' | 'CHARGING' | 'OFFLINE';
  timestamp: number;
}

/**
 * status ∈ {PENDING, ASSIGNED, IN_PROGRESS, COMPLETED, REASSIGNED, FAILED}
 */
export interface Task {
  taskId: string;
  pickupPosition: Position;
  dropPosition: Position;
  priority: number;
  status: 'PENDING' | 'ASSIGNED' | 'IN_PROGRESS' | 'COMPLETED' | 'REASSIGNED' | 'FAILED';
  createdAtTick: number;
}

export interface TaskAssignment {
  taskId: string;
  robotId: string;
  assignedAtTick: number;
  estimatedCompletionTick: number | null;
}

/**
 * type ∈ {SAME_CELL, CROSSING, NARROW_AISLE_HEADON}
 * resolutionAction ∈ {CONTINUE, WAIT, YIELD, REROUTE, REASSIGN_TASK}
 */
export interface Conflict {
  conflictId: string;
  robotIds: string[];
  type: 'SAME_CELL' | 'CROSSING' | 'NARROW_AISLE_HEADON';
  predictedCell: Position;
  predictedTick: number;
  severity: 'LOW' | 'MEDIUM' | 'HIGH';
  resolutionAction: 'CONTINUE' | 'WAIT' | 'YIELD' | 'REROUTE' | 'REASSIGN_TASK' | null;
}

export interface WarehouseMap {
  gridWidth: number;
  gridHeight: number;
  obstacles: Position[];
  chokePoints: Position[];
  pickupPoints: Position[];
  dropPoints: Position[];
  blockedCells: Position[];
}

/**
 * sensorHealth ∈ {OK, DEGRADED, OFFLINE}
 */
export interface Telemetry {
  robotId: string;
  position: Position;
  battery: number;
  obstacleDetected: boolean;
  sensorHealth: 'OK' | 'DEGRADED' | 'OFFLINE';
  tick: number;
}

/**
 * type ∈ {AISLE_BLOCKED, ROBOT_UNAVAILABLE, TASK_CREATED, CONFLICT_DETECTED,
 *          DEADLOCK_DETECTED, REROUTE, TASK_REASSIGNED}
 */
export interface SimulationEvent {
  eventId: string;
  type: string;
  tick: number;
  payload: Record<string, unknown>;
}

/**
 * mode ∈ {STOP_AND_WAIT, CENTRALIZED_RESERVATION, DECENTRALIZED_PROPOSED}
 * collisionCount comes from the independent referee — never ConflictDetector's count.
 */
export interface PerformanceMetric {
  runId: string;
  scenarioId: string;
  mode: 'STOP_AND_WAIT' | 'CENTRALIZED_RESERVATION' | 'DECENTRALIZED_PROPOSED';
  totalCompletionTicks: number;
  avgCompletionTicks: number;
  collisionCount: number;
  deadlockCount: number;
  rerouteCount: number;
  idleTicksTotal: number;
  messageCount: number;
  seed: number;
}

// ── WebSocket live-update envelope ───────────────────────────────────────────
// Matches backend's LiveUpdateBroadcaster — see docs/06_BACKEND.md §8.5

export type LiveWsMessage =
  | { type: 'ROBOT_STATE_BATCH'; tick: number; payload: RobotState[] }
  | { type: 'SIMULATION_EVENT'; tick: number; payload: SimulationEvent }
  | { type: 'METRIC_UPDATE'; tick: number; payload: PerformanceMetric };
