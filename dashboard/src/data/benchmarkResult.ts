// dashboard/src/data/benchmarkResult.ts
// Owner: Member 4
//
// STATIC MIRROR of the already-audited, finalized offline benchmark result
// — NOT live data, NOT fetched from any endpoint, NOT recomputed by this
// frontend. Every number below is transcribed verbatim from CLAUDE.md /
// report.md's authoritative benchmark sections (the 270-run
// 9-scenario x 3-mode x 10-seed run, independently sanity-checked from
// raw_results.csv). If the benchmark is ever re-run and its documented
// numbers change, this file must be updated to match — it is a
// transcription, not an independent source of truth, exactly like
// data/scenarioCatalog.ts is for scenario definitions.
//
// Hard rule this file exists to enforce in the UI layer: the 21.74%
// i_parallel_aisles result is a SCENARIO-SPECIFIC finding, never an overall
// system speedup. This file deliberately does NOT export any single
// blended "overall improvement" number — BenchmarkView must never compute
// or display one (see CLAUDE.md's "Legacy Reference Aggregate", which is
// explicitly reference-only and is intentionally NOT surfaced here).

export type BenchmarkCategory =
  | 'overlapping_path'
  | 'completion_under_contention'
  | 'resilience'
  | 'negative_control';

export interface ModeResult {
  /** true if this mode reached its destination(s) within the scenario's own max_ticks deadline. */
  completed: boolean;
  /** Ticks to completion — null when completed is false (never a fabricated tick count for a timeout). */
  makespanTicks: number | null;
}

export interface BenchmarkScenarioResult {
  scenarioId: string;
  name: string;
  category: BenchmarkCategory;
  /** The scenario's own max_ticks — the predeclared deadline, unchanged by this feature. */
  deadlineTicks: number;
  stopAndWait: ModeResult;
  centralizedReservation: ModeResult;
  decentralizedProposed: ModeResult;
  /** DeadlockDetector.check()==True activations per run for DECENTRALIZED_PROPOSED — 0 is a real finding, not an omission. */
  deadlockActivationsPerRun: number;
  /**
   * (stopAndWait - decentralizedProposed) / stopAndWait * 100, only when
   * BOTH modes completed (comparable). null means "not a comparable
   * percentage" (e.g. STOP_AND_WAIT timed out) — rendered as such, never
   * defaulted to 0 or omitted silently.
   */
  improvementVsStopAndWaitPercent: number | null;
}

