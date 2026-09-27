// dashboard/src/components/product/FleetRoster.tsx
//
// One row per robot from the latest /ws/live frame. A robot the backend has latched as broken down shows
// "Broken down — needs attention" with a "Mark as fixed" button (POST /api/product/robot/{id}/fix). Everything else uses the shared
// StatusPill so colors stay identical to the map and the Live view.

import type { RosterRow } from './productDerive';
import { StatusPill } from '../common/StatusPill';

interface FleetRosterProps {
  rows: RosterRow[];
  selectedRobotId: string | null;
  onSelect: (id: string) => void;
  onFix: (robotId: string) => void;
  fixing: Set<string>;
  fixError: string | null;
}

const shortTask = (id: string | null) => {
  if (!id) return '—';
  const m = id.match(/_(\d+)$/);
  return m ? `#${m[1]}` : id;
};

export function FleetRoster({ rows, selectedRobotId, onSelect, onFix, fixing, fixError }: FleetRosterProps) {
  return (
    <div data-testid="fleet-roster">
      <div style={{ fontSize: 10, letterSpacing: '0.06em', color: 'var(--text-1)', marginBottom: 6 }}>FLEET ROSTER</div>
      {rows.length === 0 ? (
        <div style={{ fontSize: 12, color: 'var(--text-1)' }}>No robot telemetry received yet.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {rows.map((r) => {
            const broken = r.status === 'BROKEN_DOWN';
            const selected = r.robotId === selectedRobotId;
            return (
              <div
                key={r.robotId}
                data-testid={`roster-row-${r.robotId}`}
                onClick={() => onSelect(r.robotId)}
                style={{
                  cursor: 'pointer',
                  padding: '6px 8px',
                  background: 'var(--surface-2)',
                  borderLeft: `3px solid ${broken ? 'var(--status-offline)' : selected ? 'var(--accent)' : 'var(--border-1)'}`,
                  outline: selected ? '1px solid var(--accent)' : 'none',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className="mono" style={{ fontWeight: 700, minWidth: 34 }}>
                    {r.robotId}
                  </span>
                  {broken ? (
                    <span
                      className="mono"
                      data-testid={`roster-status-${r.robotId}`}
                      style={{ fontSize: 11, fontWeight: 700, color: 'var(--status-offline)' }}
                    >
                      Broken down — needs attention
                    </span>
                  ) : (
                    <span data-testid={`roster-status-${r.robotId}`}>
                      <StatusPill status={r.status as Exclude<typeof r.status, 'BROKEN_DOWN'>} compact />
                    </span>
                  )}
                  <span style={{ flex: 1 }} />
                  {broken && (
                    <button
                      data-testid={`fix-${r.robotId}`}
                      disabled={fixing.has(r.robotId)}
                      onClick={(e) => {
                        e.stopPropagation();
                        onFix(r.robotId);
                      }}
                      style={{ fontSize: 11, padding: '3px 8px', borderColor: 'var(--ok)', color: 'var(--ok)', fontWeight: 700 }}
                    >
                      {fixing.has(r.robotId) ? 'Fixing…' : 'Mark as fixed'}
                    </button>
                  )}
                </div>
                <div className="mono" style={{ fontSize: 10, color: 'var(--text-1)', marginTop: 3, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  <span>
                    at ({r.position.x},{r.position.y})
                  </span>
                  <span>task {shortTask(r.taskId)}</span>
                  {r.destination && !broken && (
                    <span>
                      → ({r.destination.x},{r.destination.y}) · {r.pathRemaining} steps
                    </span>
                  )}
                  {r.verdict && !broken && <span>last verdict {r.verdict}</span>}
                </div>
              </div>
            );
          })}
        </div>
      )}
      {fixError && (
        <div className="mono" data-testid="fix-error" style={{ marginTop: 6, fontSize: 11, color: 'var(--error)' }}>
          Mark as fixed failed — {fixError}
        </div>
      )}
    </div>
  );
}

export default FleetRoster;
