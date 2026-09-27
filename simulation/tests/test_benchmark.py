"""Focused tests for simulation/benchmarks/benchmark.py.
Owner: Member 3.
"""
import unittest

from simulation.benchmarks.benchmark import (
    CATEGORY_1_OVERLAPPING_PATH,
    CATEGORY_2_COMPLETION_UNDER_CONTENTION,
    CATEGORY_3_RESILIENCE,
    CATEGORY_5_NEGATIVE_CONTROL,
    MODES,
    RunResult,
    aggregate,
    build_benchmark_warehouse_map,
    build_collision_safety_report,
    build_deadline_task_completion_report,
    build_negative_control_report,
    build_resilience_report,
    build_scenario_comparisons,
    category_pooled_improvement,
    completion_summary,
    improvement_percent,
    run_one,
    sih_verdict,
    unweighted_mean_improvement_for,
)
from simulation.scenarios import list_scenarios


def _r(scenario="a_normal", mode="STOP_AND_WAIT", seed=1, ticks=10, collisions=0,
       deadlocks=0, completed=True, error=None, robot_count=2,
       completed_task_count=None, completed_task_ticks_sum=None, events_observed=0):
    """Build a RunResult. A timed-out run (completed=False) has NO makespan —
    mirrors what run_one() produces for a censored run. Task-completion
    fields default to "every robot completed at the run's own tick count"
    when the run completed, and "nobody completed" when it didn't — callers
    testing task-level nuance (partial completion, reassignment) pass
    explicit values."""
    if completed_task_count is None:
        completed_task_count = robot_count if completed else 0
    if completed_task_ticks_sum is None:
        completed_task_ticks_sum = ticks * completed_task_count
    return RunResult(
        scenarioId=scenario, mode=mode, seed=seed, robotCount=robot_count, maxTicks=40,
        totalCompletionTicks=ticks,
        makespanTicks=ticks if completed else None,
        avgCompletionTicks=float(ticks),
        collisionCount=collisions, deadlockCount=deadlocks, rerouteCount=0,
        idleTicksTotal=0, messageCount=0,
        completed=completed, timedOut=(not completed and error is None),
        completedTaskCount=completed_task_count,
        completedTaskTicksSum=completed_task_ticks_sum,
        eventsObserved=events_observed,
        error=error,
    )


def _three_modes(scenario, saw, cen, dec, saw_done=True, dec_done=True):
    """One scenario's runs across all three modes (comparisons need all three)."""
    return [
        _r(scenario=scenario, mode="STOP_AND_WAIT", ticks=saw, completed=saw_done),
        _r(scenario=scenario, mode="CENTRALIZED_RESERVATION", ticks=cen),
        _r(scenario=scenario, mode="DECENTRALIZED_PROPOSED", ticks=dec, completed=dec_done),
    ]


class ModeAndScenarioEnumerationTests(unittest.TestCase):
    def test_three_modes_exactly(self):
        self.assertEqual(MODES, ["STOP_AND_WAIT", "CENTRALIZED_RESERVATION", "DECENTRALIZED_PROPOSED"])

    def test_nine_scenarios_exactly(self):
        self.assertEqual(len(list_scenarios()), 9)


class BenchmarkCategoryDefinitionTests(unittest.TestCase):
    """The predeclared category scenario lists — PART 2. Fixed BEFORE any
    benchmark run, not chosen after seeing results."""

    def test_category_1_is_exactly_the_two_overlapping_path_scenarios(self):
        self.assertEqual(set(CATEGORY_1_OVERLAPPING_PATH), {"b_intersection", "i_parallel_aisles"})

    def test_category_2_is_exactly_the_three_completion_under_contention_scenarios(self):
        self.assertEqual(set(CATEGORY_2_COMPLETION_UNDER_CONTENTION),
                         {"c_narrow_aisle", "d_deadlock", "g_high_load"})

    def test_category_3_is_exactly_the_two_resilience_scenarios(self):
        self.assertEqual(set(CATEGORY_3_RESILIENCE), {"e_blocked_aisle", "f_task_reassignment"})

    def test_category_5_is_exactly_the_two_negative_controls(self):
        self.assertEqual(set(CATEGORY_5_NEGATIVE_CONTROL), {"a_normal", "h_negative_control"})

    def test_categories_are_disjoint_and_cover_all_nine_scenarios(self):
        parts = [CATEGORY_1_OVERLAPPING_PATH, CATEGORY_2_COMPLETION_UNDER_CONTENTION,
                 CATEGORY_3_RESILIENCE, CATEGORY_5_NEGATIVE_CONTROL]
        all_categorized = set().union(*parts)
        self.assertEqual(sum(len(p) for p in parts), len(all_categorized),
                         "no scenario should appear in two categories")
        self.assertEqual(all_categorized, set(list_scenarios()))


