// dashboard/src/components/shell/RunInfoStrip.tsx
// Owner: Member 4
//
// Real-time run identity: scenario / mode / tick, sourced from
// GET /api/simulation/status (proxied Python /control/status). Shows an
// explicit "no run active" state rather than blank/zero when nothing is
// running — currentTick=0 while idle is a real value, not a placeholder,
// but distinguishing "running" from "idle" avoids implying a tick is
// progressing when it isn't.

import type { SimulationStatus } from '../../types/contracts';
import { getScenario } from '../../data/scenarioCatalog';

export function RunInfoStrip({ status }: { status: SimulationStatus | null }) {
  if (!status) {
    return <div className="mono" style={{ color: 'var(--text-2)', fontSize: 12 }}>status unavailable</div>;
  }

  const catalogEntry = status.scenarioId ? getScenario(status.scenarioId) : undefined;

  return (
    <div className="mono" style={{ display: 'flex', alignItems: 'center', gap: 14, fontSize: 12 }}>
      <span style={{ color: status.running ? 'var(--ok)' : 'var(--text-2)', fontWeight: 700 }}>
        {status.running ? '● RUNNING' : '○ IDLE'}
      </span>
      <span>
        <span style={{ color: 'var(--text-1)' }}>scenario </span>
        {status.scenarioId ? (catalogEntry?.shortId ?? status.scenarioId) : '—'}
      </span>
      <span>
        <span style={{ color: 'var(--text-1)' }}>mode </span>
        {status.mode || '—'}
      </span>
      <span>
        <span style={{ color: 'var(--text-1)' }}>tick </span>
        {status.currentTick}
      </span>
    </div>
  );
}

export default RunInfoStrip;
