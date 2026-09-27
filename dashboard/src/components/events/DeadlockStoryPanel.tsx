// dashboard/src/components/events/DeadlockStoryPanel.tsx
// Owner: Member 4
//
// Builds a legible approach -> conflict -> yield -> resume narrative from
// two, and only two, real sources:
//   1. Real RobotState.status TRANSITIONS across the buffered tick history
//      (feed.robotHistory) — e.g. MOVING -> WAITING is a real, observed fact,
//      not an inference.
//   2. Real NEGOTIATION events (feed.allEvents) — the real
//      resolutionAction/peerRobotId ConflictResolver actually decided.
//
// DEADLOCK_DETECTED is a real contract value but is NEVER constructed
// anywhere in the current codebase (confirmed, Phase 1 audit) — this panel
// does not claim a "deadlock was detected" moment exists in the event
// stream. It only narrates what status transitions and NEGOTIATION events
// actually prove: a robot stopped, why (per its own resolver verdict, if
// recorded), and when it moved again. Nothing here is inferred beyond that.

import type { LiveFeed } from '../../hooks/useLiveFeed';
import type { NegotiationEventPayload, SimulationStatus } from '../../types/contracts';
import { EmptyState } from '../common/States';
import { STATUS_LABEL, statusColor } from '../../lib/statusColors';
import type { DisplayStatus } from '../../lib/statusColors';

interface StoryMoment {
  tick: number;
  robotId: string;
  kind: 'STATUS_CHANGE' | 'NEGOTIATION';
  fromStatus?: string;
  toStatus?: string;
  peerRobotId?: string | null;
  resolutionAction?: string;
}

function buildStory(feed: LiveFeed): StoryMoment[] {
  const moments: StoryMoment[] = [];

  // 1. Real status transitions, per robot, across the buffered history.
  const lastStatus: Record<string, string> = {};
  for (const { tick, robots } of feed.robotHistory) {
    for (const r of robots) {
      const prev = lastStatus[r.robotId];
      if (prev !== undefined && prev !== r.status) {
        moments.push({ tick, robotId: r.robotId, kind: 'STATUS_CHANGE', fromStatus: prev, toStatus: r.status });
      }
      lastStatus[r.robotId] = r.status;
    }
  }

  // 2. Real NEGOTIATION events.
  for (const e of feed.allEvents) {
    if (e.type !== 'NEGOTIATION') continue;
    const p = e.payload as unknown as NegotiationEventPayload;
    moments.push({
      tick: e.tick,
      robotId: p.robotId,
      kind: 'NEGOTIATION',
      peerRobotId: p.peerRobotId,
      resolutionAction: p.resolutionAction,
    });
  }

  return moments.sort((a, b) => a.tick - b.tick);
}

function MomentRow({ m }: { m: StoryMoment }) {
  if (m.kind === 'STATUS_CHANGE') {
    const toColor = statusColor((m.toStatus as DisplayStatus) ?? 'IDLE');
    return (
      <div className="mono" style={{ fontSize: 11, display: 'flex', gap: 8, alignItems: 'center', padding: '3px 0' }}>
        <span style={{ color: 'var(--text-2)', minWidth: 44 }}>t={m.tick}</span>
        <span style={{ fontWeight: 700 }}>{m.robotId}</span>
        <span style={{ color: 'var(--text-1)' }}>
          {STATUS_LABEL[(m.fromStatus as DisplayStatus) ?? 'IDLE']} → <span style={{ color: toColor, fontWeight: 700 }}>{STATUS_LABEL[(m.toStatus as DisplayStatus) ?? 'IDLE']}</span>
        </span>
      </div>
    );
  }
  return (
    <div className="mono" style={{ fontSize: 11, display: 'flex', gap: 8, alignItems: 'center', padding: '3px 0', paddingLeft: 16 }}>
      <span style={{ color: 'var(--text-2)', minWidth: 44 }}>t={m.tick}</span>
      <span style={{ color: 'var(--status-yield)' }}>↳ resolver:</span>
      <span style={{ fontWeight: 700 }}>{m.robotId}</span>
      {m.peerRobotId && <span style={{ color: 'var(--text-1)' }}>re: {m.peerRobotId}</span>}
      <span style={{ color: 'var(--status-yield)', fontWeight: 700 }}>{m.resolutionAction}</span>
    </div>
  );
}

export function DeadlockStoryPanel({ feed, status }: { feed: LiveFeed; status: SimulationStatus | null }) {
  const moments = buildStory(feed);
  const isDeadlockScenario = status?.scenarioId === 'd_deadlock';

  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <span style={{ fontWeight: 700, fontSize: 12 }}>
          {isDeadlockScenario ? 'Deadlock sequence (d_deadlock)' : 'State transition story'}
        </span>
        <div style={{ fontSize: 10, color: 'var(--text-2)', marginTop: 2 }}>
          Built only from real RobotState.status transitions and real NEGOTIATION events — never narrated beyond
          what those two sources actually show.
        </div>
      </div>
      {moments.length === 0 ? (
        <EmptyState
          title="No transitions recorded yet"
          detail={isDeadlockScenario ? 'Run d_deadlock to see the approach → conflict → yield → resume sequence.' : 'Nothing has changed status yet in this run.'}
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {moments.map((m, i) => (
            <MomentRow key={`${m.tick}-${m.robotId}-${m.kind}-${i}`} m={m} />
          ))}
        </div>
      )}
    </div>
  );
}

export default DeadlockStoryPanel;
