"""
simulation/benchmarks/benchmark.py — Reproducible 3-mode x 8-scenario benchmark.
Owner: Member 3.

Runs the REAL Python simulation (simulation.runner.SimulationRunner) directly
— no Java backend, no dashboard, no browser required — across every
(scenario, mode, seed) combination and produces:

    <out-dir>/raw_results.csv       one row per individual run
    <out-dir>/summary.json          aggregated stats + improvement %s
    <out-dir>/BENCHMARK_REPORT.md   human-readable report with the SIH verdict

Methodology follows SIH_26123_Project_Overview.md §19 ("Evaluation
Methodology"): same map/task batch/seed per run across modes (paired
comparison), all eight scenarios including the negative control, headline
metric = total makespan (`PerformanceMetric.totalCompletionTicks`) on
DECENTRALIZED_PROPOSED vs. STOP_AND_WAIT specifically; CENTRALIZED_RESERVATION
is supporting evidence only, not the headline claim. Collisions are read from
`PerformanceMetric.collisionCount`, which is always produced by the
independent `CollisionReferee` (`simulation/referee.py`), never by
`collision_engine`'s own detector — see CLAUDE.md "Important Design
Decisions".

BENCHMARK CATEGORIES (see CLAUDE.md "Benchmark Categories" for the full
rationale). The SIH problem statement's ≥20% target is specifically about
"overlapping paths" — it is NOT a claim about every scenario in this repo,
so the headline percentage is deliberately computed over a NARROWER,
predeclared scenario set than "every scenario where the numbers happen to
exist":

  CATEGORY 1 — Overlapping-path throughput (the PRIMARY ≥20% metric):
      b_intersection, c_narrow_aisle, d_deadlock, g_high_load.
  CATEGORY 2 — Completion under contention: completion/timeout rate for the
      SAME Category-1 scenarios — reliability, not speed.
  CATEGORY 3 — Resilience / rerouting / task failure: e_blocked_aisle,
      f_task_reassignment — event-detected / recovered / completed / failed,
      reported separately, never folded into the Category-1 percentage.
  CATEGORY 4 — Collision safety: ALL 8 scenarios, all 3 modes.
  CATEGORY 5 — Negative controls: a_normal, h_negative_control — no-
      regression evidence only, never used as speed evidence for Category 1.

Every scenario is still run, still aggregated, and still shown in the full
per-scenario table — categorization only changes which scenarios feed the
headline ≥20% number, never which scenarios are visible in the report.

CLI usage:
    python -m simulation.benchmarks.benchmark
    python -m simulation.benchmarks.benchmark --scenarios a_normal b_intersection --modes DECENTRALIZED_PROPOSED --seeds 1 2 3
    python -m simulation.benchmarks.benchmark --seeds 1 2 3 4 5 6 7 8 9 10 --out-dir benchmark_results
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from shared.python.models import Position, WarehouseMap
from simulation.runner import SimulationRunner
from simulation.scenarios import get_scenario, list_scenarios

MODES = ["STOP_AND_WAIT", "CENTRALIZED_RESERVATION", "DECENTRALIZED_PROPOSED"]
BASELINE_MODE = "STOP_AND_WAIT"
CENTRALIZED_MODE = "CENTRALIZED_RESERVATION"
PROPOSED_MODE = "DECENTRALIZED_PROPOSED"

# ── Benchmark categories (predeclared — see module docstring) ────────────────
# These scenario-id lists are the experimental design, fixed BEFORE running
# any benchmark, not chosen after seeing results. Do not add/remove a
# scenario from a category to change which numbers land where.
#
# Restructured 2026-09-06 (see CLAUDE_CODE_PROMPT_parallel_aisles_and_final_report.md
# Phase 3): Category 1 — the PRIMARY ≥20% metric — now holds ONLY
# `i_parallel_aisles` (genuine route-diversity headroom, verified via a
# Phase-1 pre-check to have real slack for an algorithm to improve on) and
# `b_intersection` (kept for historical comparison only — proven,
# separately, to have a hard information-theoretic floor equal to
# STOP_AND_WAIT's own optimum, so it can never itself prove the ≥20%
# claim). `c_narrow_aisle`/`d_deadlock`/`g_high_load` move to their OWN
# Category 2 (completion-rate reliability, never a speed percentage) —
# they were never comparable for a % anyway, since STOP_AND_WAIT times out
# on all three; folding them into Category 1's scenario LIST was
# previously harmless only because the pooling logic already excluded
# non-comparable runs, but the category assignment itself was imprecise
# per the SIH statement's specific "overlapping paths" wording. This is a
# measurement-scope correction, not an algorithm change.
CATEGORY_1_OVERLAPPING_PATH = ["b_intersection", "i_parallel_aisles"]
CATEGORY_2_COMPLETION_UNDER_CONTENTION = ["c_narrow_aisle", "d_deadlock", "g_high_load"]
CATEGORY_3_RESILIENCE = ["e_blocked_aisle", "f_task_reassignment"]
CATEGORY_5_NEGATIVE_CONTROL = ["a_normal", "h_negative_control"]

# Non-collision SimulationEvent types that prove a scripted environmental
# event was actually observed this run (as opposed to silently ignored) —
# see RunResult.eventsObserved.
_OBSERVABLE_EVENT_TYPES = {"AISLE_BLOCKED", "TASK_REASSIGNED"}

# Unreachable-but-instantly-refused loopback address (same pattern used by
# simulation/tests/test_runner.py and test_scenarios.py) — every run still
# goes through SimulationRunner's normal resilient _push_to_backend() calls,
# they just fail fast instead of blocking, since no backend is needed to
# benchmark the simulation engine itself.
DEFAULT_BACKEND_URL = "http://127.0.0.1:59999"

DEFAULT_SEEDS = list(range(1, 11))  # 10 seeds — see BENCHMARK_REPORT.md "Methodology" for the runtime estimate that justified this default.


def build_benchmark_warehouse_map(width: int = 20, height: int = 20) -> WarehouseMap:
    """The SAME WarehouseMap fixture simulation/tests/test_scenarios.py and
    test_runner.py already use to validate all 8 scenarios end-to-end —
    reused here rather than reinvented, for exactly the same reason those
    tests use it.

    Disclosed finding (not silently worked around): simulation/warehouse/
    demo_map.py's real get_demo_map() is only 20x15 (gridHeight=15, valid y
    is 0..14), but four of the eight scenario definitions — a_normal,
    f_task_reassignment, g_high_load, h_negative_control — place at least
    one robot's start/goal at y=17 or y=18, outside demo_map.py's real
    bounds. Running those scenarios against the real demo map would make
    GridAStarPlanner.plan() unable to find any path to those out-of-bounds
    goals in EVERY mode identically — not a mode-specific failure, just a
    silently meaningless "everyone times out" number. This is a pre-existing
    inconsistency between Member 1's demo_map.py and Member 3's scenario
    definitions, out of scope to fix in this benchmarking session (recorded
    in CLAUDE.md Known Bugs). Using this larger, already-validated fixture —
    identically for every scenario and every mode — keeps the comparison
    fair (same map for all three modes, same map for all eight scenarios)
    without touching scenario definitions or demo_map.py.
    """
    obstacles: list[Position] = []
    for x in range(width):
        obstacles.append(Position(x=x, y=0))
        obstacles.append(Position(x=x, y=height - 1))
    for y in range(height):
        obstacles.append(Position(x=0, y=y))
        obstacles.append(Position(x=width - 1, y=y))
    for rack_x in [4, 7, 12, 15]:
        for y in range(3, 17):
            if y not in (9, 10):
                obstacles.append(Position(x=rack_x, y=y))
    return WarehouseMap(
        gridWidth=width,
        gridHeight=height,
        obstacles=obstacles,
        chokePoints=[Position(x=10, y=9)],
    )


# ── Single-run execution ────────────────────────────────────────────────────

@dataclass
class RunResult:
    """One benchmark run.

    Completion semantics (the distinction the whole methodology rests on):
      completed=True   — every robot reached its destination; `makespanTicks`
                         holds the real makespan.
      completed=False  — the run hit maxTicks without finishing. This is a task
                         FAILURE, not a slow completion: `makespanTicks` is None
                         (censored/unobserved). `totalCompletionTicks` still
                         records the raw final tick (== maxTicks) purely for
                         traceability — it must never be used as a makespan.

    Per-TASK (per-robot) fields (PART 3 — deadline/task-completion metric,
    distinct from the whole-run makespan above): `maxTicks` doubles as the
    scenario's DEADLINE — a fixed, predeclared, per-scenario tick budget,
    identical for every mode, unchanged by this feature (see module
    docstring / CLAUDE.md "Deadline / Task-Completion Metric"). A robot
    counts toward `completedTaskCount` ONLY if it genuinely reached its own
    CURRENT destination before that deadline — never fabricated, never a
    stale entry from a since-superseded destination (SimulationRunner clears
    that on reassignment). `completedTaskTicksSum` is the sum of those
    robots' completion ticks, so a pooled mean across many runs/seeds can be
    computed exactly (sum/count) without averaging pre-averaged numbers.
    """
    scenarioId: str
    mode: str
    seed: int
    robotCount: int
    maxTicks: int
    totalCompletionTicks: int      # raw final tick; == maxTicks when censored — NOT a makespan
    makespanTicks: int | None      # real makespan, or None when the run did not complete
    avgCompletionTicks: float
    collisionCount: int
    deadlockCount: int             # genuine DeadlockDetector.check() activations
    rerouteCount: int
    idleTicksTotal: int
    messageCount: int
    completed: bool
    timedOut: bool
    completedTaskCount: int        # robots that genuinely reached their OWN current destination
    completedTaskTicksSum: int     # sum of those robots' completion ticks (0 if completedTaskCount==0)
    eventsObserved: int            # count of AISLE_BLOCKED/TASK_REASSIGNED events actually recorded this run
    error: str | None = None


def run_one(
    scenario_id: str,
    mode: str,
    seed: int,
    warehouse_map: WarehouseMap,
    backend_url: str = DEFAULT_BACKEND_URL,
) -> RunResult:
    """Execute exactly one (scenario, mode, seed) combination through the
    real SimulationRunner and capture its real PerformanceMetric — never
    fabricated. A per-combination exception is caught and recorded as a
    failed run (error != None) rather than aborting the whole matrix, per
    "do not silently skip failing combinations" — the failure is reported,
    not hidden.
    """
    runner = SimulationRunner(backend_url=backend_url)
    scenario = None
    try:
        scenario = get_scenario(scenario_id, seed, warehouse_map=warehouse_map)
        metric = runner.run(
            scenario_id,
            mode=mode,
            seed=seed,
            speed="BATCH",  # never LIVE — no real-time throttling/sleep in a benchmark
            max_ticks=scenario.max_ticks,
            warehouse_map=warehouse_map,
        )
    except Exception as exc:  # noqa: BLE001 — a benchmark records a per-combo crash, it doesn't abort the run
        # scenario may be None if get_scenario() itself is what failed (e.g.
        # an unknown scenario_id) — don't assume it was constructed.
        return RunResult(
            scenarioId=scenario_id, mode=mode, seed=seed,
            robotCount=len(scenario.robots) if scenario is not None else -1,
            maxTicks=scenario.max_ticks if scenario is not None else -1,
            totalCompletionTicks=-1, makespanTicks=None, avgCompletionTicks=-1.0,
            collisionCount=-1, deadlockCount=-1, rerouteCount=-1,
            idleTicksTotal=-1, messageCount=-1, completed=False, timedOut=False,
            completedTaskCount=-1, completedTaskTicksSum=-1, eventsObserved=-1,
            error=f"{type(exc).__name__}: {exc}",
        )
    # Authoritative completion signal from the runner itself — set only when the
    # all_done branch broke the tick loop. The old `current_tick < max_ticks`
    # heuristic also misreported a run that legitimately finished ON the last tick.
    completed = runner.last_run_completed
    per_robot_ticks = runner.last_run_completion_ticks_per_robot  # never fabricated — see SimulationRunner docstring
    events_observed = sum(1 for e in runner.events if e.type in _OBSERVABLE_EVENT_TYPES)
    return RunResult(
        scenarioId=scenario_id, mode=mode, seed=seed,
        robotCount=len(scenario.robots), maxTicks=scenario.max_ticks,
        totalCompletionTicks=metric.totalCompletionTicks,
        makespanTicks=metric.totalCompletionTicks if completed else None,
        avgCompletionTicks=metric.avgCompletionTicks,
        collisionCount=metric.collisionCount,
        deadlockCount=metric.deadlockCount,
        rerouteCount=metric.rerouteCount,
        idleTicksTotal=metric.idleTicksTotal,
        messageCount=metric.messageCount,
        completed=completed,
        timedOut=not completed,
        completedTaskCount=len(per_robot_ticks),
        completedTaskTicksSum=sum(per_robot_ticks.values()),
        eventsObserved=events_observed,
    )


def run_matrix(
    scenarios: list[str],
    modes: list[str],
    seeds: list[int],
    warehouse_map: WarehouseMap | None = None,
    backend_url: str = DEFAULT_BACKEND_URL,
    progress=None,
) -> list[RunResult]:
    """Run every (scenario, mode, seed) combination. Same warehouse_map
    instance is used for every combination — the "paired comparison, same
    map/task batch/seed per run" requirement from SIH_26123_Project_Overview.md
    §19."""
    wm = warehouse_map if warehouse_map is not None else build_benchmark_warehouse_map()
    results: list[RunResult] = []
    for sid in scenarios:
        for mode in modes:
            for seed in seeds:
                r = run_one(sid, mode, seed, wm, backend_url=backend_url)
                results.append(r)
                if progress:
                    progress(r)
    return results


# ── Aggregation ──────────────────────────────────────────────────────────

@dataclass
class ScenarioModeAggregate:
    """Per (scenario, mode) stats.

    Makespan statistics are computed over COMPLETED runs only. Timed-out runs
    contribute to completionRate/timeoutRuns and to nothing else — folding
    their censored maxTicks value into a mean would present a task failure as
    a completion latency.

    Task-level fields (PART 3) are pooled correctly across every run/seed in
    this group: totalTasks/completedTasks sum raw per-run counts, and
    meanCompletedTaskTicks is completedTaskTicksSum / completedTasks (exact,
    not an average-of-averages). None when completedTasks == 0 — never a
    fabricated 0 or a maxTicks substitute.
    """
    scenarioId: str
    mode: str
    n: int
    successes: int           # runs with no error
    collisionRuns: int       # runs with collisionCount > 0
    deadlockRuns: int        # runs with deadlockCount > 0
    completedRuns: int
    timeoutRuns: int
    completionRate: float    # completedRuns / successes
    meanMakespanCompleted: float | None
    medianMakespanCompleted: float | None
    minMakespanCompleted: int | None
    maxMakespanCompleted: int | None
    rawMeanFinalTicks: float  # includes censored maxTicks values — traceability only, never a makespan
    deadlineTicks: int        # scenario.max_ticks — identical across modes, the fixed deadline used
    totalTasks: int
    completedTasks: int
    taskCompletionRate: float
    meanCompletedTaskTicks: float | None
    runsWithEventObserved: int  # only meaningful for Category 3 scenarios; 0 elsewhere


def aggregate(results: list[RunResult]) -> list[ScenarioModeAggregate]:
    groups: dict[tuple, list[RunResult]] = defaultdict(list)
    for r in results:
        groups[(r.scenarioId, r.mode)].append(r)

    aggs: list[ScenarioModeAggregate] = []
    for (sid, mode), rs in groups.items():
        ok = [r for r in rs if r.error is None]
        done = [r for r in ok if r.completed and r.makespanTicks is not None]
        makespans = [r.makespanTicks for r in done]
        raw_ticks = [r.totalCompletionTicks for r in ok]
        total_tasks = sum(r.robotCount for r in ok)
        completed_tasks = sum(r.completedTaskCount for r in ok)
        completed_task_ticks_sum = sum(r.completedTaskTicksSum for r in ok)
        aggs.append(ScenarioModeAggregate(
            scenarioId=sid, mode=mode, n=len(rs), successes=len(ok),
            collisionRuns=sum(1 for r in ok if r.collisionCount > 0),
            deadlockRuns=sum(1 for r in ok if r.deadlockCount > 0),
            completedRuns=len(done),
            timeoutRuns=sum(1 for r in ok if r.timedOut),
            completionRate=(len(done) / len(ok)) if ok else 0.0,
            meanMakespanCompleted=statistics.mean(makespans) if makespans else None,
            medianMakespanCompleted=statistics.median(makespans) if makespans else None,
            minMakespanCompleted=min(makespans) if makespans else None,
            maxMakespanCompleted=max(makespans) if makespans else None,
            rawMeanFinalTicks=statistics.mean(raw_ticks) if raw_ticks else float("nan"),
            deadlineTicks=ok[0].maxTicks if ok else (rs[0].maxTicks if rs else -1),
            totalTasks=total_tasks,
            completedTasks=completed_tasks,
            taskCompletionRate=(completed_tasks / total_tasks) if total_tasks else 0.0,
            meanCompletedTaskTicks=(completed_task_ticks_sum / completed_tasks) if completed_tasks else None,
            runsWithEventObserved=sum(1 for r in ok if r.eventsObserved > 0),
        ))
    return sorted(aggs, key=lambda a: (a.scenarioId, a.mode))


def improvement_percent(baseline_mean: float, proposed_mean: float) -> float:
    """(baseline - proposed) / baseline * 100 — positive means proposed is
    faster (fewer ticks) than baseline. Undefined (NaN) if baseline is 0 or
    NaN rather than dividing by zero."""
    if not baseline_mean or baseline_mean != baseline_mean:  # 0 or NaN
        return float("nan")
    return (baseline_mean - proposed_mean) / baseline_mean * 100.0


@dataclass
class ScenarioComparison:
    """Per-scenario comparison.

    A makespan improvement % is only meaningful when BOTH compared modes
    actually completed every run. If either side ever timed out, the run has no
    observed completion time and any ratio built from it would be fiction — so
    `improvementVsStopAndWait` is None and `note` records what happened
    instead. The completion rates carry the real finding in those cases (e.g.
    "baseline completed 0/10, proposed completed 10/10"), which is a stronger
    and more honest statement than a percentage derived from a censored value.

    NOTE: this comparison is computed for EVERY scenario (all 8 stay visible
    in the report, per Part 5 rule 7) — `comparable` alone does NOT mean a
    scenario feeds the SIH headline percentage. Only Category 1 scenarios
    that are ALSO `comparable` do that (see category_pooled_improvement()).
    A comparable Category 3/5 scenario is still reported here for
    transparency, just excluded from the headline by category, not by
    outcome.
    """
    scenarioId: str
    category: str                                # "overlapping_path" | "resilience" | "negative_control"
    stopAndWaitCompletionRate: float
    centralizedCompletionRate: float
    decentralizedCompletionRate: float
    stopAndWaitMeanMakespan: float | None
    centralizedMeanMakespan: float | None
    decentralizedMeanMakespan: float | None
    comparable: bool                            # both baseline and proposed completed 100% of runs
    improvementVsStopAndWait: float | None      # only when comparable — NOT necessarily part of the headline
    centralizedComparable: bool
    centralizedImprovementVsStopAndWait: float | None  # supporting evidence only, per project overview §19
    collisionsDecentralized: int
    deadlocksDecentralized: int
    deadlineTicks: int
    note: str


def _scenario_category(scenario_id: str) -> str:
    if scenario_id in CATEGORY_1_OVERLAPPING_PATH:
        return "overlapping_path"
    if scenario_id in CATEGORY_2_COMPLETION_UNDER_CONTENTION:
        return "completion_under_contention"
    if scenario_id in CATEGORY_3_RESILIENCE:
        return "resilience"
    if scenario_id in CATEGORY_5_NEGATIVE_CONTROL:
        return "negative_control"
    return "other"


def _fully_completed(agg: ScenarioModeAggregate) -> bool:
    return agg.successes > 0 and agg.completedRuns == agg.successes


def build_scenario_comparisons(aggs: list[ScenarioModeAggregate]) -> list[ScenarioComparison]:
    by_scenario: dict[str, dict[str, ScenarioModeAggregate]] = {}
    for a in aggs:
        by_scenario.setdefault(a.scenarioId, {})[a.mode] = a

    comparisons: list[ScenarioComparison] = []
    for sid, by_mode in sorted(by_scenario.items()):
        saw = by_mode.get(BASELINE_MODE)
        cen = by_mode.get(CENTRALIZED_MODE)
        dec = by_mode.get(PROPOSED_MODE)
        if not (saw and cen and dec):
            continue  # incomplete matrix for this scenario — excluded, not fabricated

        comparable = _fully_completed(saw) and _fully_completed(dec)
        cen_comparable = _fully_completed(saw) and _fully_completed(cen)

        if comparable:
            note = "both modes completed every run — makespan comparison valid"
        elif not _fully_completed(saw) and not _fully_completed(dec):
            note = (f"NOT COMPARABLE: both timed out (STOP_AND_WAIT {saw.completedRuns}/{saw.successes}, "
                    f"DECENTRALIZED_PROPOSED {dec.completedRuns}/{dec.successes} completed)")
        elif not _fully_completed(saw):
            note = (f"NOT COMPARABLE: STOP_AND_WAIT failed to complete "
                    f"({saw.completedRuns}/{saw.successes} runs); DECENTRALIZED_PROPOSED completed "
                    f"{dec.completedRuns}/{dec.successes}. Report as a completion-rate win, not a % speedup.")
        else:
            note = (f"NOT COMPARABLE: DECENTRALIZED_PROPOSED failed to complete "
                    f"({dec.completedRuns}/{dec.successes} runs); STOP_AND_WAIT completed "
                    f"{saw.completedRuns}/{saw.successes}.")

        comparisons.append(ScenarioComparison(
            scenarioId=sid,
            category=_scenario_category(sid),
            stopAndWaitCompletionRate=saw.completionRate,
            centralizedCompletionRate=cen.completionRate,
            decentralizedCompletionRate=dec.completionRate,
            stopAndWaitMeanMakespan=saw.meanMakespanCompleted,
            centralizedMeanMakespan=cen.meanMakespanCompleted,
            decentralizedMeanMakespan=dec.meanMakespanCompleted,
            comparable=comparable,
            improvementVsStopAndWait=(
                improvement_percent(saw.meanMakespanCompleted, dec.meanMakespanCompleted)
                if comparable else None
            ),
            centralizedComparable=cen_comparable,
            centralizedImprovementVsStopAndWait=(
                improvement_percent(saw.meanMakespanCompleted, cen.meanMakespanCompleted)
                if cen_comparable else None
            ),
            collisionsDecentralized=dec.collisionRuns,
            deadlocksDecentralized=dec.deadlockRuns,
            deadlineTicks=saw.deadlineTicks if saw.deadlineTicks > 0 else dec.deadlineTicks,
            note=note,
        ))
    return comparisons


def category_pooled_improvement(
    results: list[RunResult],
    comparisons: list[ScenarioComparison],
    scenario_ids: list[str],
    basis_label: str,
) -> dict:
    """Run-weighted improvement, pooled over COMPARABLE scenarios WITHIN a
    predeclared scenario_ids set. This is the generalized form of the old
    "pool over every comparable scenario" behavior — used with
    CATEGORY_1_OVERLAPPING_PATH for the actual SIH headline, and can be
    called with the full scenario list for the legacy/reference view (see
    build_summary()). "Comparable" = both STOP_AND_WAIT and
    DECENTRALIZED_PROPOSED completed every run of that scenario. Scenarios
    in scenario_ids that are NOT comparable are excluded from the percentage
    entirely and listed in `excludedScenarios` with the reason.
    """
    in_scope = {c.scenarioId for c in comparisons if c.scenarioId in scenario_ids}
    comparable_ids = {c.scenarioId for c in comparisons if c.scenarioId in in_scope and c.comparable}
    excluded = [{"scenarioId": c.scenarioId, "reason": c.note}
                for c in comparisons if c.scenarioId in in_scope and not c.comparable]

    ok = [r for r in results
          if r.error is None and r.completed and r.makespanTicks is not None
          and r.scenarioId in comparable_ids]
    by_mode: dict[str, list[int]] = defaultdict(list)
    for r in ok:
        by_mode[r.mode].append(r.makespanTicks)

    saw = by_mode.get(BASELINE_MODE, [])
    cen = by_mode.get(CENTRALIZED_MODE, [])
    dec = by_mode.get(PROPOSED_MODE, [])
    saw_mean = statistics.mean(saw) if saw else float("nan")
    cen_mean = statistics.mean(cen) if cen else float("nan")
    dec_mean = statistics.mean(dec) if dec else float("nan")
    return {
        "basis": basis_label,
        "scenarioSet": sorted(in_scope),
        "comparableScenarios": sorted(comparable_ids),
        "excludedScenarios": excluded,
        "pooledStopAndWaitMeanMakespan": saw_mean,
        "pooledCentralizedMeanMakespan": cen_mean,
        "pooledDecentralizedMeanMakespan": dec_mean,
        "pooledImprovementVsStopAndWait": improvement_percent(saw_mean, dec_mean),
        "pooledCentralizedImprovementVsStopAndWait": improvement_percent(saw_mean, cen_mean),
        "pooledRunCount": {"STOP_AND_WAIT": len(saw), "CENTRALIZED_RESERVATION": len(cen), "DECENTRALIZED_PROPOSED": len(dec)},
    }


def unweighted_mean_improvement_for(comparisons: list[ScenarioComparison], scenario_ids: list[str]) -> float:
    """Mean of each COMPARABLE scenario's own improvement percentage, within
    scenario_ids only (every such scenario counts equally, regardless of its
    tick scale) — as opposed to category_pooled_improvement()'s run-weighted
    pooling. Returns NaN if no in-scope scenario is comparable."""
    values = [c.improvementVsStopAndWait for c in comparisons
              if c.scenarioId in scenario_ids and c.improvementVsStopAndWait is not None]
    return statistics.mean(values) if values else float("nan")


def completion_summary(aggs: list[ScenarioModeAggregate], scenario_ids: list[str] | None = None) -> dict:
    """Completion rate per mode — the metric that carries the real result for
    scenarios a percentage cannot describe (baseline never finishes, proposed
    does). Deliberately separate from any makespan number.

    scenario_ids restricts this to a subset (e.g. CATEGORY_1_OVERLAPPING_PATH
    for "completion under contention" — Category 2); None (default) means
    every scenario, used for the whole-benchmark completion-rate table.
    """
    scope = set(scenario_ids) if scenario_ids is not None else None
    by_mode: dict[str, dict] = {}
    for mode in MODES:
        mode_aggs = [a for a in aggs if a.mode == mode and (scope is None or a.scenarioId in scope)]
        total = sum(a.successes for a in mode_aggs)
        done = sum(a.completedRuns for a in mode_aggs)
        n_scenarios = len(scope) if scope is not None else len({a.scenarioId for a in aggs})
        by_mode[mode] = {
            "runs": total,
            "completedRuns": done,
            "timeoutRuns": sum(a.timeoutRuns for a in mode_aggs),
            "completionRate": (done / total) if total else 0.0,
            "scenariosFullyCompleted": sum(1 for a in mode_aggs if _fully_completed(a)),
            "scenariosWithAnyTimeout": sum(1 for a in mode_aggs if a.timeoutRuns > 0),
            "scenarioCount": n_scenarios,
        }
    return by_mode


# ── Category-level report builders (PART 2) ─────────────────────────────────

def build_resilience_report(aggs: list[ScenarioModeAggregate]) -> list[dict]:
    """CATEGORY 3 — per (scenario, mode) resilience breakdown for
    e_blocked_aisle/f_task_reassignment: was the scripted event actually
    observed, did the mode recover (complete), and if not, is that a real,
    honestly-reported failure. NEVER folded into the Category-1 percentage."""
    rows = []
    for a in aggs:
        if a.scenarioId not in CATEGORY_3_RESILIENCE:
            continue
        rows.append({
            "scenarioId": a.scenarioId,
            "mode": a.mode,
            "eventObserved": a.runsWithEventObserved == a.successes and a.successes > 0,
            "runsWithEventObserved": a.runsWithEventObserved,
            "totalRuns": a.successes,
            "completionRate": a.completionRate,
            "completedRuns": a.completedRuns,
            "timeoutRuns": a.timeoutRuns,
            "meanMakespanWhenCompleted": a.meanMakespanCompleted,
            "deadlineTicks": a.deadlineTicks,
            "collisionRuns": a.collisionRuns,
        })
    return sorted(rows, key=lambda r: (r["scenarioId"], r["mode"]))


def build_negative_control_report(aggs: list[ScenarioModeAggregate]) -> list[dict]:
    """CATEGORY 5 — a_normal/h_negative_control's own numbers, reported as
    no-regression evidence ONLY. Never cited as Category-1 speed evidence."""
    rows = []
    for a in aggs:
        if a.scenarioId not in CATEGORY_5_NEGATIVE_CONTROL:
            continue
        rows.append({
            "scenarioId": a.scenarioId,
            "mode": a.mode,
            "completionRate": a.completionRate,
            "meanMakespanCompleted": a.meanMakespanCompleted,
            "collisionRuns": a.collisionRuns,
            "deadlockRuns": a.deadlockRuns,
        })
    return sorted(rows, key=lambda r: (r["scenarioId"], r["mode"]))


def build_collision_safety_report(aggs: list[ScenarioModeAggregate]) -> dict:
    """CATEGORY 4 — collision safety across ALL 8 scenarios, all 3 modes.
    Must remain 0 regardless of every other category's outcome."""
    total_runs = sum(a.successes for a in aggs)
    colliding_runs = sum(a.collisionRuns for a in aggs)
    by_mode: dict[str, dict] = {}
    for mode in MODES:
        mode_aggs = [a for a in aggs if a.mode == mode]
        by_mode[mode] = {
            "runs": sum(a.successes for a in mode_aggs),
            "collidingRuns": sum(a.collisionRuns for a in mode_aggs),
        }
    return {
        "totalRuns": total_runs,
        "collidingRuns": colliding_runs,
        "allCollisionFree": colliding_runs == 0,
        "byMode": by_mode,
    }


