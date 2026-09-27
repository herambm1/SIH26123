// dashboard/src/components/product/KpiStrip.tsx
//
// Tasks completed / active / pending, active conflicts and referee collisions (red when > 0) — all derived from real data, see
// productDerive.deriveKpis for the exact definitions (shown as tooltips).

import type { ProductKpis } from './productDerive';

function Tile({ label, value, title, tone, testId }: { label: string; value: number | string; title: string; tone?: 'error' | 'warn'; testId: string }) {
  const color = tone === 'error' ? 'var(--error)' : tone === 'warn' ? 'var(--warn)' : 'var(--text-0)';
  return (
    <div
      title={title}
      data-testid={testId}
      style={{
        flex: 1,
        minWidth: 110,
        padding: '8px 12px',
        background: 'var(--surface-1)',
        border: `1px solid ${tone === 'error' ? 'var(--error)' : 'var(--border-0)'}`,
      }}
    >
      <div style={{ fontSize: 10, color: 'var(--text-1)', letterSpacing: '0.05em' }}>{label}</div>
      <div className="mono" style={{ fontSize: 22, fontWeight: 700, color, lineHeight: 1.2 }}>
        {value}
      </div>
    </div>
  );
}

export function KpiStrip({ kpis, active }: { kpis: ProductKpis; active: boolean }) {
  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }} data-testid="kpi-strip">
      <Tile testId="kpi-completed" label="TASKS COMPLETED" value={kpis.completed} title="Tasks whose robot reached the drop cell (Java's lifetime counter for this session)." />
      <Tile testId="kpi-active" label="TASKS ACTIVE" value={kpis.active} title="Tasks handed to a robot and not yet completed or abandoned." />
      <Tile testId="kpi-pending" label="TASKS PENDING" value={kpis.pending} title="Tasks created but not yet handed to a robot (no idle robot available yet)." />
      <Tile
        testId="kpi-abandoned"
        label="TASKS ABANDONED"
        value={kpis.abandoned}
        tone={kpis.abandoned > 0 ? 'warn' : undefined}
        title="Tasks abandoned after the robot made no progress for 30 ticks (the robot is released and can take new work)."
      />
      <Tile
        testId="kpi-conflicts"
        label="ACTIVE CONFLICTS"
        value={kpis.activeConflicts}
        title="Robots that are waiting or blocked right now and whose latest coordination verdict was WAIT, YIELD, REROUTE or REASSIGN_TASK."
      />
      <Tile
        testId="kpi-collisions"
        label="REFEREE COLLISIONS"
        value={active || kpis.collisions > 0 ? kpis.collisions : '—'}
        tone={kpis.collisions > 0 ? 'error' : undefined}
        title="Collisions counted by the independent referee (it does not use the robots' own detector). Red when above zero."
      />
      <Tile testId="kpi-broken" label="ROBOTS BROKEN DOWN" value={kpis.brokenDown} tone={kpis.brokenDown > 0 ? 'error' : undefined} title="Robots latched as broken down until marked as fixed." />
    </div>
  );
}

export default KpiStrip;
