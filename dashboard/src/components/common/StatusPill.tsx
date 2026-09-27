// dashboard/src/components/common/StatusPill.tsx
// Owner: Member 4
//
// The one place a status renders as a colored pill. Used identically on the
// warehouse map legend, the robot inspector, the event timeline, and the
// benchmark completion table — see src/lib/statusColors.ts for the fixed
// color/label mapping this reads from.

import type { DisplayStatus } from '../../lib/statusColors';
import { statusColor, STATUS_LABEL } from '../../lib/statusColors';

interface StatusPillProps {
  status: DisplayStatus;
  compact?: boolean;
}

export function StatusPill({ status, compact = false }: StatusPillProps) {
  const color = statusColor(status);
  return (
    <span
      className="mono"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        padding: compact ? '1px 6px' : '2px 8px',
        fontSize: compact ? 10 : 11,
        fontWeight: 600,
        letterSpacing: '0.03em',
        border: `1px solid ${color}`,
        borderRadius: 2,
        color,
        background: 'color-mix(in srgb, ' + color + ' 12%, transparent)',
        whiteSpace: 'nowrap',
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: color,
          flexShrink: 0,
        }}
      />
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

export default StatusPill;