class RunOneMetricExtractionTests(unittest.TestCase):
    def test_run_one_extracts_real_metric_fields(self):
        wm = build_benchmark_warehouse_map()
        result = run_one("a_normal", "DECENTRALIZED_PROPOSED", seed=1, warehouse_map=wm)
        self.assertIsNone(result.error)
        self.assertEqual(result.scenarioId, "a_normal")
        self.assertEqual(result.robotCount, 2)
        self.assertEqual(result.collisionCount, 0)  # a_normal has no conflicts by design

    def test_completed_run_records_a_real_makespan(self):
        """a_normal completes, so it must carry a makespan equal to its final tick."""
        wm = build_benchmark_warehouse_map()
        result = run_one("a_normal", "DECENTRALIZED_PROPOSED", seed=1, warehouse_map=wm)
        self.assertTrue(result.completed)
        self.assertFalse(result.timedOut)
        self.assertIsNotNone(result.makespanTicks)
        self.assertEqual(result.makespanTicks, result.totalCompletionTicks)
        self.assertLess(result.makespanTicks, result.maxTicks)

    def test_timed_out_run_has_no_makespan(self):
        """c_narrow_aisle under STOP_AND_WAIT never finishes. It must be recorded
        as a censored failure, NOT as 'completed in maxTicks ticks'."""
        wm = build_benchmark_warehouse_map()
        result = run_one("c_narrow_aisle", "STOP_AND_WAIT", seed=1, warehouse_map=wm)
        self.assertFalse(result.completed)
        self.assertTrue(result.timedOut)
        self.assertIsNone(result.makespanTicks)
        # The raw final tick is still recorded for traceability, and equals maxTicks.
        self.assertEqual(result.totalCompletionTicks, result.maxTicks)

    def test_run_one_handles_a_failing_combination_without_raising(self):
        wm = build_benchmark_warehouse_map()
        result = run_one("not_a_real_scenario", "DECENTRALIZED_PROPOSED", seed=1, warehouse_map=wm)
        self.assertIsNotNone(result.error)
        self.assertFalse(result.completed)

    def test_run_one_reports_per_task_completion_fields(self):
        """PART 3 — task-level fields must reflect the real, never-fabricated
        per-robot completion truth exposed by SimulationRunner."""
        wm = build_benchmark_warehouse_map()
        result = run_one("a_normal", "DECENTRALIZED_PROPOSED", seed=1, warehouse_map=wm)
        self.assertEqual(result.completedTaskCount, result.robotCount)
        self.assertGreater(result.completedTaskTicksSum, 0)

    def test_run_one_reports_events_observed_for_resilience_scenarios(self):
        wm = build_benchmark_warehouse_map()
        result = run_one("e_blocked_aisle", "DECENTRALIZED_PROPOSED", seed=1, warehouse_map=wm)
        self.assertGreaterEqual(result.eventsObserved, 1)

    def test_run_one_offline_baseline_has_zero_completed_tasks_for_the_dead_robot(self):
        """f_task_reassignment / STOP_AND_WAIT: R1 never completes; this must
        show up as a genuinely incomplete task, never fabricated as done."""
        wm = build_benchmark_warehouse_map()
        result = run_one("f_task_reassignment", "STOP_AND_WAIT", seed=1, warehouse_map=wm)
        self.assertFalse(result.completed)
        self.assertLess(result.completedTaskCount, result.robotCount)


