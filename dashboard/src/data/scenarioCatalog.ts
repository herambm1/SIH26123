// dashboard/src/data/scenarioCatalog.ts
// Owner: Member 4
//
// Static mirror of simulation/scenarios/*.py — id, name, description, robot
// count, and scripted-event/fault summary transcribed verbatim from each
// scenario file's own `Scenario(...)` construction and module docstring
// (verified against source during the Phase 1 audit). NOT live-fetched:
// there is no `GET /api/scenarios` endpoint, and this data is genuinely
// static (a scenario's definition never changes at runtime), so mirroring
// it here — rather than inventing a live endpoint for static data — was the
// approach confirmed in Phase 1.6/Phase 2.
//
// If a scenario file changes, this file must be updated to match — it is a
// transcription, not an independent source of truth.

export interface ScenarioCatalogEntry {
  scenarioId: string;
  shortId: string; // single-letter id accepted by simulation.scenarios.get_scenario
  name: string;
  description: string;
  robotCount: number;
  maxTicks: number;
  scriptedEvent: string | null; // human-readable summary of scenario.events, or null
  faultConfig: string | null; // human-readable summary of scenario.fault_config, or null
  category: 'overlapping_path' | 'completion_under_contention' | 'resilience' | 'negative_control';
}

export const SCENARIO_CATALOG: ScenarioCatalogEntry[] = [
  {
    scenarioId: 'a_normal',
    shortId: 'a',
    name: 'Scenario A — Normal Movement',
    description:
      'Robots navigate from their start positions to their goals without any scripted conflict events. Used to verify baseline path planning and movement correctness.',
    robotCount: 2,
    maxTicks: 40,
    scriptedEvent: null,
    faultConfig: null,
    category: 'negative_control',
  },
  {
    scenarioId: 'b_intersection',
    shortId: 'b',
    name: 'Scenario B — Intersection Conflict',
    description:
      'Two robots converge on the same intersection cell at approximately the same tick, triggering conflict detection and deterministic priority resolution.',
    robotCount: 2,
    maxTicks: 40,
    scriptedEvent: null,
    faultConfig: null,
    category: 'overlapping_path',
  },
  {
    scenarioId: 'c_narrow_aisle',
    shortId: 'c',
    name: 'Scenario C — Narrow Aisle Head-On',
    description:
      'Two robots enter a single-file narrow aisle from opposite ends, creating a NARROW_AISLE_HEADON conflict that must be resolved by one robot yielding.',
    robotCount: 2,
    maxTicks: 50,
    scriptedEvent: null,
    faultConfig: null,
    category: 'completion_under_contention',
  },
  {
    scenarioId: 'd_deadlock',
    shortId: 'd',
    name: 'Scenario D — Deadlock',
    description:
      'Multiple robots face each other in a corridor and wait on each other. Tests deadlock detection (5-tick stall heuristic) and forced-yield recovery.',
    robotCount: 2,
    maxTicks: 50,
    scriptedEvent: null,
    faultConfig: 'Message delay: 1 tick (MessageFaultConfig delay_ticks=1)',
    category: 'completion_under_contention',
  },
  {
    scenarioId: 'e_blocked_aisle',
    shortId: 'e',
    name: 'Scenario E — Blocked Aisle',
    description:
      'An aisle becomes blocked mid-simulation (SimulationEvent AISLE_BLOCKED). Affected robots detect the obstacle and dynamically reroute around it.',
    robotCount: 1,
    maxTicks: 50,
    scriptedEvent: 'AISLE_BLOCKED at tick 4, cell (10, 9)',
    faultConfig: null,
    category: 'resilience',
  },
  {
    scenarioId: 'f_task_reassignment',
    shortId: 'f',
    name: 'Scenario F — Task Reassignment',
    description:
      'A robot goes OFFLINE mid-task (via sensorHealth=OFFLINE fault injection). Its in-progress task is automatically reassigned to the next available robot.',
    robotCount: 2,
    maxTicks: 40,
    scriptedEvent: null,
    faultConfig: 'Robot sensor fault: goes OFFLINE mid-run',
    category: 'resilience',
  },
  {
    scenarioId: 'g_high_load',
    shortId: 'g',
    name: 'Scenario G — High Fleet Load',
    description:
      'Maximum number of robots (6 AMRs) operating simultaneously on the dense demo map. Tests throughput and conflict-resolution performance under high concurrency.',
    robotCount: 6,
    maxTicks: 60,
    scriptedEvent: null,
    faultConfig: null,
    category: 'completion_under_contention',
  },
  {
    scenarioId: 'h_negative_control',
    shortId: 'h',
    name: 'Scenario H — Negative Control',
    description:
      'A scenario with no possible conflicts: robots have non-overlapping routes and sufficient space to reach their goals without contention. Preempts "did you cherry-pick scenarios where your system looks good?" by showing zero conflicts are correctly reported when none are structurally possible.',
    robotCount: 3,
    maxTicks: 30,
    scriptedEvent: null,
    faultConfig: null,
    category: 'negative_control',
  },
  {
    scenarioId: 'i_parallel_aisles',
    shortId: 'i',
    name: 'Scenario I — Parallel Aisles',
    description:
      '6 unidirectional AMRs, 3 parallel 8-cell single-file aisles (entrance-tied, one objectively-shortest "direct" lane and two tied "detour" lanes), shared west staging, shared east goal corridor with 6 distinct per-robot goals — tests route-diversity throughput headroom that b_intersection structurally cannot provide. This is the scenario behind the ≥20% SIH proof result (see Benchmark & Proof).',
    robotCount: 6,
    maxTicks: 60,
    scriptedEvent: null,
    faultConfig: null,
    category: 'overlapping_path',
  },
];

export function getScenario(scenarioId: string): ScenarioCatalogEntry | undefined {
  return SCENARIO_CATALOG.find((s) => s.scenarioId === scenarioId);
}
