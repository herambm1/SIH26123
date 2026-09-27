"""Regression guard for the live-demo compatibility bug class found in
CLAUDE.md's live-demo compatibility audit: every scenario's start/goal/
scripted-event-cell positions must be valid (in bounds, not on an obstacle,
reachable) against BOTH the map it actually receives in practice - the real
demo_map.py fallback (the live Java-driven path) AND the explicit benchmark
fixture map (every test/benchmark run).

Uses simulation.scenario_validation.validate_scenario_positions - a
generic, reusable, read-only checker (not a repair mechanism), reused here
rather than reimplemented. This test does not assert anything about
collision-freedom, makespan, or benchmark numbers - it only proves every
scenario's own declared positions are structurally usable.

Owner: Member 3.
"""

import unittest

from simulation.scenarios import list_scenarios, get_scenario
from simulation.scenario_validation import validate_scenario_positions


class TestScenarioPositionValidityAgainstRealDemoMap(unittest.TestCase):
    """The live Java-driven path never supplies a warehouse_map, so every
    scenario falls through to its own get_demo_map() default (except
    i_parallel_aisles, which always uses its own dedicated map regardless)."""

    def test_every_scenario_is_valid_against_the_real_demo_map_fallback(self):
        for sid in list_scenarios():
            with self.subTest(scenario=sid):
                scenario = get_scenario(sid, seed=1, warehouse_map=None)
                problems = validate_scenario_positions(scenario)
                self.assertEqual(problems, [], f"{sid} vs real demo_map.py: {problems}")


class TestScenarioPositionValidityAgainstBenchmarkFixture(unittest.TestCase):
    """The explicit-map path every benchmark run and test actually uses -
    must remain valid (it already was; this is a permanent regression
    guard, not evidence a fix was needed here)."""

    def test_every_scenario_is_valid_against_the_benchmark_fixture_map(self):
        from simulation.benchmarks.benchmark import build_benchmark_warehouse_map

        wm = build_benchmark_warehouse_map()
        for sid in list_scenarios():
            with self.subTest(scenario=sid):
                # i_parallel_aisles deliberately ignores any supplied
                # warehouse_map and always uses its own dedicated map - not
                # part of this audit, per CLAUDE.md.
                scenario = get_scenario(sid, seed=1, warehouse_map=wm)
                problems = validate_scenario_positions(scenario)
                self.assertEqual(problems, [], f"{sid} vs benchmark fixture map: {problems}")


if __name__ == "__main__":
    unittest.main()