class DeterminismTests(unittest.TestCase):
    def test_same_scenario_mode_seed_produces_identical_result_twice(self):
        wm = build_benchmark_warehouse_map()
        r1 = run_one("b_intersection", "DECENTRALIZED_PROPOSED", seed=7, warehouse_map=wm)
        r2 = run_one("b_intersection", "DECENTRALIZED_PROPOSED", seed=7, warehouse_map=wm)
        self.assertEqual(r1.makespanTicks, r2.makespanTicks)
        self.assertEqual(r1.collisionCount, r2.collisionCount)
        self.assertEqual(r1.deadlockCount, r2.deadlockCount)
        self.assertEqual(r1.messageCount, r2.messageCount)

    def test_centralized_mode_is_reproducible_for_a_fixed_seed(self):
        """Seed now drives centralized planning order, so reproducibility for a
        fixed seed must still hold."""
        wm = build_benchmark_warehouse_map()
        r1 = run_one("g_high_load", "CENTRALIZED_RESERVATION", seed=3, warehouse_map=wm)
        r2 = run_one("g_high_load", "CENTRALIZED_RESERVATION", seed=3, warehouse_map=wm)
        self.assertEqual(r1.makespanTicks, r2.makespanTicks)
        self.assertEqual(r1.collisionCount, r2.collisionCount)


class ImprovementCalculationTests(unittest.TestCase):
    def test_improvement_positive_when_proposed_faster(self):
        self.assertAlmostEqual(improvement_percent(100.0, 80.0), 20.0)

    def test_improvement_negative_when_proposed_slower(self):
        self.assertAlmostEqual(improvement_percent(100.0, 120.0), -20.0)

    def test_improvement_zero_baseline_is_nan_not_a_crash(self):
        result = improvement_percent(0.0, 10.0)
        self.assertNotEqual(result, result)  # NaN != NaN


