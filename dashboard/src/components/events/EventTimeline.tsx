// dashboard/src/components/events/EventTimeline.tsx
// Owner: Member 4
//
// Primary source: feed.allEvents (live-buffered this run, deduplicated by
// eventId, correctly scoped to the current run via useLiveFeed's
// runGeneration reset). Secondary, opt-in source: GET /api/events (approved
// "b-1") — a full persisted log the backend does NOT tag by run/scenario
// (confirmed in the Phase 1 audit), shown only behind an explicit toggle
// and labeled honestly as spanning potentially more than this run, never
// silently merged into the primary (scoped) timeline.
//
// Real event types only: AISLE_BLOCKED, TASK_REASSIGNED, CONFLICT_DETECTED
// (fires only on an actual referee-confirmed collision — labeled precisely,
// not implied to mean "conflict being negotiated", see NEGOTIATION for
// that), NEGOTIATION. DEADLOCK_DETECTED/REROUTE are real contract values
// that are never actually constructed anywhere in the current codebase
// (Phase 1 finding) — filtering by them will legitimately show nothing.

import { useState } from 'react';
import type { LiveFeed } from '../../hooks/useLiveFeed';
import type { SimulationEvent } from '../../types/contracts';
import { fetchEvents, ApiRequestError } from '../../api/client';
import { EmptyState, ErrorState, LoadingState } from '../common/States';

const KNOWN_TYPES = [
  'AISLE_BLOCKED',
  'TASK_REASSIGNED',
  'CONFLICT_DETECTED',
  'NEGOTIATION',
  'DEADLOCK_DETECTED',
  'REROUTE',
  'ROBOT_UNAVAILABLE',
  'TASK_CREATED',
];

const TYPE_COLOR: Record<string, string> = {
  AISLE_BLOCKED: 'var(--status-blocked)',
  TASK_REASSIGNED: 'var(--accent)',
  CONFLICT_DETECTED: 'var(--error)',
  NEGOTIATION: 'var(--status-yield)',
  DEADLOCK_DETECTED: 'var(--status-blocked)',
  REROUTE: 'var(--accent)',
};

function EventRow({ e }: { e: SimulationEvent }) {
  const color = TYPE_COLOR[e.type] ?? 'var(--text-1)';
  return (
    <div
      className="mono"
      style={{ display: 'flex', gap: 8, fontSize: 11, padding: '4px 8px', background: 'var(--surface-2)', borderLeft: `3px solid ${color}` }}
    >
      <span style={{ color: 'var(--text-2)', minWidth: 44 }}>t={e.tick}</span>
      <span style={{ color, fontWeight: 700, minWidth: 130 }}>{e.type}</span>
      <span style={{ color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {JSON.stringify(e.payload)}
      </span>
    </div>
  );
}

export function EventTimeline({ feed }: { feed: LiveFeed }) {
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [showFullLog, setShowFullLog] = useState(false);
  const [fullLog, setFullLog] = useState<SimulationEvent[] | null>(null);
  const [fullLogLoading, setFullLogLoading] = useState(false);
  const [fullLogError, setFullLogError] = useState<string | null>(null);

  const source = showFullLog ? (fullLog ?? []) : feed.allEvents;
  const filtered = typeFilter ? source.filter((e) => e.type === typeFilter) : source;

  const loadFullLog = async () => {
    setFullLogLoading(true);
    setFullLogError(null);
    try {
      const events = await fetchEvents(typeFilter ? { type: typeFilter } : undefined);
      setFullLog(events);
    } catch (e) {
      setFullLogError(e instanceof ApiRequestError ? e.message : String(e));
    } finally {
      setFullLogLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, height: '100%', minHeight: 0 }}>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        <button
          onClick={() => setTypeFilter(null)}
          style={{ background: typeFilter === null ? 'var(--surface-3)' : undefined, fontSize: 10, padding: '3px 7px' }}
        >
          ALL
        </button>
        {KNOWN_TYPES.map((t) => (
          <button
            key={t}
            onClick={() => setTypeFilter(t)}
            style={{ background: typeFilter === t ? 'var(--surface-3)' : undefined, fontSize: 10, padding: '3px 7px' }}
          >
            {t}
          </button>
        ))}
        <span style={{ flex: 1 }} />
        <button
          onClick={() => {
            const next = !showFullLog;
            setShowFullLog(next);
            if (next) loadFullLog();
          }}
          title="GET /api/events — the backend does not tag events by run/scenario, so this spans everything ever persisted, not just this run"
          style={{ fontSize: 10, padding: '3px 7px', color: showFullLog ? 'var(--warn)' : undefined }}
        >
          {showFullLog ? '● FULL PERSISTED LOG (all runs)' : '○ show full persisted log'}
        </button>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 3 }}>
        {showFullLog && fullLogLoading && <LoadingState label="Fetching GET /api/events…" />}
        {showFullLog && fullLogError && <ErrorState title="Failed to fetch event log" detail={fullLogError} />}
        {!fullLogLoading &&
          !fullLogError &&
          (filtered.length === 0 ? (
            <EmptyState
              title="No events"
              detail={
                showFullLog
                  ? 'The backend has no persisted events matching this filter.'
                  : 'No matching events have occurred yet in this run.'
              }
            />
          ) : (
            filtered
              .slice()
              .reverse()
              .map((e) => <EventRow key={e.eventId} e={e} />)
          ))}
      </div>
    </div>
  );
}

export default EventTimeline;
