// dashboard/src/components/shell/PlaybackControls.tsx
// Owner: Member 4
//
// Start/Stop are real POST /api/simulation/control calls. Step/pause/resume
// now operate on the real client-side tick buffer (useLiveFeed) — there is
// still no backend history, so these can only move backward through ticks
// already received, never forward past the latest (see TickTimeline /
// useLiveFeed for the enforced bounds).

import type { SimulationControl } from '../../hooks/useSimulationControl';
import type { LiveFeed } from '../../hooks/useLiveFeed';

export function PlaybackControls({ control, feed }: { control: SimulationControl; feed: LiveFeed }) {
  const { status, starting, stopping, start, stop } = control;
  const running = status?.running ?? false;
  const hasBuffer = feed.displayTick !== null;

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <button className="primary" disabled={running || starting} onClick={start} title="POST /api/simulation/control {action: start}">
        {starting ? 'STARTING…' : '▶ START'}
      </button>
      <button disabled={!running || stopping} onClick={stop} title="POST /api/simulation/control {action: stop}">
        {stopping ? 'STOPPING…' : '■ STOP'}
      </button>
      <span style={{ width: 1, height: 18, background: 'var(--border-1)', margin: '0 4px' }} />
      <button disabled={!hasBuffer || feed.displayTick === feed.minBufferedTick} onClick={feed.stepBack} title="Step back one buffered tick">
        ⏮
      </button>
      <button
        disabled={!hasBuffer}
        onClick={feed.isLive ? feed.pauseAtCurrent : feed.resumeLive}
        title={feed.isLive ? 'Pause — freeze on the current tick (buffer keeps filling in the background)' : 'Resume following the live feed'}
      >
        {feed.isLive ? '⏸ pause' : '▶ resume'}
      </button>
      <button
        disabled={!hasBuffer || feed.displayTick === feed.maxBufferedTick}
        onClick={feed.stepForward}
        title="Step forward — cannot exceed the latest tick actually received"
      >
        ⏭
      </button>
    </div>
  );
}

export default PlaybackControls;