class AggregationTests(unittest.TestCase):
    def test_aggregate_computes_makespan_stats_over_completed_runs(self):
        results = [_r(ticks=10), _r(ticks=20), _r(ticks=30)]
        aggs = aggregate(results)
        saw = next(a for a in aggs if a.mode == "STOP_AND_WAIT")
        self.assertEqual(saw.n, 3)
        self.assertEqual(saw.successes, 3)
        self.assertEqual(saw.completedRuns, 3)
        self.assertAlmostEqual(saw.completionRate, 1.0)
        self.assertAlmostEqual(saw.meanMakespanCompleted, 20.0)
        self.assertAlmostEqual(saw.medianMakespanCompleted, 20.0)
        self.assertEqual(saw.minMakespanCompleted, 10)
        self.assertEqual(saw.maxMakespanCompleted, 30)

    def test_timed_out_runs_are_excluded_from_makespan_but_counted(self):
        """The core fix: a censored run must not drag a makespan mean around."""
        results = [_r(ticks=10), _r(ticks=40, completed=False)]
        aggs = aggregate(results)
        a = aggs[0]
        self.assertEqual(a.successes, 2)
        self.assertEqual(a.completedRuns, 1)
        self.assertEqual(a.timeoutRuns, 1)
        self.assertAlmostEqual(a.completionRate, 0.5)
        # 10, not 25 — the timeout's maxTicks value is NOT averaged in.
        self.assertAlmostEqual(a.meanMakespanCompleted, 10.0)
        # ...but the raw figure retains it for traceability.
        self.assertAlmostEqual(a.rawMeanFinalTicks, 25.0)

    def test_all_runs_timed_out_gives_no_makespan_at_all(self):
        results = [_r(ticks=40, completed=False), _r(ticks=40, completed=False)]
        aggs = aggregate(results)
        a = aggs[0]
        self.assertEqual(a.completedRuns, 0)
        self.assertAlmostEqual(a.completionRate, 0.0)
        self.assertIsNone(a.meanMakespanCompleted)

    def test_aggregate_excludes_failed_runs_from_stats_but_counts_them(self):
        results = [_r(ticks=10), _r(ticks=20, error="boom")]
        aggs = aggregate(results)
        a = aggs[0]
        self.assertEqual(a.n, 2)
        self.assertEqual(a.successes, 1)
        self.assertAlmostEqual(a.meanMakespanCompleted, 10.0)

    def test_aggregate_counts_collision_and_deadlock_runs(self):
        results = [_r(ticks=10, collisions=1), _r(ticks=10, collisions=0), _r(ticks=10, deadlocks=1)]
        aggs = aggregate(results)
        a = aggs[0]
        self.assertEqual(a.collisionRuns, 1)
        self.assertEqual(a.deadlockRuns, 1)

    def test_aggregate_pools_task_completion_correctly(self):
        """PART 3 — meanCompletedTaskTicks must be an exact pooled mean
        (sum/count across runs), not an average of per-run averages."""
        results = [
            _r(ticks=10, robot_count=2, completed_task_count=2, completed_task_ticks_sum=20),
            _r(ticks=20, robot_count=2, completed_task_count=1, completed_task_ticks_sum=20),
        ]
        aggs = aggregate(results)
        a = aggs[0]
        self.assertEqual(a.totalTasks, 4)
        self.assertEqual(a.completedTasks, 3)
        self.assertAlmostEqual(a.taskCompletionRate, 0.75)
        self.assertAlmostEqual(a.meanCompletedTaskTicks, 40 / 3)

    def test_aggregate_reports_none_mean_completed_task_ticks_when_nobody_completed(self):
        results = [_r(ticks=40, completed=False, completed_task_count=0, completed_task_ticks_sum=0)]
        a = aggregate(results)[0]
        self.assertIsNone(a.meanCompletedTaskTicks)

    def test_aggregate_carries_the_deadline_ticks(self):
        a = aggregate([_r(ticks=10)])[0]
        self.assertEqual(a.deadlineTicks, 40)  # matches _r()'s maxTicks=40


class ScenarioComparisonTests(unittest.TestCase):
    def test_full_matrix_produces_a_comparison_row(self):
        aggs = aggregate(_three_modes("a_normal", saw=100, cen=90, dec=80))
        comparisons = build_scenario_comparisons(aggs)
        self.assertEqual(len(comparisons), 1)
        c = comparisons[0]
        self.assertTrue(c.comparable)
        self.assertAlmostEqual(c.improvementVsStopAndWait, 20.0)
        self.assertAlmostEqual(c.centralizedImprovementVsStopAndWait, 10.0)

    def test_comparison_row_carries_its_category(self):
        aggs = aggregate(_three_modes("b_intersection", saw=100, cen=90, dec=80))
        c = build_scenario_comparisons(aggs)[0]
        self.assertEqual(c.category, "overlapping_path")

        aggs = aggregate(_three_modes("e_blocked_aisle", saw=100, cen=90, dec=80))
        c = build_scenario_comparisons(aggs)[0]
        self.assertEqual(c.category, "resilience")

        aggs = aggregate(_three_modes("a_normal", saw=100, cen=90, dec=80))
        c = build_scenario_comparisons(aggs)[0]
        self.assertEqual(c.category, "negative_control")

    def test_baseline_timeout_makes_scenario_non_comparable(self):
        """The headline case: STOP_AND_WAIT never finishes. No % may be produced
        from its censored value — the completion rate carries the finding."""
        aggs = aggregate(_three_modes("d_deadlock", saw=50, cen=7, dec=12, saw_done=False))
        c = build_scenario_comparisons(aggs)[0]
        self.assertFalse(c.comparable)
        self.assertIsNone(c.improvementVsStopAndWait)
        self.assertAlmostEqual(c.stopAndWaitCompletionRate, 0.0)
        self.assertAlmostEqual(c.decentralizedCompletionRate, 1.0)
        self.assertIn("NOT COMPARABLE", c.note)

    def test_proposed_timeout_makes_scenario_non_comparable(self):
        """The inverse case (f_task_reassignment): the proposed mode is the one
        that fails. It must not be reported as a -400% slowdown."""
        aggs = aggregate(_three_modes("f_task_reassignment", saw=8, cen=9, dec=40, dec_done=False))
        c = build_scenario_comparisons(aggs)[0]
        self.assertFalse(c.comparable)
        self.assertIsNone(c.improvementVsStopAndWait)
        self.assertAlmostEqual(c.decentralizedCompletionRate, 0.0)

    def test_incomplete_matrix_scenario_is_excluded_not_fabricated(self):
        results = [_r(mode="STOP_AND_WAIT", ticks=100), _r(mode="DECENTRALIZED_PROPOSED", ticks=80)]
        comparisons = build_scenario_comparisons(aggregate(results))
        self.assertEqual(comparisons, [])


