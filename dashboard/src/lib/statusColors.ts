// dashboard/src/lib/statusColors.ts
// Owner: Member 4
//
// Single source of truth for status -> color mapping. Every component that
// renders a robot status (map markers, inspector, event timeline, benchmark
// completion cells) imports from here — never redefines a color inline.
// Values are CSS custom properties defined in styles/theme.css.

import type { RobotState } from '../types/contracts';

export type DisplayStatus = RobotState['status'] | 'YIELD' | 'COMPLETED' | 'TIMEOUT';

export const STATUS_COLOR_VAR: Record<DisplayStatus, string> = {
  IDLE: 'var(--status-idle)',
  MOVING: 'var(--status-moving)',
  WAITING: 'var(--status-waiting)',
  BLOCKED: 'var(--status-blocked)',
  CHARGING: 'var(--status-charging)',
  OFFLINE: 'var(--status-offline)',
  // Derived states — never a raw RobotState.status value:
  // YIELD comes from a Conflict.resolutionAction, COMPLETED/TIMEOUT from
  // run-completion bookkeeping (PerformanceMetric / benchmark artifact).
  YIELD: 'var(--status-yield)',
  COMPLETED: 'var(--status-completed)',
  TIMEOUT: 'var(--status-timeout)',
};

export const STATUS_LABEL: Record<DisplayStatus, string> = {
  IDLE: 'IDLE',
  MOVING: 'MOVING',
  WAITING: 'WAITING',
  BLOCKED: 'BLOCKED',
  CHARGING: 'CHARGING',
  OFFLINE: 'OFFLINE',
  YIELD: 'YIELD',
  COMPLETED: 'COMPLETED',
  TIMEOUT: 'TIMEOUT / NOT COMPLETED',
};

export function statusColor(status: DisplayStatus): string {
  return STATUS_COLOR_VAR[status] ?? 'var(--text-2)';
}
