// dashboard/src/components/simulation/WarehouseCanvas.tsx
// Owner: Member 4
//
// Renders the real WarehouseMap (obstacles, choke points, and — only when
// actually non-empty in the real data — pickup/drop/blocked cells) plus
// real RobotState markers for whichever tick is being displayed. SVG with a
// unit-per-cell viewBox so it scales to any real gridWidth/gridHeight
// without hardcoded pixel dimensions (confirmed varying across scenarios:
// 20x15 demo_map, 20x20 benchmark fixture, 25x11 i_parallel_aisles).

import { useMemo } from 'react';
import type { RobotState, WarehouseMap } from '../../types/contracts';
import { RobotMarker } from './RobotMarker';

interface WarehouseCanvasProps {
  warehouseMap: WarehouseMap;
  robots: RobotState[];
  selectedRobotId: string | null;
  onSelectRobot: (id: string) => void;
}

export function WarehouseCanvas({ warehouseMap, robots, selectedRobotId, onSelectRobot }: WarehouseCanvasProps) {
  const { gridWidth, gridHeight, obstacles, chokePoints, pickupPoints, dropPoints, blockedCells } = warehouseMap;

  const obstacleKeys = useMemo(() => new Set(obstacles.map((p) => `${p.x},${p.y}`)), [obstacles]);

  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <svg
        viewBox={`0 0 ${gridWidth} ${gridHeight}`}
        style={{
          width: '100%',
          flex: 1,
          minHeight: 0,
          background: 'var(--surface-1)',
          border: '1px solid var(--border-0)',
        }}
        shapeRendering="crispEdges"
      >
        {/* Floor grid */}
        {Array.from({ length: gridWidth + 1 }, (_, x) => (
          <line key={`gx${x}`} x1={x} y1={0} x2={x} y2={gridHeight} stroke="var(--border-0)" strokeWidth={0.02} />
        ))}
        {Array.from({ length: gridHeight + 1 }, (_, y) => (
          <line key={`gy${y}`} x1={0} y1={y} x2={gridWidth} y2={y} stroke="var(--border-0)" strokeWidth={0.02} />
        ))}

        {/* Obstacles — real WarehouseMap.obstacles */}
        {obstacles.map((p, i) => (
          <rect key={`obs${i}`} x={p.x} y={p.y} width={1} height={1} fill="var(--surface-3)" />
        ))}

        {/* Dynamically blocked cells — real WarehouseMap.blockedCells (only rendered if the field is actually non-empty) */}
        {blockedCells.map((p, i) => (
          <g key={`blk${i}`}>
            <rect x={p.x} y={p.y} width={1} height={1} fill="var(--status-blocked)" opacity={0.35} />
            <line x1={p.x} y1={p.y} x2={p.x + 1} y2={p.y + 1} stroke="var(--status-blocked)" strokeWidth={0.05} />
            <line x1={p.x + 1} y1={p.y} x2={p.x} y2={p.y + 1} stroke="var(--status-blocked)" strokeWidth={0.05} />
          </g>
        ))}

        {/* Choke points — real WarehouseMap.chokePoints */}
        {chokePoints
          .filter((p) => !obstacleKeys.has(`${p.x},${p.y}`))
          .map((p, i) => (
            <rect
              key={`chk${i}`}
              x={p.x + 0.12}
              y={p.y + 0.12}
              width={0.76}
              height={0.76}
              fill="none"
              stroke="var(--warn)"
              strokeWidth={0.05}
              strokeDasharray="0.08 0.08"
            />
          ))}

        {/* Pickup / drop points — real WarehouseMap fields, only rendered when populated */}
        {pickupPoints.map((p, i) => (
          <circle key={`pu${i}`} cx={p.x + 0.5} cy={p.y + 0.5} r={0.12} fill="var(--accent)" />
        ))}
        {dropPoints.map((p, i) => (
          <rect key={`dp${i}`} x={p.x + 0.35} y={p.y + 0.35} width={0.3} height={0.3} fill="var(--status-completed)" />
        ))}

        {/* Robots — real RobotState for the currently displayed tick */}
        {robots.map((r) => (
          <RobotMarker key={r.robotId} robot={r} selected={r.robotId === selectedRobotId} onSelect={() => onSelectRobot(r.robotId)} />
        ))}
      </svg>

      <div style={{ display: 'flex', gap: 14, padding: '6px 4px 0', fontSize: 10, color: 'var(--text-1)', flexWrap: 'wrap' }}>
        <LegendSwatch color="var(--surface-3)" label="obstacle" square />
        <LegendSwatch color="var(--warn)" label="choke point" outline />
        {blockedCells.length > 0 && <LegendSwatch color="var(--status-blocked)" label="blocked (scripted event)" square />}
        {pickupPoints.length > 0 && <LegendSwatch color="var(--accent)" label="pickup point" />}
        {dropPoints.length > 0 && <LegendSwatch color="var(--status-completed)" label="drop point" square />}
      </div>
    </div>
  );
}

function LegendSwatch({ color, label, square, outline }: { color: string; label: string; square?: boolean; outline?: boolean }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
      <span
        style={{
          width: 9,
          height: 9,
          background: outline ? 'transparent' : color,
          border: outline ? `1.5px dashed ${color}` : 'none',
          borderRadius: square || outline ? 1 : '50%',
        }}
      />
      {label}
    </span>
  );
}

export default WarehouseCanvas;
