// dashboard/src/components/benchmark/BenchmarkView.tsx
// Owner: Member 4
//
// Phase 6 — Benchmark & Proof view. This is NOT live simulation data: every
// number here is a static transcription of the already-audited, finalized
// 270-run offline benchmark (see data/benchmarkResult.ts's header comment
// for provenance). Nothing on this page is fetched, computed from a live
// run, or recomputed from raw ticks — it exists purely to visualize the
// result that CLAUDE.md/report.md already certify.
//
// Hard constraints this component enforces, per the project's standing
// instruction:
//   - the 21.74% figure is NEVER rendered without "i_parallel_aisles"
//     attached in the same visual unit — see HeadlineCard.
//   - no blended "overall improvement" percentage is computed or shown
//     anywhere on this page (benchmarkResult.ts deliberately exports no
//     such value).
//   - a mode that did not complete a scenario renders the literal label
//     "TIMEOUT / NOT COMPLETED" (from lib/statusColors.ts's existing
//     TIMEOUT status label) — never a fabricated tick count.
//   - the 5 benchmark categories are always rendered as separate sections,
//     never pooled into one table or one number.

import {
  BENCHMARK_RESULTS,
  CATEGORY_1_POOLED_IMPROVEMENT_PERCENT,
  CATEGORY_META,
  HEADLINE_RESULT,
  TOTAL_BENCHMARK_RUNS,
  TOTAL_COLLISIONS,
  type BenchmarkCategory,
  type BenchmarkScenarioResult,
  type ModeResult,
} from '../../data/benchmarkResult';
import { STATUS_LABEL, statusColor } from '../../lib/statusColors';

function ModeCell({ result }: { result: ModeResult }) {
  if (!result.completed) {
    return (
      <span className="mono" style={{ color: statusColor('TIMEOUT'), fontWeight: 700, fontSize: 11 }}>
        {STATUS_LABEL.TIMEOUT}
      </span>
    );
  }
  return (
    <span className="mono" style={{ color: 'var(--text-0)', fontWeight: 700 }}>
      {result.makespanTicks} <span style={{ color: 'var(--text-2)', fontWeight: 400 }}>ticks</span>
    </span>
  );
}

function ImprovementCell({ pct }: { pct: number | null }) {
  if (pct === null) {
    return <span className="mono" style={{ color: 'var(--text-2)', fontSize: 11 }}>n/a — not comparable</span>;
  }
  const positive = pct > 0;
  const color = pct === 0 ? 'var(--text-1)' : positive ? 'var(--ok)' : 'var(--error)';
  const sign = pct > 0 ? '+' : '';
  return (
    <span className="mono" style={{ color, fontWeight: 700 }}>
      {sign}
      {pct.toFixed(2)}%
    </span>
  );
}

function ScenarioRow({ r, highlight }: { r: BenchmarkScenarioResult; highlight?: boolean }) {
  return (
    <tr style={{ background: highlight ? 'var(--accent-dim)' : undefined }}>
      <td style={{ padding: '6px 8px' }}>
        <div className="mono" style={{ fontWeight: 700, fontSize: 12 }}>{r.scenarioId}</div>
        <div style={{ fontSize: 10, color: 'var(--text-1)' }}>{r.name}</div>
      </td>
      <td style={{ padding: '6px 8px', textAlign: 'right' }}>
        <span className="mono" style={{ fontSize: 10, color: 'var(--text-2)' }}>{r.deadlineTicks}</span>
      </td>
      <td style={{ padding: '6px 8px' }}><ModeCell result={r.stopAndWait} /></td>
      <td style={{ padding: '6px 8px' }}><ModeCell result={r.centralizedReservation} /></td>
      <td style={{ padding: '6px 8px' }}><ModeCell result={r.decentralizedProposed} /></td>
      <td style={{ padding: '6px 8px', textAlign: 'right' }}>
        <span className="mono" style={{ fontSize: 11, color: 'var(--text-1)' }}>{r.deadlockActivationsPerRun}</span>
      </td>
      <td style={{ padding: '6px 8px' }}><ImprovementCell pct={r.improvementVsStopAndWaitPercent} /></td>
    </tr>
  );
}

