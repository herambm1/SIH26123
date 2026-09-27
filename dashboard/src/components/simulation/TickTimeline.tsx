// dashboard/src/components/simulation/TickTimeline.tsx
// Owner: Member 4
//
// Scrubs backward through ticks ACTUALLY RECEIVED over /ws/live during this
// connection — there is no backend history to replay (see useLiveFeed's
// header comment / the Phase 1 audit), so the range slider's max is always
// exactly the highest tick received, never a fabricated "full run" length.
// It is structurally impossible to drag past that point.

import type { LiveFeed } from '../../hooks/useLiveFeed';

export function TickTimeline({ feed }: { feed: LiveFeed }) {
  const { minBufferedTick, maxBufferedTick, displayTick, isLive, scrubTo, stepBack, stepForward, resumeLive } = feed;

  if (minBufferedTick === null || maxBufferedTick === null || displayTick === null) {
    return (
      <div className="mono" style={{ fontSize: 11, color: 'var(--text-2)' }}>
        No ticks received yet — start a simulation to buffer playback data.
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <button onClick={stepBack} disabled={displayTick <= minBufferedTick} title="Step back one buffered tick">
        ⏮
      </button>
      <span
        className="mono"
        style={{
          fontSize: 10,
          fontWeight: 700,
          color: isLive ? 'var(--ok)' : 'var(--status-waiting)',
          border: `1px solid ${isLive ? 'var(--ok)' : 'var(--status-waiting)'}`,
          borderRadius: 2,
          padding: '2px 6px',
          whiteSpace: 'nowrap',
        }}
      >
        {isLive ? '● LIVE' : '⏸ SCRUBBED'}
      </span>

      <input
        type="range"
        min={minBufferedTick}
        max={maxBufferedTick}
        value={displayTick}
        onChange={(e) => scrubTo(Number(e.target.value))}
        style={{ flex: 1 }}
      />

      <span className="mono" style={{ fontSize: 11, minWidth: 90, textAlign: 'right' }}>
        tick {displayTick} / {maxBufferedTick}
      </span>

      <button onClick={stepForward} disabled={displayTick >= maxBufferedTick} title="Step forward — cannot exceed the latest tick actually received">
        ⏭
      </button>

      {!isLive && (
        <button className="primary" onClick={resumeLive} title="Resume following the live feed">
          ▶ RESUME LIVE
        </button>
      )}

      <span className="mono" style={{ fontSize: 9, color: 'var(--text-2)' }}>
        buffered {minBufferedTick}–{maxBufferedTick} (this connection only — no server-side history)
      </span>
    </div>
  );
}

export default TickTimeline;
