// dashboard/src/components/scenario/ScenarioCard.tsx
// Owner: Member 4

import type { ScenarioCatalogEntry } from '../../data/scenarioCatalog';

const CATEGORY_LABEL: Record<ScenarioCatalogEntry['category'], string> = {
  overlapping_path: 'Overlapping-path throughput',
  completion_under_contention: 'Completion under contention',
  resilience: 'Resilience & re-routing',
  negative_control: 'Negative control',
};

export function ScenarioCard({
  entry,
  selected,
  onSelect,
}: {
  entry: ScenarioCatalogEntry;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      style={{
        display: 'block',
        width: '100%',
        textAlign: 'left',
        padding: '8px 10px',
        marginBottom: 4,
        background: selected ? 'var(--surface-3)' : 'var(--surface-2)',
        borderColor: selected ? 'var(--accent)' : 'var(--border-0)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span className="mono" style={{ fontWeight: 700, fontSize: 12 }}>
          {entry.scenarioId}
        </span>
        <span className="mono" style={{ fontSize: 10, color: 'var(--text-1)' }}>
          {entry.robotCount} robot{entry.robotCount === 1 ? '' : 's'} · {entry.maxTicks} max ticks
        </span>
      </div>
      <div style={{ fontSize: 12, fontWeight: 600, margin: '3px 0 2px' }}>{entry.name}</div>
      <div style={{ fontSize: 11, color: 'var(--text-1)', lineHeight: 1.35 }}>{entry.description}</div>
      <div style={{ marginTop: 5, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <span
          className="mono"
          style={{ fontSize: 9, color: 'var(--accent)', border: '1px solid var(--accent-dim)', borderRadius: 2, padding: '1px 5px' }}
        >
          {CATEGORY_LABEL[entry.category]}
        </span>
        {entry.scriptedEvent && (
          <span
            className="mono"
            style={{ fontSize: 9, color: 'var(--status-waiting)', border: '1px solid var(--status-waiting)', borderRadius: 2, padding: '1px 5px' }}
          >
            EVENT: {entry.scriptedEvent}
          </span>
        )}
        {entry.faultConfig && (
          <span
            className="mono"
            style={{ fontSize: 9, color: 'var(--status-offline)', border: '1px solid var(--status-offline)', borderRadius: 2, padding: '1px 5px' }}
          >
            FAULT: {entry.faultConfig}
          </span>
        )}
      </div>
    </button>
  );
}

export default ScenarioCard;