class CategoryPooledImprovementTests(unittest.TestCase):
    """category_pooled_improvement() — the generalized, scenario-set-scoped
    pooling PART 2 requires. Passing CATEGORY_1_OVERLAPPING_PATH is what
    makes the Category-1 headline exclude Category 3/5 scenarios even when
    their own numbers would otherwise look favorable."""

    def test_pools_across_comparable_scenarios_within_the_given_set(self):
        results = _three_modes("b_intersection", saw=100, cen=100, dec=80) + \
                  _three_modes("g_high_load", saw=200, cen=200, dec=160)
        comparisons = build_scenario_comparisons(aggregate(results))
        pooled = category_pooled_improvement(results, comparisons,
                                             ["b_intersection", "g_high_load"], "test")
        self.assertAlmostEqual(pooled["pooledStopAndWaitMeanMakespan"], 150.0)
        self.assertAlmostEqual(pooled["pooledDecentralizedMeanMakespan"], 120.0)
        self.assertAlmostEqual(pooled["pooledImprovementVsStopAndWait"], 20.0)

    def test_excludes_non_comparable_scenarios_within_the_set(self):
        """A scenario where the baseline timed out must not contribute to the
        percentage at all — this is what previously inflated the headline."""
        results = _three_modes("b_intersection", saw=100, cen=100, dec=80) + \
                  _three_modes("d_deadlock", saw=50, cen=7, dec=12, saw_done=False)
        comparisons = build_scenario_comparisons(aggregate(results))
        pooled = category_pooled_improvement(results, comparisons,
                                             ["b_intersection", "d_deadlock"], "test")
        self.assertEqual(pooled["comparableScenarios"], ["b_intersection"])
        self.assertEqual([e["scenarioId"] for e in pooled["excludedScenarios"]], ["d_deadlock"])
        self.assertAlmostEqual(pooled["pooledStopAndWaitMeanMakespan"], 100.0)
        self.assertAlmostEqual(pooled["pooledImprovementVsStopAndWait"], 20.0)

    def test_a_scenario_outside_the_given_set_is_never_pooled_in(self):
        """This is the core Category-1-vs-everything-else guarantee: a
        favorable Category-5 (negative control) result must not leak into
        a Category-1-only pooling, and vice versa."""
        results = _three_modes("a_normal", saw=100, cen=100, dec=50) + \
                  _three_modes("b_intersection", saw=100, cen=100, dec=95)
        comparisons = build_scenario_comparisons(aggregate(results))
        pooled = category_pooled_improvement(results, comparisons,
                                             CATEGORY_1_OVERLAPPING_PATH, "category1")
        # Only b_intersection is in CATEGORY_1_OVERLAPPING_PATH — a_normal's
        # much better 50% improvement must be completely excluded.
        self.assertEqual(pooled["comparableScenarios"], ["b_intersection"])
        self.assertAlmostEqual(pooled["pooledImprovementVsStopAndWait"], 5.0)

    def test_is_nan_when_nothing_in_the_set_is_comparable(self):
        results = _three_modes("d_deadlock", saw=50, cen=7, dec=12, saw_done=False)
        comparisons = build_scenario_comparisons(aggregate(results))
        pooled = category_pooled_improvement(results, comparisons, ["d_deadlock"], "test")
        value = pooled["pooledImprovementVsStopAndWait"]
        self.assertNotEqual(value, value)  # NaN

    def test_unweighted_mean_is_scoped_to_the_given_set_too(self):
        results = _three_modes("a_normal", saw=100, cen=100, dec=50) + \
                  _three_modes("b_intersection", saw=1000, cen=1000, dec=900)
        comparisons = build_scenario_comparisons(aggregate(results))
        # Only b_intersection is in CATEGORY_1_OVERLAPPING_PATH -> 10%, not (50+10)/2.
        value = unweighted_mean_improvement_for(comparisons, CATEGORY_1_OVERLAPPING_PATH)
        self.assertAlmostEqual(value, 10.0)


