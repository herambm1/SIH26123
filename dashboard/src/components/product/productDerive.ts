// dashboard/src/components/product/productDerive.ts
//
// Pure derivations for the Product tab (no React, no fetching) so they can be unit-tested with plain `node --test` — see
// dashboard/tests/productDerive.test.ts. Everything here is computed from real data only: the ProductSessionStatus counters,
// the /ws/live robot frame, and the real SimulationEvents. Nothing is invented or interpolated.

import type { RobotState, SimulationEvent } from '../../types/contracts';
import type { ProductSessionStatus } from '../../types/product';

export type RosterStatus = RobotState['status'] | 'BROKEN_DOWN';

export interface ProductKpis {
  completed: number;
  /** Tasks pushed to a robot and not yet completed or abandoned. */
  active: number;
  /** Tasks created but not yet given to a robot. */
  pending: number;
  /** Tasks abandoned (stalled robot / stale robot). */
  abandoned: number;
  /** Robots currently negotiating: waiting/blocked AND their latest coordination verdict is not CONTINUE. */
  activeConflicts: number;
  /** Independent-referee collisions (CONFLICT_DETECTED events with collision=true), each counted once. */
  collisions: number;
  brokenDown: number;
}

const NEGOTIATING_ACTIONS = new Set(['WAIT', 'YIELD', 'REROUTE', 'REASSIGN_TASK']);

/** Latest NEGOTIATION verdict per robot (events are in arrival order; the last one for a robot wins). */
export function latestVerdictByRobot(events: SimulationEvent[]): Map<string, string> {
  const latest = new Map<string, { tick: number; action: string }>();
  for (const e of events) {
    if (e.type !== 'NEGOTIATION') continue;
    const robotId = String(e.payload.robotId ?? '');
    const action = String(e.payload.resolutionAction ?? '');
    if (!robotId || !action) continue;
    const prev = latest.get(robotId);
    if (!prev || e.tick >= prev.tick) latest.set(robotId, { tick: e.tick, action });
  }
  return new Map(Array.from(latest.entries()).map(([k, v]) => [k, v.action]));
}

export function isCollisionEvent(e: SimulationEvent): boolean {
  return e.type === 'CONFLICT_DETECTED' && e.payload.collision === true;
}

export function deriveKpis(status: ProductSessionStatus | null, events: SimulationEvent[], robots: RobotState[]): ProductKpis {
  const broken = new Set(status?.brokenDownRobots ?? []);
  const verdicts = latestVerdictByRobot(events);
  const activeConflicts = robots.filter(
    (r) =>
      !broken.has(r.robotId) &&
      (r.status === 'WAITING' || r.status === 'BLOCKED') &&
      NEGOTIATING_ACTIONS.has(verdicts.get(r.robotId) ?? ''),
  ).length;

  const created = status?.tasksCreated ?? 0;
  const completed = status?.tasksCompleted ?? 0;
  const abandoned = status?.tasksFailed ?? 0;
  const pending = status?.tasksPendingOrAssigned ?? 0;
  const inFlight = Math.max(0, created - completed - abandoned);

  return {
    completed,
    active: Math.max(0, inFlight - pending),
    pending,
    abandoned,
    activeConflicts,
    collisions: events.filter(isCollisionEvent).length,
    brokenDown: broken.size,
  };
}

export interface RosterRow {
  robotId: string;
  status: RosterStatus;
  /** The robot's own reported status (only differs from `status` for a broken-down robot). */
  reportedStatus: RobotState['status'];
  position: { x: number; y: number };
  taskId: string | null;
  destination: { x: number; y: number } | null;
  pathRemaining: number;
  verdict: string | null;
}

/** Roster rows sorted by robot id (numeric-aware). A latched broken-down robot shows BROKEN_DOWN whatever its flickering status says. */
export function deriveRoster(robots: RobotState[], brokenDown: string[], events: SimulationEvent[]): RosterRow[] {
  const broken = new Set(brokenDown);
  const verdicts = latestVerdictByRobot(events);
  return robots
    .slice()
    .sort((a, b) => a.robotId.localeCompare(b.robotId, undefined, { numeric: true }))
    .map((r) => ({
      robotId: r.robotId,
      status: broken.has(r.robotId) ? 'BROKEN_DOWN' : r.status,
      reportedStatus: r.status,
      position: { x: r.position.x, y: r.position.y },
      taskId: r.currentTaskId,
      destination: r.destination ? { x: r.destination.x, y: r.destination.y } : null,
      pathRemaining: r.currentPath?.length ?? 0,
      verdict: verdicts.get(r.robotId) ?? null,
    }));
}

