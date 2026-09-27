// dashboard/src/components/product/ProductView.tsx
//
// PRODUCT tab: a live, seeded, exploratory session driven by the real pipeline (Java task lifecycle -> Python RobotAgent
// coordination -> WebSocket). Composition only:
//   * session lifecycle + broken-down overlay : useProductSession (GET/POST /api/product/...)
//   * robot frames + events                    : the existing useLiveFeed (/ws/live), reset by the session generation
//   * map                                      : the existing WarehouseCanvas (real WarehouseMap from GET /api/warehouse)
// Nothing here is simulated or interpolated; a broken-down robot is drawn with the existing OFFLINE marker.

import { useEffect, useMemo, useState } from 'react';
import { fetchWarehouseMap } from '../../api/client';
import { useLiveFeed } from '../../hooks/useLiveFeed';
import { useProductSession } from '../../hooks/useProductSession';
import type { WarehouseMap } from '../../types/contracts';
import type { ProductSpeedMultiplier } from '../../types/product';
import { EmptyState, ErrorState } from '../common/States';
import { WarehouseCanvas } from '../simulation/WarehouseCanvas';
import { FleetRoster } from './FleetRoster';
import { HonestyBanner } from './HonestyBanner';
import { KpiStrip } from './KpiStrip';
import { ProductEventFeed } from './ProductEventFeed';
import { deriveKpis, deriveRoster, robotsForMap } from './productDerive';

const WS_LABEL = {
  connecting: 'CONNECTING TO /ws/live…',
  open: 'LIVE FEED CONNECTED',
  reconnecting: 'LIVE FEED DISCONNECTED — RECONNECTING…',
  disconnected: 'LIVE FEED DISCONNECTED',
} as const;

/** The real WarehouseMap, fetched once the first robot frame of a session has arrived (Python pushes the map at session start). */
function useSessionMap(sessionId: string | null, hasFrames: boolean) {
  const [map, setMap] = useState<WarehouseMap | null>(null);
  useEffect(() => {
    setMap(null);
  }, [sessionId]);
  useEffect(() => {
    if (!sessionId || !hasFrames) return;
    let cancelled = false;
    fetchWarehouseMap()
      .then((m) => {
        if (!cancelled && m) setMap(m);
      })
      .catch(() => {
        /* the next session/frame change retries; the empty state below explains */
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, hasFrames]);
  return map;
}

export function ProductView() {
  const session = useProductSession();
  const feed = useLiveFeed(session.generation);
  const [speed, setSpeed] = useState<ProductSpeedMultiplier>(2);
  const [selectedRobotId, setSelectedRobotId] = useState<string | null>(null);

  const { status } = session;
  const running = status?.running ?? false;
  const sessionId = status?.sessionId ?? null;
  const robots = feed.robotsAtDisplayTick;
  const brokenDown = status?.brokenDownRobots ?? [];
  const map = useSessionMap(sessionId, robots.length > 0);

  useEffect(() => {
    if (selectedRobotId && !robots.some((r) => r.robotId === selectedRobotId)) setSelectedRobotId(null);
  }, [robots, selectedRobotId]);

  const events = feed.allEvents;
  const kpis = useMemo(() => deriveKpis(status, events, robots), [status, events, robots]);
  const roster = useMemo(() => deriveRoster(robots, brokenDown, events), [robots, brokenDown, events]);
  const mapRobots = useMemo(() => robotsForMap(robots, brokenDown), [robots, brokenDown]);

  const backendDown = session.backend === 'unreachable';
  const startLabel = session.starting ? 'STARTING…' : running ? 'RANDOMIZE & RESTART' : 'RANDOMIZE & START';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, height: '100%', minHeight: 0 }} data-testid="product-view">
      <HonestyBanner />

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <button
          data-testid="randomize-start"
          onClick={() => session.randomizeAndStart(speed)}
          disabled={session.starting || backendDown}
          style={{ background: 'var(--accent-dim)', borderColor: 'var(--accent)', color: 'var(--text-0)', fontWeight: 700, padding: '7px 16px', letterSpacing: '0.04em' }}
        >
          {startLabel}
        </button>
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-1)' }}>
          SPEED
          <select
            data-testid="speed-select"
            value={speed}
            onChange={(e) => setSpeed(Number(e.target.value) as ProductSpeedMultiplier)}
            style={{ background: 'var(--surface-2)', color: 'var(--text-0)', border: '1px solid var(--border-1)', padding: '4px 6px' }}
          >
            <option value={1}>1x (0.5 s / tick)</option>
            <option value={2}>2x</option>
            <option value={4}>4x</option>
          </select>
        </label>
        <button data-testid="stop" onClick={session.stop} disabled={!running || session.stopping}>
          {session.stopping ? 'STOPPING…' : 'STOP'}
        </button>
        <span className="mono" data-testid="session-info" style={{ fontSize: 11, color: running ? 'var(--ok)' : 'var(--text-1)' }}>
          {running ? `SESSION RUNNING · tick ${status?.currentTick ?? 0} · seed ${status?.seed ?? '?'}` : status?.sessionId ? `SESSION STOPPED · seed ${status.seed ?? '?'}` : 'NO SESSION'}
        </span>
        <span style={{ flex: 1 }} />
        <span className="mono" style={{ fontSize: 10, fontWeight: 600, color: feed.connectionStatus === 'open' ? 'var(--ok)' : 'var(--error)' }}>
          {WS_LABEL[feed.connectionStatus]}
        </span>
      </div>

      {backendDown && <ErrorState title="Backend unreachable" detail="The Java backend at http://localhost:8080 is not answering; start it (and the Python engine on :8001) to run a session." />}
      {session.error && <ErrorState title="Could not start or stop the session" detail={session.error} />}

      <KpiStrip kpis={kpis} active={running || robots.length > 0} />

      <div style={{ display: 'flex', gap: 12, flex: 1, minHeight: 0 }}>
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }} data-testid="product-map">
          {robots.length === 0 && !map ? (
            <EmptyState
              title={running ? 'Waiting for the first robot frame…' : 'No session running'}
              detail={
                running
                  ? 'The session has started; positions appear as soon as the first tick arrives over /ws/live.'
                  : 'Press RANDOMIZE & START to begin a new seeded session. Robots, their movement, task assignments and any real coordination events then appear here live.'
              }
            />
          ) : !map ? (
            <EmptyState title="Fetching the warehouse map…" detail="GET /api/warehouse" />
          ) : (
            <WarehouseCanvas warehouseMap={map} robots={mapRobots} selectedRobotId={selectedRobotId} onSelectRobot={setSelectedRobotId} />
          )}
        </div>

        <aside style={{ width: 380, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 10, minHeight: 0 }}>
          <div style={{ background: 'var(--surface-1)', border: '1px solid var(--border-0)', padding: 10, flexShrink: 0, maxHeight: '60%', overflowY: 'auto' }}>
            <FleetRoster rows={roster} selectedRobotId={selectedRobotId} onSelect={setSelectedRobotId} onFix={session.fixRobot} fixing={session.fixing} fixError={session.fixError} />
          </div>
          <div style={{ background: 'var(--surface-1)', border: '1px solid var(--border-0)', padding: 10, flex: 1, minHeight: 0 }}>
            <ProductEventFeed events={events} sessionId={sessionId} />
          </div>
        </aside>
      </div>
    </div>
  );
}

export default ProductView;