export const BENCHMARK_RESULTS: BenchmarkScenarioResult[] = [
  {
    scenarioId: 'a_normal',
    name: 'Scenario A — Normal Movement',
    category: 'negative_control',
    deadlineTicks: 40,
    stopAndWait: { completed: true, makespanTicks: 6.0 },
    centralizedReservation: { completed: true, makespanTicks: 7.0 },
    decentralizedProposed: { completed: true, makespanTicks: 6.0 },
    deadlockActivationsPerRun: 0,
    improvementVsStopAndWaitPercent: 0.0,
  },
  {
    scenarioId: 'b_intersection',
    name: 'Scenario B — Intersection Conflict',
    category: 'overlapping_path',
    deadlineTicks: 40,
    stopAndWait: { completed: true, makespanTicks: 9.0 },
    centralizedReservation: { completed: true, makespanTicks: 10.0 },
    decentralizedProposed: { completed: true, makespanTicks: 11.0 },
    deadlockActivationsPerRun: 0,
    improvementVsStopAndWaitPercent: -22.22,
  },
  {
    scenarioId: 'c_narrow_aisle',
    name: 'Scenario C — Narrow Aisle Head-On',
    category: 'completion_under_contention',
    deadlineTicks: 50,
    stopAndWait: { completed: false, makespanTicks: null },
    centralizedReservation: { completed: true, makespanTicks: 11.0 },
    decentralizedProposed: { completed: true, makespanTicks: 14.0 },
    deadlockActivationsPerRun: 0,
    improvementVsStopAndWaitPercent: null,
  },
  {
    scenarioId: 'd_deadlock',
    name: 'Scenario D — Deadlock',
    category: 'completion_under_contention',
    deadlineTicks: 50,
    stopAndWait: { completed: false, makespanTicks: null },
    centralizedReservation: { completed: true, makespanTicks: 7.0 },
    decentralizedProposed: { completed: true, makespanTicks: 12.0 },
    deadlockActivationsPerRun: 2,
    improvementVsStopAndWaitPercent: null,
  },
  {
    scenarioId: 'e_blocked_aisle',
    name: 'Scenario E — Blocked Aisle',
    category: 'resilience',
    deadlineTicks: 50,
    stopAndWait: { completed: false, makespanTicks: null },
    centralizedReservation: { completed: false, makespanTicks: null },
    decentralizedProposed: { completed: true, makespanTicks: 16.0 },
    deadlockActivationsPerRun: 0,
    improvementVsStopAndWaitPercent: null,
  },
  {
    scenarioId: 'f_task_reassignment',
    name: 'Scenario F — Task Reassignment',
    category: 'resilience',
    deadlineTicks: 40,
    stopAndWait: { completed: false, makespanTicks: null },
    centralizedReservation: { completed: false, makespanTicks: null },
    decentralizedProposed: { completed: true, makespanTicks: 28.0 },
    deadlockActivationsPerRun: 0,
    improvementVsStopAndWaitPercent: null,
  },
  {
    scenarioId: 'g_high_load',
    name: 'Scenario G — High Fleet Load',
    category: 'completion_under_contention',
    deadlineTicks: 60,
    stopAndWait: { completed: false, makespanTicks: null },
    centralizedReservation: { completed: true, makespanTicks: 18.0 },
    decentralizedProposed: { completed: true, makespanTicks: 28.0 },
    deadlockActivationsPerRun: 4,
    improvementVsStopAndWaitPercent: null,
  },
  {
    scenarioId: 'h_negative_control',
    name: 'Scenario H — Negative Control',
    category: 'negative_control',
    deadlineTicks: 30,
    stopAndWait: { completed: true, makespanTicks: 9.0 },
    centralizedReservation: { completed: true, makespanTicks: 10.0 },
    decentralizedProposed: { completed: true, makespanTicks: 9.0 },
    deadlockActivationsPerRun: 0,
    improvementVsStopAndWaitPercent: 0.0,
  },
  {
    scenarioId: 'i_parallel_aisles',
    name: 'Scenario I — Parallel Aisles',
    category: 'overlapping_path',
    deadlineTicks: 60,
    stopAndWait: { completed: true, makespanTicks: 23.0 },
    centralizedReservation: { completed: true, makespanTicks: 19.0 },
    decentralizedProposed: { completed: true, makespanTicks: 18.0 },
    deadlockActivationsPerRun: 0,
    improvementVsStopAndWaitPercent: 21.74,
  },
];

/** The SIH headline proof — i_parallel_aisles ONLY. Never render this number without the scenario name attached. */
export const HEADLINE_RESULT = {
  scenarioId: 'i_parallel_aisles',
  stopAndWaitTicks: 23,
  decentralizedProposedTicks: 18,
  improvementPercent: 21.74,
} as const;

/**
 * Category 1 pooled (b_intersection + i_parallel_aisles together): 9.38%,
 * still below the 20% target. Shown ONLY as an explicitly-labeled secondary
 * reference next to the headline — never in place of it, and never
 * presented as if it were the proof itself. b_intersection has a proven
 * information-theoretic makespan floor equal to STOP_AND_WAIT's own
 * optimum (a prior session's rigorous proof, kept in Category 1 for
 * historical comparison only), which necessarily drags any pooled figure
 * with it down — this is documented, not hidden.
 */
export const CATEGORY_1_POOLED_IMPROVEMENT_PERCENT = 9.38;

/** Category display metadata, in the order specified for the Benchmark & Proof view. */
export const CATEGORY_META: { id: BenchmarkCategory; label: string; note: string }[] = [
  {
    id: 'overlapping_path',
    label: '1 — Overlapping-Path Throughput',
    note: 'THE primary ≥20% proof metric. b_intersection has a proven hard makespan floor equal to STOP_AND_WAIT’s own optimum (kept for historical comparison only, not expected to meet the target). i_parallel_aisles is where the ≥20% target is met.',
  },
  {
    id: 'completion_under_contention',
    label: '2 — Completion Under Contention',
    note: 'Reliability, not speed — STOP_AND_WAIT structurally times out on all three; both other modes finish every run. Never feeds the ≥20% headline.',
  },
  {
    id: 'resilience',
    label: '3 — Resilience & Re-routing',
    note: 'Event detection & recovery (scripted AISLE_BLOCKED / OFFLINE fault). Both baselines genuinely experience the same event and correctly time out; only DECENTRALIZED_PROPOSED completes. Never feeds the ≥20% headline.',
  },
  {
    id: 'negative_control',
    label: '5 — Negative Controls',
    note: 'No-regression evidence only — routes with no possible contention. Never cited as throughput evidence.',
  },
];

/** Total across the full audited benchmark: 9 scenarios x 3 modes x 10 seeds. */
export const TOTAL_BENCHMARK_RUNS = 270;
export const TOTAL_COLLISIONS = 0;
