// dashboard/src/components/simulation/RobotMarker.tsx
// Owner: Member 4
//
// Renders exactly at RobotState.position for whichever tick is currently
// displayed — no CSS transition on x/y, so movement between ticks is a
// hard, discrete jump matching the real discrete-tick simulation (no fake
// interpolation, per the non-negotiable rule).

import { statusColor } from '../../lib/statusColors';
import type { RobotState } from '../../types/contracts';

export function RobotMarker({
  robot,
  selected,
  onSelect,
}: {
  robot: RobotState;
  selected: boolean;
  onSelect: () => void;
}) {
  const color = statusColor(robot.status);
  const cx = robot.position.x + 0.5;
  const cy = robot.position.y + 0.5;

  return (
    <g onClick={onSelect} style={{ cursor: 'pointer' }}>
      {/* Planned path (remaining waypoints) — real currentPath data, not inferred */}
      {robot.currentPath.length > 0 && (
        <polyline
          points={[`${cx},${cy}`, ...robot.currentPath.map((p) => `${p.x + 0.5},${p.y + 0.5}`)].join(' ')}
          fill="none"
          stroke={color}
          strokeWidth={0.06}
          strokeDasharray="0.12 0.1"
          opacity={0.55}
          vectorEffect="non-scaling-stroke"
        />
      )}

      {robot.status === 'OFFLINE' && (
        <circle cx={cx} cy={cy} r={0.42} fill="none" stroke={color} strokeWidth={0.08} strokeDasharray="0.1 0.1" />
      )}

      <circle
        cx={cx}
        cy={cy}
        r={0.32}
        fill={color}
        stroke={selected ? 'var(--text-0)' : 'none'}
        strokeWidth={selected ? 0.07 : 0}
      />
      <text
        x={cx}
        y={cy}
        textAnchor="middle"
        dominantBaseline="central"
        fontSize={0.28}
        fontFamily="var(--font-mono)"
        fontWeight={700}
        fill="#08090a"
      >
        {robot.robotId.replace(/^R0+(?=\d)/, 'R')}
      </text>
    </g>
  );
}

export default RobotMarker;
