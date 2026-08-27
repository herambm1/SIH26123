// dashboard/src/api/mock.ts
// Owner: Member 4
//
// Mock data source — schema-identical to real contracts, but returns static fixture data.
// Build every component against this first. Replace with client.ts at integration time
// by swapping the import in App.tsx only — components never change.
//
// NOTE: Fixture data is intentionally minimal for scaffolding.
// Member 4 should flesh this out with realistic fake scenarios.

import type {
  RobotState,
  Task,
  WarehouseMap,
  PerformanceMetric,
  LiveWsMessage,
} from '../types/contracts';

export const mockRobots: RobotState[] = [];
export const mockTasks: Task[] = [];
export const mockWarehouseMap: WarehouseMap | null = null;
export const mockMetrics: PerformanceMetric[] = [];

// TODO: Member 4 — populate with realistic fixture data that exercises all UI states,
// including OFFLINE robots, REASSIGNED tasks, conflict events, and a full PerformanceMetric
// comparison across all three modes.