def build_deadline_task_completion_report(aggs: list[ScenarioModeAggregate]) -> list[dict]:
    """PART 3/4 — per (scenario, mode) deadline/task-completion table, ALL 8
    scenarios. A "task" here is one robot's own assignment; deadline is the
    scenario's fixed, predeclared max_ticks (identical for every mode — see
    RunResult docstring). Never counts an unfinished task as completed;
    never substitutes a timeout for a completion time."""
    rows = []
    for a in aggs:
        rows.append({
            "scenarioId": a.scenarioId,
            "mode": a.mode,
            "deadlineTicks": a.deadlineTicks,
            "runCompletionRate": a.completionRate,
            "runsCompleted": a.completedRuns,
            "runsTimedOut": a.timeoutRuns,
            "meanMakespanCompletedRuns": a.meanMakespanCompleted,
            "totalTasks": a.totalTasks,
            "completedTasks": a.completedTasks,
            "failedOrTimedOutTasks": a.totalTasks - a.completedTasks,
            "taskCompletionRate": a.taskCompletionRate,
            "meanCompletedTaskTicks": a.meanCompletedTaskTicks,
        })
    return sorted(rows, key=lambda r: (r["scenarioId"], r["mode"]))


# ── SIH ≥20% verdict (CATEGORY 1 ONLY) ───────────────────────────────────

