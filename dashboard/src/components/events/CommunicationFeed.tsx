// dashboard/src/components/events/CommunicationFeed.tsx
// Owner: Member 4
//
// Renders real NEGOTIATION events only — see shared/python/models.py's
// SimulationEvent docstring and simulation/runner.py's
// _emit_negotiation_event_if_changed() for exactly what this reads
// (agent._action_this_tick / _waiting_on / _blocked_by_peer, already
// computed by RobotAgent/ConflictResolver, never re-derived here).
//
// Each line is ONE robot's own local decision (robotId, its real
// resolutionAction, and the real peer id it names, if any) — never a
// synthesized two-sided transcript. A robot only ever reports its OWN
// resolver verdict; if its peer also emitted an event this tick, that is a
// SEPARATE line from the peer's own agent, exactly reflecting that neither
// robot has visibility into a shared/arbitrated outcome — there is no
// central negotiation to narrate as one exchange.

import type { LiveFeed } from '../../hooks/useLiveFeed';
import type { NegotiationEventPayload } from '../../types/contracts';
import { EmptyState } from '../common/States';

const ACTION_COLOR: Record<string, string> = {
  CONTINUE: 'var(--ok)',
  WAIT: 'var(--status-waiting)',
  YIELD: 'var(--status-yield)',
  REROUTE: 'var(--accent)',
  REASSIGN_TASK: 'var(--status-offline)',
};

export function CommunicationFeed({ feed }: { feed: LiveFeed }) {
  const negotiations = feed.allEvents.filter((e) => e.type === 'NEGOTIATION');

  if (negotiations.length === 0) {
    return (
      <EmptyState
        title="No negotiation events yet"
        detail="Real robot decisions (resolutionAction) are recorded here the moment a robot's ConflictResolver verdict changes — CONTINUE, WAIT, YIELD, REROUTE, or REASSIGN_TASK. Nothing has changed yet for any robot in this run."
      />
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {negotiations
        .slice()
        .reverse()
        .map((e) => {
          const p = e.payload as unknown as NegotiationEventPayload;
          const color = ACTION_COLOR[p.resolutionAction] ?? 'var(--text-1)';
          return (
            <div
              key={e.eventId}
              className="mono"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                fontSize: 11,
                padding: '4px 8px',
                background: 'var(--surface-2)',
                borderLeft: `3px solid ${color}`,
              }}
            >
              <span style={{ color: 'var(--text-2)', minWidth: 44 }}>t={e.tick}</span>
              <span style={{ fontWeight: 700 }}>{p.robotId}</span>
              {p.peerRobotId && <span style={{ color: 'var(--text-1)' }}>re: {p.peerRobotId}</span>}
              <span style={{ flex: 1 }} />
              <span style={{ color, fontWeight: 700 }}>{p.resolutionAction}</span>
            </div>
          );
        })}
    </div>
  );
}

export default CommunicationFeed;