function CategoryTable({ rows }: { rows: BenchmarkScenarioResult[] }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="mono" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ borderBottom: '1px solid var(--border-1)', textAlign: 'left' }}>
            <th style={{ padding: '4px 8px', color: 'var(--text-1)', fontWeight: 500, fontSize: 10 }}>SCENARIO</th>
            <th style={{ padding: '4px 8px', color: 'var(--text-1)', fontWeight: 500, fontSize: 10, textAlign: 'right' }}>DEADLINE</th>
            <th style={{ padding: '4px 8px', color: 'var(--text-1)', fontWeight: 500, fontSize: 10 }}>STOP_AND_WAIT</th>
            <th style={{ padding: '4px 8px', color: 'var(--text-1)', fontWeight: 500, fontSize: 10 }}>CENTRALIZED_RESERVATION</th>
            <th style={{ padding: '4px 8px', color: 'var(--text-1)', fontWeight: 500, fontSize: 10 }}>DECENTRALIZED_PROPOSED</th>
            <th style={{ padding: '4px 8px', color: 'var(--text-1)', fontWeight: 500, fontSize: 10, textAlign: 'right' }}>DEADLOCKS/RUN</th>
            <th style={{ padding: '4px 8px', color: 'var(--text-1)', fontWeight: 500, fontSize: 10 }}>vs STOP_AND_WAIT</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <ScenarioRow key={r.scenarioId} r={r} highlight={r.scenarioId === HEADLINE_RESULT.scenarioId} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CategorySection({ id, label, note }: { id: BenchmarkCategory; label: string; note: string }) {
  const rows = BENCHMARK_RESULTS.filter((r) => r.category === id);
  return (
    <section style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 4 }}>
        <h3 style={{ margin: 0, fontSize: 13, fontWeight: 700 }}>{label}</h3>
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-1)', marginBottom: 8, maxWidth: 780 }}>{note}</div>
      <div style={{ background: 'var(--surface-1)', border: '1px solid var(--border-0)' }}>
        <CategoryTable rows={rows} />
      </div>
    </section>
  );
}

function HeadlineCard() {
  const { stopAndWaitTicks, decentralizedProposedTicks, improvementPercent, scenarioId } = HEADLINE_RESULT;
  return (
    <div
      style={{
        border: '1px solid var(--ok)',
        background: 'var(--surface-1)',
        padding: '18px 20px',
        marginBottom: 16,
      }}
    >
      <div style={{ fontSize: 10, letterSpacing: '0.06em', color: 'var(--text-1)', textTransform: 'uppercase', marginBottom: 8 }}>
        SIH ≥20% makespan-reduction proof — scenario-specific
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, flexWrap: 'wrap' }}>
        <span className="mono" style={{ fontSize: 30, fontWeight: 800, color: 'var(--ok)' }}>
          {improvementPercent}% faster
        </span>
        <span style={{ fontSize: 16, fontWeight: 700 }}>
          in <span className="mono" style={{ color: 'var(--accent)' }}>{scenarioId}</span>
        </span>
      </div>
      <div className="mono" style={{ marginTop: 10, fontSize: 12, color: 'var(--text-1)' }}>
        STOP_AND_WAIT {stopAndWaitTicks} ticks → DECENTRALIZED_PROPOSED {decentralizedProposedTicks} ticks
        {'  '}·{'  '}({stopAndWaitTicks} − {decentralizedProposedTicks}) / {stopAndWaitTicks} × 100 = {improvementPercent}%
      </div>
      <div style={{ marginTop: 10, fontSize: 11, color: 'var(--warn)', maxWidth: 720 }}>
        This is the result for <b>{scenarioId}</b> specifically, reproducible across all 10 audited seeds with 0
        collisions. It is <b>not</b> an overall or system-wide speedup claim — see Category 1 below for why pooling
        it with other overlapping-path scenarios gives a materially lower, still-below-target number.
      </div>
    </div>
  );
}

