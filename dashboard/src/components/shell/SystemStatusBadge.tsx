// dashboard/src/components/shell/SystemStatusBadge.tsx
// Owner: Member 4
//
// Two independent badges, not one — a real runtime distinction found during
// Phase 4 integration testing: GET /api/simulation/status returns HTTP 503
// when the Python engine is unreachable, but the Java backend answered that
// request correctly (it's up, doing exactly what its resilience design
// promises). Collapsing these into a single "backend unreachable" label
// would misrepresent which half of the system is actually down.

import type { BackendReachability, EngineReachability } from '../../hooks/useSimulationControl';

const BACKEND_LABEL: Record<BackendReachability, string> = {
  unknown: 'BACKEND CONNECTING…',
  reachable: 'BACKEND ONLINE',
  unreachable: 'BACKEND UNREACHABLE',
};
const ENGINE_LABEL: Record<EngineReachability, string> = {
  unknown: 'SIM ENGINE UNKNOWN',
  reachable: 'SIM ENGINE ONLINE',
  unreachable: 'SIM ENGINE UNREACHABLE',
};

const COLOR = { unknown: 'var(--text-2)', reachable: 'var(--ok)', unreachable: 'var(--error)' } as const;

function Pill({ label, color, title }: { label: string; color: string; title: string }) {
  return (
    <div
      className="mono"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        fontSize: 11,
        fontWeight: 600,
        color,
        border: `1px solid ${color}`,
        borderRadius: 2,
        padding: '3px 8px',
      }}
      title={title}
    >
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: color }} />
      {label}
    </div>
  );
}

export function SystemStatusBadge({
  reachability,
  engineReachability,
}: {
  reachability: BackendReachability;
  engineReachability: EngineReachability;
}) {
  return (
    <div style={{ display: 'flex', gap: 6 }}>
      <Pill
        label={BACKEND_LABEL[reachability]}
        color={COLOR[reachability]}
        title="Java backend (localhost:8080) reachability"
      />
      <Pill
        label={ENGINE_LABEL[engineReachability]}
        color={COLOR[engineReachability]}
        title="Python simulation engine reachability, as reported by the Java backend's GET /api/simulation/status — the backend itself may be fully healthy even when this reads unreachable"
      />
    </div>
  );
}

export default SystemStatusBadge;