/** Robots as the map should draw them: a broken-down robot is drawn OFFLINE (the existing, unmistakable OFFLINE marker). */
export function robotsForMap(robots: RobotState[], brokenDown: string[]): RobotState[] {
  if (brokenDown.length === 0) return robots;
  const broken = new Set(brokenDown);
  return robots.map((r) => (broken.has(r.robotId) && r.status !== 'OFFLINE' ? { ...r, status: 'OFFLINE' as const } : r));
}

// ── Event feed ───────────────────────────────────────────────────────────

export type FeedCategory = 'NEGOTIATION' | 'TASK' | 'FAULT' | 'COLLISION' | 'SYSTEM';
export type FeedFilter = 'ALL' | 'NEGOTIATION' | 'TASKS' | 'FAULTS' | 'COLLISIONS';

export interface FeedLine {
  eventId: string;
  tick: number;
  category: FeedCategory;
  /** CSS color (theme variable) for the left rule / label. */
  color: string;
  label: string;
  text: string;
}

const NEGOTIATION_COLOR: Record<string, string> = {
  CONTINUE: 'var(--ok)',
  WAIT: 'var(--status-waiting)',
  YIELD: 'var(--status-yield)',
  REROUTE: 'var(--accent)',
  REASSIGN_TASK: 'var(--status-offline)',
};

/** A cell as either {x,y} (most events) or [x,y] (Python serializes AISLE_BLOCKED's cell tuple as a JSON array). */
function cell(v: unknown): string {
  if (Array.isArray(v) && typeof v[0] === 'number' && typeof v[1] === 'number') return `(${v[0]},${v[1]})`;
  const c = v as { x?: number; y?: number } | null | undefined;
  return c && typeof c.x === 'number' && typeof c.y === 'number' ? `(${c.x},${c.y})` : '?';
}

/** Short task label: the trailing sequence of a task id (task_product_<session>_7 -> #7, x_57_3 -> #3). */
function shortTask(id: unknown): string {
  const s = String(id ?? '');
  const m = s.match(/_(\d+)$/);
  return m ? `#${m[1]}` : s;
}

/**
 * Turn one real SimulationEvent into a feed line, or null for event types that are too noisy or duplicate another line
 * (COMM_FLOW is emitted every tick; TASK_PUSHED_TO_ENGINE and a COMPLETED TASK_STATUS_CHANGED duplicate TASK_ASSIGNED /
 * TASK_COMPLETED, which Python emits first).
 */