class CategoryReportBuilderTests(unittest.TestCase):
    """build_resilience_report / build_negative_control_report /
    build_collision_safety_report / build_deadline_task_completion_report —
    PART 2/3/4's category-scoped report sections."""

    def test_resilience_report_only_contains_category_3_scenarios(self):
        results = _three_modes("e_blocked_aisle", saw=14, cen=15, dec=16) + \
                  _three_modes("b_intersection", saw=9, cen=10, dec=11)
        rows = build_resilience_report(aggregate(results))
        self.assertTrue(all(r["scenarioId"] == "e_blocked_aisle" for r in rows))
        self.assertEqual(len(rows), 3)  # one per mode

    def test_negative_control_report_only_contains_category_5_scenarios(self):
        results = _three_modes("a_normal", saw=6, cen=7, dec=6) + \
                  _three_modes("d_deadlock", saw=50, cen=7, dec=12, saw_done=False)
        rows = build_negative_control_report(aggregate(results))
        self.assertTrue(all(r["scenarioId"] == "a_normal" for r in rows))

    def test_collision_safety_report_covers_every_scenario(self):
        results = _three_modes("a_normal", saw=6, cen=7, dec=6) + \
                  _three_modes("d_deadlock", saw=50, cen=7, dec=12, saw_done=False)
        report = build_collision_safety_report(aggregate(results))
        self.assertEqual(report["totalRuns"], 6)
        self.assertTrue(report["allCollisionFree"])

    def test_collision_safety_report_flags_any_collision(self):
        results = [_r(scenario="a_normal", collisions=1)]
        report = build_collision_safety_report(aggregate(results))
        self.assertFalse(report["allCollisionFree"])
        self.assertEqual(report["collidingRuns"], 1)

    def test_deadline_task_completion_report_covers_every_scenario(self):
        results = _three_modes("a_normal", saw=6, cen=7, dec=6) + \
                  _three_modes("e_blocked_aisle", saw=14, cen=15, dec=16)
        rows = build_deadline_task_completion_report(aggregate(results))
        scenario_ids = {r["scenarioId"] for r in rows}
        self.assertEqual(scenario_ids, {"a_normal", "e_blocked_aisle"})
        for row in rows:
            self.assertEqual(row["deadlineTicks"], 40)  # matches _r()'s maxTicks


