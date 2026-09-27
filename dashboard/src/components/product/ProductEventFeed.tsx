// dashboard/src/components/product/ProductEventFeed.tsx
//
// Real coordination and task events as they happen, newest first. Same line styling as the Live view's CommunicationFeed (mono row,
// tick, colored left rule, verdict on the right) but covering the whole Product story: robot decisions (NEGOTIATION), task
// lifecycle, injected faults, and referee collisions. Built from real SimulationEvents only; see productDerive.describeEvent for what is
// shown and what is deliberately hidden (per-tick COMM_FLOW, duplicate task lines).

import { useMemo, useState } from 'react';
import type { SimulationEvent } from '../../types/contracts';
import { buildFeed, feedCounts } from './productDerive';
import type { FeedFilter } from './productDerive';

const FILTERS: { key: FeedFilter; label: string }[] = [
  { key: 'ALL', label: 'ALL' },
  { key: 'NEGOTIATION', label: 'NEGOTIATION' },
  { key: 'TASKS', label: 'TASKS' },
  { key: 'FAULTS', label: 'FAULTS' },
  { key: 'COLLISIONS', label: 'COLLISIONS' },
];

export function ProductEventFeed({ events, sessionId }: { events: SimulationEvent[]; sessionId: string | null }) {
  const [filter, setFilter] = useState<FeedFilter>('ALL');
  const counts = useMemo(() => feedCounts(events, sessionId), [events, sessionId]);
  const lines = useMemo(() => buildFeed(events, filter, sessionId), [events, filter, sessionId]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, height: '100%' }} data-testid="event-feed">
      <div style={{ fontSize: 10, letterSpacing: '0.06em', color: 'var(--text-1)', marginBottom: 6 }}>NEGOTIATION &amp; EVENT FEED</div>
      <div style={{ display: 'flex', gap: 3, marginBottom: 6, flexWrap: 'wrap' }}>
        {FILTERS.map((f) => (
          <button
            key={f.key}
            data-testid={`feed-filter-${f.key}`}
            onClick={() => setFilter(f.key)}
            style={{
              fontSize: 10,
              padding: '3px 6px',
              background: filter === f.key ? 'var(--surface-3)' : 'var(--surface-1)',
              borderColor: filter === f.key ? 'var(--accent)' : 'var(--border-1)',
              color: filter === f.key ? 'var(--text-0)' : 'var(--text-1)',
              fontWeight: filter === f.key ? 700 : 400,
            }}
          >
            {f.label} <span className="mono">{counts[f.key]}</span>
          </button>
        ))}
      </div>
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 3 }} data-testid="event-feed-lines">
        {lines.length === 0 ? (
          <div style={{ fontSize: 12, color: 'var(--text-1)' }}>
            {events.length === 0
              ? 'No events yet. Real robot decisions, task changes, injected faults and referee collisions appear here as they happen.'
              : 'No events match this filter yet.'}
          </div>
        ) : (
          lines.map((l) => (
            <div
              key={l.eventId}
              className="mono"
              data-category={l.category}
              style={{
                display: 'flex',
                alignItems: 'baseline',
                gap: 8,
                fontSize: 11,
                padding: '3px 8px',
                background: 'var(--surface-2)',
                borderLeft: `3px solid ${l.color}`,
              }}
            >
              <span style={{ color: 'var(--text-2)', minWidth: 42, flexShrink: 0 }}>t={l.tick}</span>
              <span style={{ color: l.color, fontWeight: 700, minWidth: 92, flexShrink: 0 }}>{l.label}</span>
              <span style={{ flex: 1, wordBreak: 'break-word', color: 'var(--text-0)' }}>{l.text}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default ProductEventFeed;
