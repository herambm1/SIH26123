// dashboard/src/api/client.ts
// Owner: Member 4
//
// Real API client — talks to the Java backend only (never directly to the
// Python sim engine, per the project's frozen architecture). Swap
// mock.ts -> client.ts by changing the import in App.tsx only.

import type {
  RobotState,
  Task,
  WarehouseMap,
  PerformanceMetric,
  LiveWsMessage,
  SimulationMode,
  SimulationSpeed,
  SimulationControlAck,
  SimulationStatus,
  ApiError,
  SimulationEvent,
} from '../types/contracts';

const BASE_URL = 'http://localhost:8080';
const WS_URL = 'ws://localhost:8080/ws/live';

export class ApiRequestError extends Error {
  status: number;
  apiError: ApiError | null;
  constructor(status: number, apiError: ApiError | null, message: string) {
    super(message);
    this.status = status;
    this.apiError = apiError;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
      ...init,
    });
  } catch (e) {
    throw new ApiRequestError(0, null, `Backend unreachable at ${BASE_URL}: ${(e as Error).message}`);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  const text = await res.text();
  const body = text ? JSON.parse(text) : null;

  if (!res.ok) {
    const apiError = body as ApiError | null;
    throw new ApiRequestError(res.status, apiError, apiError?.message ?? `Request failed with status ${res.status}`);
  }
  return body as T;
}

/** GET /api/robots -> list of latest RobotState */
export async function fetchRobots(): Promise<RobotState[]> {
  return request<RobotState[]>('/api/robots');
}

/** GET /api/robots/{id} -> single RobotState, or null if unknown */
export async function fetchRobot(id: string): Promise<RobotState | null> {
  try {
    return await request<RobotState>(`/api/robots/${encodeURIComponent(id)}`);
  } catch (e) {
    if (e instanceof ApiRequestError && e.status === 404) return null;
    throw e;
  }
}

/** GET /api/tasks -> list of Task */
export async function fetchTasks(): Promise<Task[]> {
  return request<Task[]>('/api/tasks');
}

/**
 * GET /api/warehouse -> WarehouseMap, or null if no run has pushed one yet
 * (backend returns 503 WAREHOUSE_MAP_UNAVAILABLE — a real, expected empty
 * state before any simulation has started, not an error to hide/retry-loop).
 */
export async function fetchWarehouseMap(): Promise<WarehouseMap | null> {
  try {
    return await request<WarehouseMap>('/api/warehouse');
  } catch (e) {
    if (e instanceof ApiRequestError && e.status === 503) return null;
    throw e;
  }
}

/** GET /api/metrics?scenarioId= -> list of PerformanceMetric (only metrics
 * POSTed by live runs during this backend session — NOT the finalized
 * offline benchmark artifact, see src/data/benchmarkArtifact.ts for that). */
export async function fetchMetrics(scenarioId?: string): Promise<PerformanceMetric[]> {
  const qs = scenarioId ? `?scenarioId=${encodeURIComponent(scenarioId)}` : '';
  return request<PerformanceMetric[]>(`/api/metrics${qs}`);
}

/**
 * GET /api/events?type=&limit= — approved read-only addition "b-1" (Phase 5).
 * IMPORTANT: EventEntity carries no scenarioId/runId (confirmed during the
 * Phase 1 audit), so this is NOT scoped to "the current run" — it returns
 * everything the backend has ever persisted, optionally filtered by type.
 * Callers must treat it as a supplementary full log, not per-run history;
 * the live-buffered events from /ws/live (already correctly scoped to the
 * current run via useLiveFeed's runGeneration reset) are the primary source
 * for "what happened in this run".
 */
export async function fetchEvents(params?: { type?: string; limit?: number }): Promise<SimulationEvent[]> {
  const qs = new URLSearchParams();
  if (params?.type) qs.set('type', params.type);
  if (params?.limit) qs.set('limit', String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return request<SimulationEvent[]>(`/api/events${suffix}`);
}

/** POST /api/simulation/control {action: "start", ...} */
export async function startSimulation(params: {
  scenarioId: string;
  mode: SimulationMode;
  seed: number;
  speed: SimulationSpeed;
}): Promise<SimulationControlAck> {
  return request<SimulationControlAck>('/api/simulation/control', {
    method: 'POST',
    body: JSON.stringify({ action: 'start', ...params }),
  });
}

/** POST /api/simulation/control {action: "stop"} */
export async function stopSimulation(): Promise<SimulationControlAck> {
  return request<SimulationControlAck>('/api/simulation/control', {
    method: 'POST',
    body: JSON.stringify({ action: 'stop' }),
  });
}

/** GET /api/simulation/status -> proxied Python /control/status */
export async function fetchSimulationStatus(): Promise<SimulationStatus> {
  return request<SimulationStatus>('/api/simulation/status');
}

/**
 * Connect to /ws/live. Returns the raw WebSocket so the caller (useLiveFeed)
 * owns the lifecycle (reconnect/backoff/cleanup) — this function only
 * performs the real connection + typed message parsing, per
 * docs/00_SHARED_CONTRACTS.md's LiveWsMessage envelope.
 */
export function connectLiveFeed(
  onMessage: (msg: LiveWsMessage) => void,
  onOpen?: () => void,
  onClose?: (ev: CloseEvent) => void,
  onError?: (ev: Event) => void,
): WebSocket {
  const ws = new WebSocket(WS_URL);
  ws.onopen = () => onOpen?.();
  ws.onclose = (ev) => onClose?.(ev);
  ws.onerror = (ev) => onError?.(ev);
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data) as LiveWsMessage;
      onMessage(msg);
    } catch {
      // A malformed frame must never crash the live view — drop it.
    }
  };
  return ws;
}
