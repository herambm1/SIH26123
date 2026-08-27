// dashboard/src/api/client.ts
// Owner: Member 4
//
// Real API client — talks to Java backend only (never directly to Python sim engine).
// Swap mock.ts → client.ts by changing the import in App.tsx only.
// All function signatures are per docs/04_FRONTEND.md §9.

import type {
  RobotState,
  Task,
  WarehouseMap,
  PerformanceMetric,
  LiveWsMessage,
} from '../types/contracts';

const BASE_URL = 'http://localhost:8080';
const WS_URL = 'ws://localhost:8080/ws/live';

/** GET /api/robots → list of latest RobotState */
export async function fetchRobots(): Promise<RobotState[]> {
  throw new Error('Not implemented — Member 4 implementation responsibility');
}

/** GET /api/tasks → list of Task */
export async function fetchTasks(): Promise<Task[]> {
  throw new Error('Not implemented — Member 4 implementation responsibility');
}

/** GET /api/warehouse → WarehouseMap */
export async function fetchWarehouseMap(): Promise<WarehouseMap> {
  throw new Error('Not implemented — Member 4 implementation responsibility');
}

/** GET /api/metrics?scenarioId= → list of PerformanceMetric */
export async function fetchMetrics(scenarioId: string): Promise<PerformanceMetric[]> {
  throw new Error('Not implemented — Member 4 implementation responsibility');
}

/** Connect to /ws/live WebSocket feed */
export function connectLiveFeed(onMessage: (msg: LiveWsMessage) => void): WebSocket {
  throw new Error('Not implemented — Member 4 implementation responsibility');
}
