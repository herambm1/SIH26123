// dashboard/src/components/simulation/LiveSimulationView.tsx
// Owner: Member 4
//
// Composes the warehouse canvas, tick timeline, and a tabbed side panel
// (Inspector / Communication / Events / Deadlock Story). Real data only:
// WarehouseMap via GET /api/warehouse, RobotState + SimulationEvent via
// /ws/live buffering (useLiveFeed), event history also via GET /api/events
// (approved "b-1", used inside EventTimeline).

import { useEffect, useState } from 'react';
import type { LiveFeed } from '../../hooks/useLiveFeed';
import { useWarehouseMap } from '../../hooks/useWarehouseMap';
import type { SimulationStatus } from '../../types/contracts';
import { WarehouseCanvas } from './WarehouseCanvas';
import { RobotInspector } from './RobotInspector';
import { TickTimeline } from './TickTimeline';
import { CommunicationFeed } from '../events/CommunicationFeed';
import { EventTimeline } from '../events/EventTimeline';
import { DeadlockStoryPanel } from '../events/DeadlockStoryPanel';
import { EmptyState, ErrorState, LoadingState } from '../common/States';

const WS_STATUS_LABEL: Record<LiveFeed['connectionStatus'], string> = {
  connecting: 'CONNECTING TO /ws/live…',
  open: 'LIVE FEED CONNECTED',
  reconnecting: 'LIVE FEED DISCONNECTED — RECONNECTING…',
  disconnected: 'LIVE FEED DISCONNECTED',
};

type SideTab = 'inspector' | 'comms' | 'events' | 'story';

export function LiveSimulationView({ feed, status }: { feed: LiveFeed; status: SimulationStatus | null }) {
  const { map, loading, error } = useWarehouseMap(status?.scenarioId);
  const [selectedRobotId, setSelectedRobotId] = useState<string | null>(null);
  const [sideTab, setSideTab] = useState<SideTab>('inspector');

  const robots = feed.robotsAtDisplayTick;

  // If the selected robot isn't present at the currently displayed tick
  // (new run, or it was never in this scenario), clear the selection
  // rather than showing stale data under a still-highlighted id.
  useEffect(() => {
    if (selectedRobotId && !robots.some((r) => r.robotId === selectedRobotId)) {
      setSelectedRobotId(null);
    }
  }, [robots, selectedRobotId]);

  const selectedRobot = robots.find((r) => r.robotId === selectedRobotId) ?? null;
  const isDeadlockScenario = status?.scenarioId === 'd_deadlock';

  const tabButton = (tab: SideTab, label: string) => (
    <button
      onClick={() => setSideTab(tab)}
      style={{
        flex: 1,
        fontSize: 10,
        padding: '5px 4px',
        background: sideTab === tab ? 'var(--surface-3)' : 'var(--surface-1)',
        borderColor: sideTab === tab ? 'var(--accent)' : 'var(--border-1)',
        color: sideTab === tab ? 'var(--text-0)' : 'var(--text-1)',
        fontWeight: sideTab === tab ? 700 : 400,
      }}
    >
      {label}
    </button>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, height: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span
          className="mono"
          style={{
            fontSize: 10,
            fontWeight: 600,
            color: feed.connectionStatus === 'open' ? 'var(--ok)' : 'var(--error)',
          }}
        >
          {WS_STATUS_LABEL[feed.connectionStatus]}
        </span>
      </div>

      <div style={{ display: 'flex', gap: 12, flex: 1, minHeight: 0 }}>
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {loading ? (
            <LoadingState label="Fetching warehouse map…" />
          ) : error ? (
            <ErrorState title="Failed to fetch warehouse map" detail={error} />
          ) : !map ? (
            <EmptyState
              title="No warehouse map yet"
              detail="The backend has not received one — a scenario pushes its real WarehouseMap when it starts (GET /api/warehouse currently returns 503). Start a simulation from the left panel."
            />
          ) : robots.length === 0 ? (
            <>
              <WarehouseCanvas warehouseMap={map} robots={[]} selectedRobotId={null} onSelectRobot={() => {}} />
              <EmptyState title="No robot telemetry received yet" detail="Waiting for the first ROBOT_STATE_BATCH frame over /ws/live." />
            </>
          ) : (
            <WarehouseCanvas warehouseMap={map} robots={robots} selectedRobotId={selectedRobotId} onSelectRobot={setSelectedRobotId} />
          )}

          <div style={{ padding: '8px 10px', background: 'var(--surface-1)', border: '1px solid var(--border-0)' }}>
            <TickTimeline feed={feed} />
          </div>
        </div>

        <aside
          style={{
            width: 340,
            flexShrink: 0,
            background: 'var(--surface-1)',
            border: '1px solid var(--border-0)',
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
          }}
        >
          <div style={{ display: 'flex', gap: 2, padding: 6, borderBottom: '1px solid var(--border-0)' }}>
            {tabButton('inspector', 'INSPECTOR')}
            {tabButton('comms', 'COMMS')}
            {tabButton('events', 'EVENTS')}
            {tabButton('story', isDeadlockScenario ? 'DEADLOCK' : 'STORY')}
          </div>
          <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: 12 }}>
            {sideTab === 'inspector' && <RobotInspector robot={selectedRobot} feed={feed} />}
            {sideTab === 'comms' && <CommunicationFeed feed={feed} />}
            {sideTab === 'events' && <EventTimeline feed={feed} />}
            {sideTab === 'story' && <DeadlockStoryPanel feed={feed} status={status} />}
          </div>
        </aside>
      </div>
    </div>
  );
}

export default LiveSimulationView;
