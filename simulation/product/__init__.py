# simulation/product package — live, seeded "Product" driver.
#
# NOT part of the benchmark or scenario registry. Nothing under
# simulation/scenarios/, simulation/benchmarks/, or the scenario registry
# (simulation/scenarios/__init__.py::get_scenario/list_scenarios) imports
# anything from this package, and nothing here registers a scenario. This
# package only imports FROM simulation.runner (GridAStarPlanner,
# _MessageCountingTransport, _DeadlockCountingDetector) and other existing
# building blocks — it never modifies them.
#
# See docs/PRODUCT_MODE.md for what this driver does and does not do.
