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
 *          DEADLOCK_DETECTED, REROUTE, TASK_REASSIGNED, NEGOTIATION}
 *
 * NEGOTIATION (Phase 5, approved addition "b-2"): observability only,
 * emitted by simulation/runner.py from real RobotAgent/ConflictResolver
 * attributes already computed inside agent.tick() — never a new decision,
 * DECENTRALIZED_PROPOSED mode only (the baselines never run
 * ConflictDetector/ConflictResolver, so there is nothing to observe for
 * them). Fires only on a genuine change from the robot's previously
 * recorded action. payload shape: NegotiationEventPayload below.
 *
 * NOTE: only DEADLOCK_DETECTED and REROUTE are listed in the frozen
 * contract's type set but are NEVER actually constructed anywhere in the
 * current codebase (confirmed by source inspection, Phase 1 audit) — a
 * timeline showing these types will legitimately never see one; that is
 * real absence, not a frontend gap.
 */
export interface SimulationEvent {
  eventId: string;
  type: string;
  tick: number;
  payload: Record<string, unknown>;
}

/** Real payload shape of a NEGOTIATION event — see SimulationEvent above. */
export interface NegotiationEventPayload {
  robotId: string;
  peerRobotId: string | null;
  resolutionAction: 'CONTINUE' | 'WAIT' | 'YIELD' | 'REROUTE' | 'REASSIGN_TASK';
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

// ── Simulation control (mirrors SimulationControlController / SimulationClient) ──
// NOT a shared/python/models.py contract — SimulationRunner.run()'s actual
// parameters and Python's GET /control/status response shape, inspected
// directly (see CLAUDE.md / Phase 1 audit), same status as
// backend's SimulationStatusDto.

export type SimulationMode = 'STOP_AND_WAIT' | 'CENTRALIZED_RESERVATION' | 'DECENTRALIZED_PROPOSED';
export type SimulationSpeed = 'BATCH' | 'LIVE';

export interface SimulationControlStartRequest {
  action: 'start';
  scenarioId: string;
  mode: SimulationMode;
  seed: number;
  speed: SimulationSpeed;
}

export interface SimulationControlStopRequest {
  action: 'stop';
}

export interface SimulationControlAck {
  message: string;
  runId?: string;
  scenarioId?: string;
  mode?: string;
  seed?: number;
  speed?: string;
}

/** GET /api/simulation/status → Python's real /control/status shape, proxied verbatim. */
export interface SimulationStatus {
  running: boolean;
  currentTick: number;
  scenarioId: string | null;
  mode: string;
}

/** Mirrors ApiErrorDto — the uniform error body on every non-2xx backend response. */
export interface ApiError {
  error: string;
  message: string;
  timestamp?: string;
}