class CompletionSummaryTests(unittest.TestCase):
    def test_completion_summary_reports_per_mode_rates(self):
        results = _three_modes("a_normal", saw=100, cen=100, dec=80) + \
                  _three_modes("d_deadlock", saw=50, cen=7, dec=12, saw_done=False)
        cs = completion_summary(aggregate(results))
        self.assertEqual(cs["STOP_AND_WAIT"]["completedRuns"], 1)
        self.assertEqual(cs["STOP_AND_WAIT"]["timeoutRuns"], 1)
        self.assertAlmostEqual(cs["STOP_AND_WAIT"]["completionRate"], 0.5)
        self.assertEqual(cs["DECENTRALIZED_PROPOSED"]["completedRuns"], 2)
        self.assertAlmostEqual(cs["DECENTRALIZED_PROPOSED"]["completionRate"], 1.0)
        self.assertEqual(cs["DECENTRALIZED_PROPOSED"]["scenariosFullyCompleted"], 2)

    def test_completion_summary_can_be_scoped_to_a_scenario_subset(self):
        """CATEGORY 2 — completion under contention restricts this to
        CATEGORY_1_OVERLAPPING_PATH only."""
        results = _three_modes("a_normal", saw=100, cen=100, dec=80) + \
                  _three_modes("d_deadlock", saw=50, cen=7, dec=12, saw_done=False)
        cs = completion_summary(aggregate(results), scenario_ids=["d_deadlock"])
        self.assertEqual(cs["STOP_AND_WAIT"]["runs"], 1)
        self.assertEqual(cs["DECENTRALIZED_PROPOSED"]["completionRate"], 1.0)


class SihVerdictTests(unittest.TestCase):
    """sih_verdict() is now computed EXCLUSIVELY from Category 1
    (overlapping-path) scenarios — using b_intersection (Category 1)
    instead of the old a_normal (Category 5) examples, since a_normal can
    no longer drive the headline at all (see
    test_negative_control_result_never_drives_the_verdict below)."""

    def _verdict(self, results):
        comparisons = build_scenario_comparisons(aggregate(results))
        pooled = category_pooled_improvement(results, comparisons, CATEGORY_1_OVERLAPPING_PATH, "category1")
        return sih_verdict(results, pooled)

    def test_verified_when_improvement_at_least_20_and_no_collisions(self):
        verdict = self._verdict(_three_modes("b_intersection", saw=100, cen=100, dec=79))
        self.assertTrue(verdict.startswith("VERIFIED"))

    def test_not_verified_when_improvement_below_20(self):
        verdict = self._verdict(_three_modes("b_intersection", saw=100, cen=100, dec=90))
        self.assertTrue(verdict.startswith("NOT VERIFIED"))

    def test_not_verified_when_any_decentralized_collision_regardless_of_speed(self):
        results = _three_modes("b_intersection", saw=100, cen=100, dec=10)
        results[-1] = _r(scenario="b_intersection", mode="DECENTRALIZED_PROPOSED", ticks=10, collisions=1)
        verdict = self._verdict(results)
        self.assertTrue(verdict.startswith("NOT VERIFIED"))
        self.assertIn("collision", verdict.lower())

    def test_inconclusive_when_a_run_failed(self):
        results = _three_modes("b_intersection", saw=100, cen=100, dec=10)
        results[-1] = _r(scenario="b_intersection", mode="DECENTRALIZED_PROPOSED", ticks=10, error="crashed")
        verdict = self._verdict(results)
        self.assertTrue(verdict.startswith("INCONCLUSIVE"))

    def test_inconclusive_when_no_category1_scenario_is_comparable(self):
        """Everything timed out somewhere — there is no honest % to report."""
        verdict = self._verdict(_three_modes("d_deadlock", saw=50, cen=7, dec=12, saw_done=False))
        self.assertTrue(verdict.startswith("INCONCLUSIVE"))

    def test_negative_control_result_never_drives_the_verdict(self):
        """PART 5 rule 4/6 in one test: an excellent a_normal (Category 5)
        result must NOT verify the ≥20% claim on its own — only a genuine
        Category-1 (overlapping-path) result can."""
        # a_normal alone: huge improvement, but it's Category 5 — must be INCONCLUSIVE.
        verdict = self._verdict(_three_modes("a_normal", saw=100, cen=100, dec=10))
        self.assertTrue(verdict.startswith("INCONCLUSIVE"))

    def test_resilience_scenario_result_never_drives_the_verdict(self):
        """Same guarantee for Category 3 (e_blocked_aisle/f_task_reassignment)."""
        verdict = self._verdict(_three_modes("e_blocked_aisle", saw=100, cen=100, dec=10))
        self.assertTrue(verdict.startswith("INCONCLUSIVE"))


if __name__ == "__main__":
    unittest.main()