export function describeEvent(e: SimulationEvent): FeedLine | null {
  const p = e.payload;
  const base = { eventId: e.eventId, tick: e.tick };
  switch (e.type) {
    case 'NEGOTIATION': {
      const action = String(p.resolutionAction ?? '');
      const peer = p.peerRobotId ? ` re ${p.peerRobotId}` : '';
      const where = p.contestedCell ? ` at ${cell(p.contestedCell)}` : '';
      const kind = p.conflictType ? ` [${String(p.conflictType).replace(/_/g, ' ').toLowerCase()}]` : '';
      return { ...base, category: 'NEGOTIATION', color: NEGOTIATION_COLOR[action] ?? 'var(--text-1)', label: action, text: `${p.robotId}${peer}${where}${kind}` };
    }
    case 'TASK_CREATED':
      return { ...base, category: 'TASK', color: 'var(--text-1)', label: 'TASK NEW', text: `${shortTask(p.taskId)} priority ${p.priority ?? '?'} -> drop ${cell(p.dropPosition)}` };
    case 'TASK_ASSIGNED':
      return { ...base, category: 'TASK', color: 'var(--accent)', label: 'ASSIGNED', text: `${shortTask(p.taskId)} -> ${p.robotId} drop ${cell(p.dropPosition)}` };
    case 'TASK_COMPLETED':
      return { ...base, category: 'TASK', color: 'var(--status-completed)', label: 'DONE', text: `${p.robotId} completed ${shortTask(p.taskId)}` };
    case 'TASK_STATUS_CHANGED':
      if (p.toStatus === 'FAILED') {
        return { ...base, category: 'TASK', color: 'var(--warn)', label: 'ABANDONED', text: `${shortTask(p.taskId)}${p.robotId ? ` (${p.robotId})` : ''} - ${String(p.reason ?? 'abandoned')}` };
      }
      return null;
    case 'TASK_REASSIGNED':
      return { ...base, category: 'TASK', color: 'var(--status-offline)', label: 'REASSIGNED', text: `${shortTask(p.taskId)} ${p.fromRobotId} -> ${p.toRobotId}` };
    case 'ROBOT_UNAVAILABLE':
      return { ...base, category: 'FAULT', color: 'var(--status-offline)', label: 'ROBOT OFFLINE', text: `${p.robotId} sensor fault injected${p.manual ? ' (manual)' : ''}` };
    case 'ROBOT_BROKEN_DOWN':
      return { ...base, category: 'FAULT', color: 'var(--status-offline)', label: 'BROKEN DOWN', text: `${p.robotId} needs attention` };
    case 'ROBOT_FIXED':
      return { ...base, category: 'FAULT', color: 'var(--ok)', label: 'FIXED', text: `${p.robotId} marked as fixed` };
    case 'AISLE_BLOCKED':
      return { ...base, category: 'FAULT', color: 'var(--status-blocked)', label: 'AISLE BLOCKED', text: `cell ${cell(p.cell)}${p.manual ? ' (manual)' : ''}` };
    case 'AISLE_CLEARED':
      return { ...base, category: 'FAULT', color: 'var(--ok)', label: 'AISLE CLEARED', text: `cell ${cell(p.cell)}` };
    case 'COMM_DELAY_STARTED':
      return { ...base, category: 'FAULT', color: 'var(--warn)', label: 'COMMS DELAYED', text: 'message delay injected' };
    case 'COMM_DELAY_ENDED':
      return { ...base, category: 'FAULT', color: 'var(--ok)', label: 'COMMS RESTORED', text: 'message delay ended' };
    case 'CONFLICT_DETECTED':
      if (p.collision === true) {
        const ids = Array.isArray(p.robotIds) ? (p.robotIds as unknown[]).join(' x ') : '?';
        return { ...base, category: 'COLLISION', color: 'var(--error)', label: 'COLLISION', text: `${ids} (independent referee, cumulative ${p.cumulativeCollisionCount ?? '?'})` };
      }
      return null;
    case 'SYSTEM': {
      const reason = String(p.reason ?? '');
      if (!reason) return null;
      return { ...base, category: 'SYSTEM', color: 'var(--text-2)', label: 'SYSTEM', text: reason };
    }
    default:
      return null; // COMM_FLOW, TASK_PUSHED_TO_ENGINE, and anything not part of the coordination story
  }
}

const FILTER_CATEGORY: Record<Exclude<FeedFilter, 'ALL'>, FeedCategory> = {
  NEGOTIATION: 'NEGOTIATION',
  TASKS: 'TASK',
  FAULTS: 'FAULT',
  COLLISIONS: 'COLLISION',
};

/** Newest first, capped. Events of another session (payload.sessionId differing from `sessionId`) are dropped when a session id is known. */
export function buildFeed(events: SimulationEvent[], filter: FeedFilter, sessionId: string | null, limit = 200): FeedLine[] {
  const lines: FeedLine[] = [];
  for (let i = events.length - 1; i >= 0 && lines.length < limit; i--) {
    const e = events[i];
    if (sessionId && typeof e.payload.sessionId === 'string' && e.payload.sessionId !== sessionId) continue;
    const line = describeEvent(e);
    if (!line) continue;
    if (filter !== 'ALL' && line.category !== FILTER_CATEGORY[filter]) continue;
    lines.push(line);
  }
  return lines;
}

/** Counts per filter chip (over all matching events of this session, uncapped). */
export function feedCounts(events: SimulationEvent[], sessionId: string | null): Record<FeedFilter, number> {
  const counts: Record<FeedFilter, number> = { ALL: 0, NEGOTIATION: 0, TASKS: 0, FAULTS: 0, COLLISIONS: 0 };
  for (const e of events) {
    if (sessionId && typeof e.payload.sessionId === 'string' && e.payload.sessionId !== sessionId) continue;
    const line = describeEvent(e);
    if (!line) continue;
    counts.ALL++;
    if (line.category === 'NEGOTIATION') counts.NEGOTIATION++;
    else if (line.category === 'TASK') counts.TASKS++;
    else if (line.category === 'FAULT') counts.FAULTS++;
    else if (line.category === 'COLLISION') counts.COLLISIONS++;
  }
  return counts;
}
