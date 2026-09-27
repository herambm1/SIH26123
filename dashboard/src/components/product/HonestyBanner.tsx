// dashboard/src/components/product/HonestyBanner.tsx
//
// Persistent, non-dismissible framing for the Product tab. The audited benchmark figures must never be read as properties of this
// live view: a Product session is a different, exploratory mode (random seed, randomly generated tasks, injected faults) whose
// collisions are counted by the same independent referee but which the audited 0/270 result says nothing about.

export function HonestyBanner() {
  return (
    <div
      role="note"
      data-testid="honesty-banner"
      style={{
        border: '1px solid var(--warn)',
        borderLeft: '4px solid var(--warn)',
        background: 'color-mix(in srgb, var(--warn) 9%, var(--surface-1))',
        padding: '8px 12px',
        fontSize: 12,
        lineHeight: 1.45,
      }}
    >
      <span className="mono" style={{ color: 'var(--warn)', fontWeight: 700, marginRight: 8 }}>
        LIVE, EXPLORATORY DEMO MODE
      </span>
      Each session uses a random seed, randomly generated tasks and randomly injected faults (robots breaking down, blocked aisles, message
      delays). <strong>The audited 0/270 referee-verified collisions and the 21.74% makespan improvement (on i_parallel_aisles) apply only to the
      offline benchmark — see BENCHMARK &amp; PROOF — not to this view.</strong> Collisions here are still counted by the independent referee and
      shown as measured; some sessions have them.
    </div>
  );
}

export default HonestyBanner;
