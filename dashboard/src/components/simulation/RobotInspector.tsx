// dashboard/src/components/simulation/RobotInspector.tsx
// Owner: Member 4
//
// Detail panel for the selected robot — every field is real RobotState data
// for whichever tick is currently displayed. The conflict/decision-reasoning
// subsection now reads the real NEGOTIATION event (Phase 5, approved
// addition "b-2") most recently recorded for this robot, up to the
// displayed tick — the actual resolutionAction/peer ConflictResolver
// decided, never invented. If none has occurred yet for this robot, that is
// shown as a real empty state, not a fabricated "no conflict" narrative.

import type { LiveFeed } from '../../hooks/useLiveFeed';
import type { NegotiationEventPayload, RobotState } from '../../types/contracts';
import { StatusPill } from '../common/StatusPill';
import { EmptyState } from '../common/States';

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0', borderBottom: '1px solid var(--border-0)' }}>
      <span style={{ color: 'var(--text-1)', fontSize: 11 }}>{label}</span>
      <span className="mono" style={{ fontSize: 11 }}>{value}</span>
    </div>
  );
}

export function RobotInspector({ robot, feed }: { robot: RobotState | null; feed: LiveFeed }) {
  if (!robot) {
    return <EmptyState title="No robot selected" detail="Click a robot on the map to inspect it." />;
  }

  const pos = `(${robot.position.x}, ${robot.position.y})`;
  const dest = robot.destination ? `(${robot.destination.x}, ${robot.destination.y})` : '—';

  const robotNegotiations = feed.eventsUpToDisplayTick.filter(
    (e) => e.type === 'NEGOTIATION' && (e.payload as unknown as NegotiationEventPayload).robotId === robot.robotId,
  );
  const latestNegotiation = robotNegotiations.length > 0 ? robotNegotiations[robotNegotiations.length - 1] : undefined;
  const negotiationPayload = latestNegotiation?.payload as unknown as NegotiationEventPayload | undefined;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span className="mono" style={{ fontWeight: 700, fontSize: 14 }}>{robot.robotId}</span>
        <StatusPill status={robot.status} />
      </div>

      <Field label="Position" value={pos} />
      <Field label="Destination" value={dest} />
      <Field label="Velocity" value={`${robot.velocity} cells/tick`} />
      <Field label="Battery" value={`${robot.battery.toFixed(0)}%`} />
      <Field label="Current task" value={robot.currentTaskId ?? '—'} />
      <Field label="Remaining waypoints" value={String(robot.currentPath.length)} />
      <Field label="Snapshot tick" value={String(robot.timestamp)} />

      <div style={{ marginTop: 14 }}>
        <label>Conflict / decision reasoning</label>
        <div style={{ marginTop: 6 }}>
          {negotiationPayload ? (
            <div style={{ fontSize: 11, background: 'var(--surface-2)', padding: '8px 10px', borderLeft: '3px solid var(--status-yield)' }}>
              <div className="mono">
                Last resolver verdict: <span style={{ color: 'var(--status-yield)', fontWeight: 700 }}>{negotiationPayload.resolutionAction}</span>
                {negotiationPayload.peerRobotId && <> re: <span style={{ fontWeight: 700 }}>{negotiationPayload.peerRobotId}</span></>}
                {' '}(tick {latestNegotiation!.tick})
              </div>
              <div style={{ color: 'var(--text-2)', marginTop: 4 }}>
                From RobotAgent's real ConflictResolver — not inferred by the frontend.
              </div>
            </div>
          ) : (
            <EmptyState
              title="No resolver decision recorded yet"
              detail="This robot's ConflictResolver has not produced a recorded verdict (CONTINUE/WAIT/YIELD/REROUTE/REASSIGN_TASK) up to the currently displayed tick."
            />
          )}
        </div>
      </div>
    </div>
  );
}

export default RobotInspector;