def sih_verdict(results: list[RunResult], category1_pooled: dict) -> str:
    """Never manufactures a pass. Computed EXCLUSIVELY from
    CATEGORY_1_OVERLAPPING_PATH's pooled result — the SIH statement's ≥20%
    target is specifically about "overlapping paths", so resilience
    (Category 3) and negative-control (Category 5) scenarios must never be
    used to inflate or substitute for this number, even if their own
    numbers happen to be favorable. Three possible outcomes: VERIFIED /
    NOT VERIFIED / INCONCLUSIVE."""
    failed = [r for r in results if r.error is not None]
    if failed:
        return (f"INCONCLUSIVE — {len(failed)}/{len(results)} (scenario, mode, seed) combinations "
                f"failed to run; see raw_results.csv for exact failures.")

    decentralized = [r for r in results if r.mode == PROPOSED_MODE]
    colliding = [r for r in decentralized if r.collisionCount > 0]
    if colliding:
        return (f"NOT VERIFIED — {len(colliding)}/{len(decentralized)} DECENTRALIZED_PROPOSED runs "
                f"had a referee-verified collision (collisionCount > 0); the zero-collision requirement "
                f"takes precedence over the makespan number.")

    headline = category1_pooled["pooledImprovementVsStopAndWait"]
    n_comparable = len(category1_pooled.get("comparableScenarios", []))
    n_excluded = len(category1_pooled.get("excludedScenarios", []))
    scope = (f" (Category 1 — overlapping-path throughput only: {n_comparable} comparable scenario(s) "
             f"of {len(CATEGORY_1_OVERLAPPING_PATH)}; {n_excluded} excluded because a mode failed to "
             f"complete — see completionUnderContention)")
    if headline != headline:  # NaN
        return ("INCONCLUSIVE — no Category-1 overlapping-path scenario had both STOP_AND_WAIT and "
                "DECENTRALIZED_PROPOSED complete every run, so no valid makespan comparison exists" + scope + ".")
    if headline >= 20.0:
        return f"VERIFIED — makespan improvement {headline:.2f}% >= 20% target{scope}."
    return f"NOT VERIFIED — makespan improvement {headline:.2f}% is below the 20% target{scope}."


