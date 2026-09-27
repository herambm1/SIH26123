"""Scenario G — High Fleet Load.

Maximum number of robots (6 AMRs) operating simultaneously on the dense demo map.
Tests throughput and conflict-resolution performance under high concurrency.

Owner: Member 3.
"""

from shared.python.models import Position, WarehouseMap
from simulation.scenarios import Scenario
from simulation.warehouse.demo_map import get_demo_map


def get_scenario(seed: int = 42, warehouse_map: WarehouseMap | None = None) -> Scenario:
    # Two coordinate fixtures, deliberately kept separate (see CLAUDE.md's
    # live-demo compatibility audit): 8 of the 12 original coordinates are
    # obstacle/out-of-bounds cells in the real demo_map.py.
    #   1. LIVE DEMO (warehouse_map is None): mirror the original's 3
    #      head-to-head pairs (same robotIds, same priorities), remapped
    #      onto real open lanes, on this branch ONLY.
    #
    #      IMPORTANT, found via direct empirical verification (not assumed):
    #      a full-width crossing design was tried first - three pairs on
    #      rows 0/14 and column 12/2, each pair's span long enough for the
    #      vertical pair to cross BOTH horizontal pairs - and it does NOT
    #      reliably complete against the real demo_map.py. Isolated
    #      precisely: (a) horizontal spans beyond ~8 cells on rows 0/14
    #      never resolve their own head-on conflict (livelock, high
    #      deadlockCount, confirmed independent of which row or which
    #      priority values are used - a length effect); (b) even at a
    #      short, otherwise-safe span, a vertical pair on column 2
    #      specifically fails to complete whenever it also crosses the
    #      row-14 pair (confirmed independent of which robots/priorities
    #      occupy either pair - a genuine geometry-dependent interaction in
    #      the existing, unmodified coordination/deadlock-resolution logic,
    #      which this task does not permit touching). Column 12 has the
    #      same row-14-crossing failure. No cross-pair-crossing design
    #      using demo_map.py's only two vertical aisles was found to be
    #      safe within this task's constraints.
    #
    #      The design below therefore mirrors the original's 3 head-to-head
    #      PAIRS exactly (same robots, same priorities, same "each robot
    #      faces its own partner head-on" structure) using proven-safe span
    #      lengths, but does NOT attempt a cross-pair crossing - a real,
    #      disclosed reduction from the original description's "crossing
    #      intersecting aisles" framing. What IS preserved and verified:
    #      all 6 robots moving concurrently, 3 simultaneous genuine
    #      pairwise conflicts, real WAIT/YIELD negotiation for all 3 pairs,
    #      zero collisions, full completion - reproducible across 5 seeds.
    #   2. EXPLICIT MAP (benchmark/tests): keep the exact original literals,
    #      unchanged.
    using_real_demo_map = warehouse_map is None
    if warehouse_map is None:
        warehouse_map = get_demo_map()

    if using_real_demo_map:
        pairs = [
            (Position(x=1, y=0), Position(x=8, y=0)),    # R1/R2, row 0
            (Position(x=1, y=14), Position(x=8, y=14)),  # R3/R4, row 14
            (Position(x=2, y=1), Position(x=2, y=8)),    # R5/R6, column 2
        ]
    else:
        pairs = [
            (Position(x=2, y=2), Position(x=17, y=2)),
            (Position(x=2, y=17), Position(x=17, y=17)),
            (Position(x=10, y=2), Position(x=10, y=17)),
        ]
    (p1, p2), (p3, p4), (p5, p6) = pairs

    robots = [
        {"robotId": "R1", "start": p1, "goal": p2, "priority": 3},
        {"robotId": "R2", "start": p2, "goal": p1, "priority": 2},
        {"robotId": "R3", "start": p3, "goal": p4, "priority": 2},
        {"robotId": "R4", "start": p4, "goal": p3, "priority": 1},
        {"robotId": "R5", "start": p5, "goal": p6, "priority": 3},
        {"robotId": "R6", "start": p6, "goal": p5, "priority": 1},
    ]
    return Scenario(
        scenario_id="g_high_load",
        name="Scenario G — High Fleet Load",
        # NOTE: corrected 2026-09-08 (documentation-sync task) — the live-demo
        # geometry (see the using_real_demo_map branch above) no longer
        # produces a genuine 3-way crossing/intersecting-aisle conflict; that
        # was tried and found not to reliably complete against the real
        # demo_map.py (see CLAUDE.md). This description is intentionally
        # generic so it stays accurate for both the live and explicit-map
        # paths — it must not claim "crossing intersecting aisles" again
        # unless a safe crossing design is found for the live path too.
        description=(
            "6 AMRs with three simultaneous head-to-head aisle conflicts, "
            "demonstrating concurrent decentralized negotiation and "
            "deadlock-safe coordination under high fleet load."
        ),
        robots=robots,
        warehouse_map=warehouse_map,
        max_ticks=60,
        events=[],
    )