function CategoryOnePooledNote() {
  return (
    <div
      style={{
        border: '1px dashed var(--border-1)',
        padding: '10px 14px',
        marginBottom: 16,
        fontSize: 11,
        color: 'var(--text-1)',
        maxWidth: 780,
      }}
    >
      <b style={{ color: 'var(--text-0)' }}>Reference only — Category 1 pooled (b_intersection + i_parallel_aisles):</b>{' '}
      <span className="mono" style={{ color: 'var(--warn)', fontWeight: 700 }}>
        {CATEGORY_1_POOLED_IMPROVEMENT_PERCENT}%
      </span>{' '}
      — still below the 20% target. b_intersection has a proven hard makespan floor equal to STOP_AND_WAIT's own
      optimum (a single shared bottleneck cell has no slack for any algorithm to improve on), which necessarily
      drags the pooled figure down. This is shown for completeness, not as the headline — the per-scenario
      i_parallel_aisles result above is the one that meets the target.
    </div>
  );
}

function CollisionSafetySection() {
  return (
    <section style={{ marginBottom: 20 }}>
      <h3 style={{ margin: '0 0 4px', fontSize: 13, fontWeight: 700 }}>4 — Collision Safety</h3>
      <div style={{ fontSize: 11, color: 'var(--text-1)', marginBottom: 8, maxWidth: 780 }}>
        Certified by the independent <span className="mono">CollisionReferee</span> — structurally isolated from{' '}
        <span className="mono">collision_engine</span>'s own detector, so this is a verified result, not a
        circular one. Covers all 9 scenarios, all 3 modes, 10 seeds each.
      </div>
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 10,
          background: 'var(--surface-1)',
          border: '1px solid var(--border-0)',
          padding: '14px 18px',
        }}
      >
        <span className="mono" style={{ fontSize: 26, fontWeight: 800, color: 'var(--ok)' }}>
          {TOTAL_COLLISIONS} / {TOTAL_BENCHMARK_RUNS}
        </span>
        <span style={{ fontSize: 12, color: 'var(--text-1)' }}>referee-verified collisions across every run</span>
      </div>
    </section>
  );
}

export function BenchmarkView() {
  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: '4px 2px 24px' }}>
      <div
        style={{
          display: 'inline-block',
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: '0.06em',
          color: 'var(--warn)',
          border: '1px solid var(--warn)',
          padding: '3px 8px',
          marginBottom: 10,
        }}
      >
        FINALIZED BENCHMARK RESULT — NOT LIVE SIMULATION DATA
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-1)', marginBottom: 16, maxWidth: 780 }}>
        This view visualizes the already-audited, offline 270-run benchmark (9 scenarios × 3 modes × 10 seeds),
        run directly against <span className="mono">simulation.benchmarks.benchmark</span> — no Java backend, no
        dashboard involved in producing it. Nothing on this page is fetched live or recomputed; it is a static
        transcription of the figures already certified in the project report.
      </div>

      <HeadlineCard />
      <CategoryOnePooledNote />

      {/* Rendered in numeric order 1-5: categories 1-3, then 4 (Collision
          Safety, not scenario-subset-filtered — covers all 9), then 5. */}
      {CATEGORY_META.slice(0, 3).map((c) => (
        <CategorySection key={c.id} id={c.id} label={c.label} note={c.note} />
      ))}

      <CollisionSafetySection />

      {CATEGORY_META.slice(3).map((c) => (
        <CategorySection key={c.id} id={c.id} label={c.label} note={c.note} />
      ))}
    </div>
  );
}

export default BenchmarkView;