# ── Output ───────────────────────────────────────────────────────────────

def write_csv(results: list[RunResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(results[0]).keys()) if results else [
        "scenarioId", "mode", "seed", "robotCount", "maxTicks", "totalCompletionTicks",
        "avgCompletionTicks", "collisionCount", "deadlockCount", "rerouteCount",
        "idleTicksTotal", "messageCount", "completed", "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(asdict(r))


def build_summary(
    results: list[RunResult],
    aggs: list[ScenarioModeAggregate],
    comparisons: list[ScenarioComparison],
    elapsed_seconds: float,
    scenarios: list[str],
    modes: list[str],
    seeds: list[int],
) -> dict:
    failed = [r for r in results if r.error is not None]
    decentralized = [r for r in results if r.mode == PROPOSED_MODE and r.error is None]
    matrix_ok = {(sid, mode): any(r.scenarioId == sid and r.mode == mode and r.error is None for r in results)
                 for sid in scenarios for mode in modes}

    # PRIMARY metric — Category 1 (overlapping-path throughput) ONLY.
    category1_pooled = category_pooled_improvement(
        results, comparisons, CATEGORY_1_OVERLAPPING_PATH,
        basis_label="completed runs of Category-1 (overlapping-path) scenarios where BOTH "
                     "baseline and proposed completed every run",
    )
    category1_unweighted = unweighted_mean_improvement_for(comparisons, CATEGORY_1_OVERLAPPING_PATH)

    # Legacy/reference view — pooled over EVERY comparable scenario regardless
    # of category. Shown for continuity/transparency (Part 5 rule 7: keep
    # every scenario visible) but is explicitly NOT the SIH headline anymore.
    all_scenario_pooled = category_pooled_improvement(
        results, comparisons, scenarios,
        basis_label="completed runs of ANY scenario where BOTH baseline and proposed completed every "
                     "run (reference/legacy view — NOT the SIH headline, see overlappingPathThroughput)",
    )
    all_scenario_unweighted = unweighted_mean_improvement_for(comparisons, scenarios)

    return {
        "methodology": {
            "scenarios": scenarios,
            "modes": modes,
            "seeds": seeds,
            "runsTotal": len(results),
            "warehouseMap": "simulation/benchmarks/benchmark.py:build_benchmark_warehouse_map() (20x20 fixture — see its docstring)",
            "makespanDefinition": "ticks to complete, recorded ONLY for runs that actually completed (every robot at its destination). A run that hits maxTicks is a task failure with NO makespan — it is censored, never counted as a completion time.",
            "improvementBasis": "the PRIMARY ≥20% metric is pooled ONLY over Category 1 (overlapping-path) scenarios that are also comparable (both modes complete every run) — see overlappingPathThroughput. A legacy all-scenario pooling is also shown for reference, never as the headline.",
            "collisionDefinition": "PerformanceMetric.collisionCount, produced by the independent CollisionReferee (simulation/referee.py), never collision_engine's own count",
            "deadlockDefinition": "PerformanceMetric.deadlockCount == genuine DeadlockDetector.check() activations (forced deadlock recoveries), counted by a pass-through wrapper in simulation/runner.py",
            "stoppingCondition": "all robots IDLE or at destination (all_done), else scenario.max_ticks",
            "deadlineDefinition": "each scenario's own scenario.max_ticks — fixed and predeclared before this benchmark ran, identical for every mode, unchanged by the deadline/task-completion feature. A task (one robot's own assignment) is COMPLETED only if it reaches its own current destination before this deadline; otherwise FAILED/TIMED OUT. Never converted into a fake completion time.",
            "categories": {
                "category1_overlapping_path_throughput": CATEGORY_1_OVERLAPPING_PATH,
                "category2_completion_under_contention": CATEGORY_2_COMPLETION_UNDER_CONTENTION,
                "category3_resilience": CATEGORY_3_RESILIENCE,
                "category4_collision_safety": "all scenarios",
                "category5_negative_controls": CATEGORY_5_NEGATIVE_CONTROL,
            },
        },
        "elapsedSeconds": elapsed_seconds,
        "matrixCoverage": {
            "expectedCombinations": len(scenarios) * len(modes),
            "combinationsWithAtLeastOneSuccess": sum(1 for ok in matrix_ok.values() if ok),
            "allScenarioModeCombinationsRan": all(matrix_ok.values()),
            "failedRuns": len(failed),
            "failedRunDetails": [{"scenarioId": r.scenarioId, "mode": r.mode, "seed": r.seed, "error": r.error} for r in failed],
        },
        # CATEGORY 4 — collision safety, ALL scenarios.
        "collisionSafety": build_collision_safety_report(aggs),
        "collisionSummary": {  # kept for backward compatibility with older tooling/readers
            "decentralizedRuns": len(decentralized),
            "decentralizedCollisionFreeRuns": sum(1 for r in decentralized if r.collisionCount == 0),
            "decentralizedAllCollisionFree": all(r.collisionCount == 0 for r in decentralized) if decentralized else False,
            "decentralizedDeadlockRuns": sum(1 for r in decentralized if r.deadlockCount > 0),
        },
        "completionSummary": completion_summary(aggs),  # all scenarios — whole-benchmark reference
        "scenarioModeAggregates": [asdict(a) for a in aggs],
        "scenarioComparisons": [asdict(c) for c in comparisons],
        # CATEGORY 1 — the PRIMARY ≥20% metric.
        "overlappingPathThroughput": {
            "scenarios": CATEGORY_1_OVERLAPPING_PATH,
            "pooled": category1_pooled,
            "unweightedMeanImprovementVsStopAndWait": category1_unweighted,
        },
        # CATEGORY 2 — completion under contention (its own scenario set,
        # separate from Category 1 since 2026-09-06 — see the category
        # definitions above).
        "completionUnderContention": completion_summary(aggs, CATEGORY_2_COMPLETION_UNDER_CONTENTION),
        # CATEGORY 3 — resilience / rerouting / task failure.
        "resilience": build_resilience_report(aggs),
        # CATEGORY 5 — negative controls (no-regression evidence only).
        "negativeControls": build_negative_control_report(aggs),
        # PART 3/4 — deadline / task-completion metric, all 8 scenarios.
        "deadlineTaskCompletion": build_deadline_task_completion_report(aggs),
        # Legacy/reference pooling (NOT the headline — kept for continuity).
        "pooledAggregate": all_scenario_pooled,
        "unweightedMeanImprovementVsStopAndWait": all_scenario_unweighted,
        "sihVerdict": sih_verdict(results, category1_pooled),
    }


def render_markdown_report(summary: dict) -> str:
    m = summary["methodology"]
    lines = []
    lines.append("# SIH 26123 Benchmark\n")
    lines.append("## Methodology\n")
    lines.append(f"- Scenarios: {', '.join(m['scenarios'])} ({len(m['scenarios'])} total)")
    lines.append(f"- Modes: {', '.join(m['modes'])}")
    lines.append(f"- Seeds: {m['seeds']} ({len(m['seeds'])} per scenario/mode)")
    lines.append(f"- Total runs: {summary['methodology']['runsTotal']}")
    lines.append(f"- Warehouse map: {m['warehouseMap']}")
    lines.append(f"- Makespan definition: {m['makespanDefinition']}")
    lines.append(f"- Improvement basis (PRIMARY metric): {m['improvementBasis']}")
    lines.append(f"- Collision definition: {m['collisionDefinition']}")
    lines.append(f"- Deadlock definition: {m['deadlockDefinition']}")
    lines.append(f"- Stopping condition: {m['stoppingCondition']}")
    lines.append(f"- Deadline / task-completion definition: {m['deadlineDefinition']}")
    lines.append(f"- Elapsed wall-clock time: {summary['elapsedSeconds']:.1f}s\n")

    lines.append("### Benchmark categories\n")
    lines.append("| Category | Purpose | Scenarios |")
    lines.append("|---|---|---|")
    lines.append(f"| 1 — Overlapping-path throughput | PRIMARY ≥20% metric | {', '.join(CATEGORY_1_OVERLAPPING_PATH)} |")
    lines.append(f"| 2 — Completion under contention | Reliability, not speed | {', '.join(CATEGORY_2_COMPLETION_UNDER_CONTENTION)} |")
    lines.append(f"| 3 — Resilience / rerouting / task failure | Event detection & recovery, NOT folded into Category 1 | {', '.join(CATEGORY_3_RESILIENCE)} |")
    lines.append("| 4 — Collision safety | Must remain 0 | all scenarios |")
    lines.append(f"| 5 — Negative controls | No-regression evidence ONLY | {', '.join(CATEGORY_5_NEGATIVE_CONTROL)} |")
    lines.append("")

    def _fmt(v, suffix="", nd=1):
        return "—" if v is None else f"{v:.{nd}f}{suffix}"

    lines.append("## Completion Rates (all 8 scenarios, reference)\n")
    lines.append("Whether the task was finished at all, before any talk of speed. A run that hits maxTicks is a failure, not a slow completion.\n")
    lines.append("| Mode | Completed runs | Timeouts | Completion rate | Scenarios fully completed |")
    lines.append("|---|---|---|---|---|")
    for mode, cs in summary["completionSummary"].items():
        lines.append(f"| {mode} | {cs['completedRuns']}/{cs['runs']} | {cs['timeoutRuns']} | "
                     f"{cs['completionRate'] * 100:.1f}% | {cs['scenariosFullyCompleted']}/{len(m['scenarios'])} |")
    lines.append("")

    lines.append("## Scenario Results (all 8, per-scenario 3-way comparison)\n")
    lines.append("Mean makespan is over COMPLETED runs only; `—` means no run of that mode completed. "
                 "Improvement is shown only where both compared modes completed every run. `Category` shows "
                 "which benchmark category this scenario belongs to — only `overlapping_path` rows feed the "
                 "SIH headline percentage below.\n")
    lines.append("| Scenario | Category | Deadline | SAW completion | SAW makespan | CEN makespan | DEC completion | DEC makespan | Improvement vs SAW | Collisions (DEC) | Deadlock runs (DEC) |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for c in summary["scenarioComparisons"]:
        imp = "n/a" if c["improvementVsStopAndWait"] is None else f"{c['improvementVsStopAndWait']:+.1f}%"
        lines.append(
            f"| {c['scenarioId']} | {c['category']} | {c['deadlineTicks']} | {c['stopAndWaitCompletionRate'] * 100:.0f}% | {_fmt(c['stopAndWaitMeanMakespan'])} | "
            f"{_fmt(c['centralizedMeanMakespan'])} | {c['decentralizedCompletionRate'] * 100:.0f}% | "
            f"{_fmt(c['decentralizedMeanMakespan'])} | {imp} | "
            f"{c['collisionsDecentralized']} | {c['deadlocksDecentralized']} |"
        )
    lines.append("")

    non_comparable = [c for c in summary["scenarioComparisons"] if not c["comparable"]]
    if non_comparable:
        lines.append("### Scenarios not comparable for a % speedup (and why)\n")
        for c in non_comparable:
            lines.append(f"- **{c['scenarioId']}** ({c['category']}) — {c['note']}")
        lines.append("")

    # ── CATEGORY 1 — PRIMARY ≥20% METRIC ───────────────────────────────
    lines.append("## CATEGORY 1 — Overlapping-Path Throughput (PRIMARY ≥20% metric)\n")
    lines.append(f"In-scope scenarios: {', '.join(CATEGORY_1_OVERLAPPING_PATH)} — the SIH statement's "
                 "\"overlapping paths\" contention scenarios.\n")
    p = summary["overlappingPathThroughput"]["pooled"]
    lines.append(f"- Basis: {p['basis']}")
    lines.append(f"- Comparable scenarios (both modes complete every run): {', '.join(p['comparableScenarios']) or 'none'}")
    if p["excludedScenarios"]:
        lines.append("- Excluded from this percentage (a mode failed to complete):")
        for e in p["excludedScenarios"]:
            lines.append(f"  - **{e['scenarioId']}** — {e['reason']}")
    lines.append(f"- **Pooled** STOP_AND_WAIT mean makespan: {_fmt(p['pooledStopAndWaitMeanMakespan'])} ticks")
    lines.append(f"- **Pooled** CENTRALIZED_RESERVATION mean makespan: {_fmt(p['pooledCentralizedMeanMakespan'])} ticks")
    lines.append(f"- **Pooled** DECENTRALIZED_PROPOSED mean makespan: {_fmt(p['pooledDecentralizedMeanMakespan'])} ticks")
    lines.append(f"- **Pooled improvement vs STOP_AND_WAIT: {_fmt(p['pooledImprovementVsStopAndWait'], '%', 2)}** (run-weighted, Category 1 comparable scenarios only) — **THIS IS THE SIH HEADLINE NUMBER**")
    lines.append(f"- CENTRALIZED_RESERVATION improvement vs STOP_AND_WAIT: {_fmt(p['pooledCentralizedImprovementVsStopAndWait'], '%', 2)} (supporting evidence only)")
    lines.append(f"- Unweighted mean of per-scenario improvements: {_fmt(summary['overlappingPathThroughput']['unweightedMeanImprovementVsStopAndWait'], '%', 2)} (each comparable Category-1 scenario counts equally)")
    lines.append("")

    # ── CATEGORY 2 — COMPLETION UNDER CONTENTION ────────────────────────
    lines.append("## CATEGORY 2 — Completion Under Contention (reliability, NOT the ≥20% metric)\n")
    lines.append(f"Own scenario set, separate from Category 1 ({', '.join(CATEGORY_2_COMPLETION_UNDER_CONTENTION)}) "
                 "— none of these are comparable for a % speedup (STOP_AND_WAIT times out on all three), so this "
                 "reports whether the fleet actually finishes under contention, independent of speed.\n")
    lines.append("| Mode | Completed runs | Timeouts | Completion rate | Scenarios fully completed |")
    lines.append("|---|---|---|---|---|")
    for mode, cs in summary["completionUnderContention"].items():
        lines.append(f"| {mode} | {cs['completedRuns']}/{cs['runs']} | {cs['timeoutRuns']} | "
                     f"{cs['completionRate'] * 100:.1f}% | {cs['scenariosFullyCompleted']}/{cs['scenarioCount']} |")
    lines.append("")

    # ── CATEGORY 3 — RESILIENCE ──────────────────────────────────────────
    lines.append("## CATEGORY 3 — Resilience / Rerouting / Task Failure (NOT folded into Category 1)\n")
    lines.append(f"Scenarios: {', '.join(CATEGORY_3_RESILIENCE)}. `Event observed` confirms every run of that "
                 "mode genuinely saw the scripted fault (not silently ignored) — see CLAUDE.md \"Benchmark "
                 "Fairness — Identical Event Exposure\".\n")
    lines.append("| Scenario | Mode | Event observed | Completion rate | Completed | Timed out | Mean makespan (completed) | Deadline | Collisions |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in summary["resilience"]:
        lines.append(
            f"| {r['scenarioId']} | {r['mode']} | {'YES' if r['eventObserved'] else 'no'} | "
            f"{r['completionRate'] * 100:.0f}% | {r['completedRuns']}/{r['totalRuns']} | {r['timeoutRuns']} | "
            f"{_fmt(r['meanMakespanWhenCompleted'])} | {r['deadlineTicks']} | {r['collisionRuns']} |"
        )
    lines.append("")

    # ── CATEGORY 4 — COLLISION SAFETY ────────────────────────────────────
    lines.append("## CATEGORY 4 — Collision Safety (all 8 scenarios, all 3 modes)\n")
    cs4 = summary["collisionSafety"]
    lines.append(f"- Total runs: {cs4['totalRuns']}, colliding runs: {cs4['collidingRuns']} — "
                 f"**{'ALL COLLISION-FREE' if cs4['allCollisionFree'] else 'COLLISIONS OBSERVED'}**")
    lines.append("| Mode | Runs | Colliding runs |")
    lines.append("|---|---|---|")
    for mode, d in cs4["byMode"].items():
        lines.append(f"| {mode} | {d['runs']} | {d['collidingRuns']} |")
    lines.append("")

    # ── CATEGORY 5 — NEGATIVE CONTROLS ───────────────────────────────────
    lines.append("## CATEGORY 5 — Negative Controls (no-regression evidence ONLY)\n")
    lines.append(f"Scenarios: {', '.join(CATEGORY_5_NEGATIVE_CONTROL)}. These have no overlapping-path "
                 "contention by design — used to confirm no regression when there is nothing to contend "
                 "over, NEVER cited as evidence for the Category-1 speed claim.\n")
    lines.append("| Scenario | Mode | Completion rate | Mean makespan | Collisions | Deadlocks |")
    lines.append("|---|---|---|---|---|---|")
    for r in summary["negativeControls"]:
        lines.append(
            f"| {r['scenarioId']} | {r['mode']} | {r['completionRate'] * 100:.0f}% | "
            f"{_fmt(r['meanMakespanCompleted'])} | {r['collisionRuns']} | {r['deadlockRuns']} |"
        )
    lines.append("")

    # ── PART 3/4 — DEADLINE / TASK-COMPLETION MATRIX ─────────────────────
    lines.append("## Deadline / Task-Completion Matrix (all 8 scenarios — SECONDARY operational metric)\n")
    lines.append("This is a SEPARATE, secondary metric from the Category-1 ≥20% makespan claim above. A "
                 "\"task\" is one robot's own assignment; the deadline is that scenario's own fixed "
                 "`max_ticks` (identical for every mode). A task that misses the deadline is FAILED, never "
                 "counted as completed, and never converted into a fake completion time.\n")
    lines.append("| Scenario | Mode | Completion Rate | Completed Task Time / Makespan | Failed/Timed-Out Tasks | Deadline | Runs Timed Out |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in summary["deadlineTaskCompletion"]:
        task_time = _fmt(r["meanCompletedTaskTicks"]) if r["meanCompletedTaskTicks"] is not None else "—"
        lines.append(
            f"| {r['scenarioId']} | {r['mode']} | {r['taskCompletionRate'] * 100:.0f}% "
            f"({r['completedTasks']}/{r['totalTasks']} tasks) | {task_time} | "
            f"{r['failedOrTimedOutTasks']} | {r['deadlineTicks']} | {r['runsTimedOut']} |"
        )
    lines.append("")

    lines.append("## Legacy Reference Aggregate (ALL comparable scenarios, regardless of category — NOT the SIH headline)\n")
    lp = summary["pooledAggregate"]
    lines.append(f"- Basis: {lp['basis']}")
    lines.append(f"- Comparable scenarios: {', '.join(lp['comparableScenarios']) or 'none'}")
    lines.append(f"- Pooled improvement vs STOP_AND_WAIT: {_fmt(lp['pooledImprovementVsStopAndWait'], '%', 2)} (reference only)")
    lines.append(f"- Unweighted mean: {_fmt(summary['unweightedMeanImprovementVsStopAndWait'], '%', 2)} (reference only)")
    mc = summary["matrixCoverage"]
    lines.append(f"- 3-mode x 8-scenario matrix coverage: {mc['combinationsWithAtLeastOneSuccess']}/{mc['expectedCombinations']} "
                 f"combinations ran successfully at least once ({'ALL RAN' if mc['allScenarioModeCombinationsRan'] else 'SOME FAILED — see below'})")
    if mc["failedRunDetails"]:
        lines.append("\n### Failed runs\n")
        lines.append("| Scenario | Mode | Seed | Error |")
        lines.append("|---|---|---|---|")
        for f in mc["failedRunDetails"]:
            lines.append(f"| {f['scenarioId']} | {f['mode']} | {f['seed']} | {f['error']} |")
    lines.append("")

    lines.append("## SIH Requirement (CATEGORY 1 ONLY)\n")
    lines.append(f"**{summary['sihVerdict']}**\n")

    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description="SIH 26123 three-mode x eight-scenario reproducible benchmark.")
    parser.add_argument("--scenarios", nargs="+", default=list_scenarios(), help="Scenario IDs to run (default: all 8).")
    parser.add_argument("--modes", nargs="+", default=list(MODES), help="Modes to run (default: all 3).")
    parser.add_argument("--seeds", nargs="+", type=int, default=DEFAULT_SEEDS, help="Seeds to run per scenario/mode (default: 1..10).")
    parser.add_argument("--out-dir", default="benchmark_results", help="Output directory (default: benchmark_results/).")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL, help="Backend URL for resilient pushes (default: an unreachable loopback port — no real backend needed).")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-run progress lines.")
    args = parser.parse_args(argv)

    wm = build_benchmark_warehouse_map()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    total = len(args.scenarios) * len(args.modes) * len(args.seeds)
    done = 0
    start = time.time()

    def progress(r: RunResult) -> None:
        nonlocal done
        done += 1
        if args.quiet:
            return
        status = "OK" if r.error is None else f"FAILED: {r.error}"
        makespan = "TIMEOUT" if r.makespanTicks is None else f"{r.makespanTicks}"
        print(f"[{done}/{total}] {r.scenarioId:22s} {r.mode:24s} seed={r.seed:<3d} "
              f"makespan={makespan:<8s} collisions={r.collisionCount:<2d} "
              f"deadlocks={r.deadlockCount:<2d} {status}")

    results = run_matrix(args.scenarios, args.modes, args.seeds, warehouse_map=wm,
                          backend_url=args.backend_url, progress=progress)
    elapsed = time.time() - start

    write_csv(results, out_dir / "raw_results.csv")
    aggs = aggregate(results)
    comparisons = build_scenario_comparisons(aggs)
    summary = build_summary(results, aggs, comparisons, elapsed, args.scenarios, args.modes, args.seeds)

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    report_md = render_markdown_report(summary)
    (out_dir / "BENCHMARK_REPORT.md").write_text(report_md, encoding="utf-8")

    if not args.quiet:
        print(f"\nDone in {elapsed:.1f}s. Results written to {out_dir}/")
        print(f"SIH verdict: {summary['sihVerdict']}")

    return summary


if __name__ == "__main__":
    main()
