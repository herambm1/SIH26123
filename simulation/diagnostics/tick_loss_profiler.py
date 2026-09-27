"""
simulation/diagnostics/tick_loss_profiler.py — PHASE 1 instrumentation for
the decentralized-coordination throughput experiment (see
CLAUDE_CODE_PROMPT_throughput_experiment.md).

Purely observational. This module monkeypatches a handful of methods on
RobotAgent / ConflictDetector / ConflictResolver / GridAStarPlanner for the
duration of a single profiling run (restored immediately after via a context
manager), so it can attribute every tick a robot does not make goal-progress
to a cause. It does NOT modify simulation/runner.py, robot_agent/agent.py,
collision_engine/, the benchmark methodology, or any scenario definition —
nothing here is imported by production code, and running the real benchmark
(simulation.benchmarks.benchmark) is completely unaffected whether or not
this module has ever been imported.

Attribution model
------------------
For each robot, from tick=1 to the tick it reaches ITS OWN destination (or
the scenario's max_ticks if it never does):

    total_ticks_observed = moving_ticks + wait_ticks
    moving_ticks          = ticks where ground-truth position actually changed
    ideal_ticks           = shortest-path length ignoring every other robot
                            (static-obstacle-only A*, computed once per robot
                            from its own start/goal — GridAStarPlanner.plan()
                            with no blocked_cells/avoid_intervals)
    detour_extra_ticks    = max(0, moving_ticks - ideal_ticks)
                            — extra cells actually travelled beyond the
                              shortest possible route (a real detour, not a
                              wait)
    wait_ticks            = total_ticks_observed - moving_ticks, subdivided
                            into buckets by what was true on that specific
                            non-progress tick:
        conflict_wait      — ConflictDetector.detect() found a conflict this
                             tick (whatever the resolver then decided)
        residual_wait      — status stayed WAITING with NO conflict detected
                             this tick (peer-physical-occupancy guard, or a
                             resume-on-clear check that hasn't cleared yet)
        blocked_or_noplan  — status BLOCKED (scripted blocked cell, or the
                             planner had nothing to give this tick)
        deadlock_recovery  — NOT mutually exclusive with the three above;
                             counted separately whenever DeadlockDetector's
                             escape (_force_yield()) fired on this exact tick
        other_stall        — anything else with no position change (OFFLINE,
                             already-IDLE bookkeeping, etc.)

Replans and yields
------------------
Every YIELD/REROUTE resolver verdict and every _force_yield() deadlock
escape is recorded as a "replan trigger" with the cell it caused the robot
to avoid and the peer it was attributed to. Post-hoc, each trigger is
checked against the peer's ACTUAL logged ground-truth trajectory: if the
peer was never actually at the avoided cell in the tick window the trigger
predicted, the replan is flagged "unnecessary" (the broadcast intent that
caused it was stale/conservative, not a real future conflict). This is an
approximation (a small window is used, not a full counterfactual re-run of
"what would have happened without replanning"), and is reported as such.

Every WAIT/YIELD/REROUTE verdict is also recorded as a "yield event" with
both robots' remaining shortest-path cost-to-goal (static BFS distance from
each robot's own destination, computed once per scenario) at the moment of
the decision — this is what lets Phase 2 test the "wrong robot yields"
hypothesis.

Usage
-----
    python -m simulation.diagnostics.tick_loss_profiler
    python -m simulation.diagnostics.tick_loss_profiler --scenarios b_intersection --seeds 1 2 3
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from shared.python.models import Position, WarehouseMap
import robot_agent.agent as agent_mod
import collision_engine.detection as detection_mod
import collision_engine.resolution as resolution_mod
import simulation.runner as runner_mod
from simulation.runner import SimulationRunner
from simulation.scenarios import get_scenario
from simulation.benchmarks.benchmark import build_benchmark_warehouse_map

DEFAULT_SCENARIOS = ["b_intersection", "c_narrow_aisle", "d_deadlock", "g_high_load"]
DEFAULT_SEEDS = list(range(1, 11))
BACKEND_URL = "http://127.0.0.1:59999"  # instantly-refused loopback — no real backend needed


# ── Static-obstacle-only distance maps (ignore every other robot) ───────────

def _bfs_dist_from(warehouse_map: WarehouseMap, origin: Position) -> dict:
    """Flood-fill distance (in ticks) from `origin` to every reachable cell,
    over static obstacles ONLY — no peers, no runtime blocked cells. Used
    both as the "ideal path length" (distance from a robot's start to its
    goal) and as "remaining cost-to-goal" (distance from any cell to a
    robot's destination, since the same map is symmetric under 4-connected
    unweighted movement)."""
    obstacles = {(o.x, o.y) for o in (warehouse_map.obstacles or [])}
    w, h = warehouse_map.gridWidth, warehouse_map.gridHeight
    start = (origin.x, origin.y)
    dist = {start: 0}
    q = collections.deque([start])
    while q:
        cx, cy = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            if (nx, ny) in obstacles or (nx, ny) in dist:
                continue
            dist[(nx, ny)] = dist[(cx, cy)] + 1
            q.append((nx, ny))
    return dist


# ── Profiler state + monkeypatches ───────────────────────────────────────────

class TickLossProfiler:
    def __init__(self, dist_from_goal: dict):
        self.dist_from_goal = dist_from_goal  # {robotId: {(x,y): dist}}
        self.tick_events: list[dict] = []
        self.yield_events: list[dict] = []
        self.replan_events: list[dict] = []
        self.reset_only_deadlock_events: list[dict] = []
        self.planner_calls_during_run = 0
        self._ctx_tick: int = 0
        self._current: dict | None = None  # scratch for the in-flight tick() call


_ACTIVE: TickLossProfiler | None = None

_orig_tick = agent_mod.RobotAgent.tick
_orig_force_yield = agent_mod.RobotAgent._force_yield
_orig_detect = detection_mod.ConflictDetector.detect
_orig_resolve = resolution_mod.ConflictResolver.resolve
_orig_planner_plan = runner_mod.GridAStarPlanner.plan


def _patched_tick(self, current_tick):
    prof = _ACTIVE
    if prof is None:
        return _orig_tick(self, current_tick)
    pos_before = (self.state.position.x, self.state.position.y) if self.state else None
    status_before = self.state.status if self.state else None
    prof._ctx_tick = current_tick
    prof._current = {"conflict_type": None, "action": None, "peer_id": None, "deadlock_fired": False}
    result = _orig_tick(self, current_tick)
    cur = prof._current
    prof.tick_events.append({
        "robot_id": self.robot_id, "tick": current_tick,
        "pos_before": pos_before, "pos_after": (result.position.x, result.position.y),
        "status_before": status_before, "status_after": result.status,
        "conflict_type": cur["conflict_type"], "action": cur["action"],
        "peer_id": cur["peer_id"], "deadlock_fired": cur["deadlock_fired"],
    })
    prof._current = None
    return result


def _patched_detect(self, own_state, own_path, peer_intents):
    conflict = _orig_detect(self, own_state, own_path, peer_intents)
    prof = _ACTIVE
    if prof is not None and prof._current is not None and conflict is not None:
        prof._current["conflict_type"] = conflict.type
    return conflict


def _patched_resolve(self, conflict, own_state, peer_intents):
    action = _orig_resolve(self, conflict, own_state, peer_intents)
    prof = _ACTIVE
    if prof is not None and prof._current is not None:
        peer_id = next((rid for rid in conflict.robotIds if rid != own_state.robotId), None)
        prof._current["action"] = action
        prof._current["peer_id"] = peer_id
        if action in ("WAIT", "YIELD", "REROUTE"):
            peer = next((p for p in peer_intents if p.get("robotId") == peer_id), {})
            peer_pos = peer.get("position") or {}
            own_map = prof.dist_from_goal.get(own_state.robotId, {})
            peer_map = prof.dist_from_goal.get(peer_id, {})
            own_remaining = own_map.get((own_state.position.x, own_state.position.y))
            peer_remaining = (
                peer_map.get((peer_pos.get("x"), peer_pos.get("y")))
                if peer_pos.get("x") is not None else None
            )
            prof.yield_events.append({
                "tick": prof._ctx_tick, "own_id": own_state.robotId, "peer_id": peer_id or "?",
                "action": action, "own_remaining": own_remaining, "peer_remaining": peer_remaining,
                "conflict_type": conflict.type, "predicted_tick": conflict.predictedTick,
                "next_waypoint_tick": (own_state.currentPath[0].tick if own_state.currentPath else None),
            })
        if action in ("YIELD", "REROUTE") and conflict.predictedCell is not None:
            prof.replan_events.append({
                "tick": prof._ctx_tick, "robot_id": own_state.robotId, "trigger": action.lower(),
                "avoided_cell": (conflict.predictedCell.x, conflict.predictedCell.y),
                "peer_id": peer_id, "predicted_tick": conflict.predictedTick,
            })
    return action


def _patched_force_yield(self):
    prof = _ACTIVE
    if prof is not None and prof._current is not None:
        prof._current["deadlock_fired"] = True
        # _force_yield() only actually adds an avoid-cell/detour when
        # _should_step_aside() is True (the lower-priority robot in the
        # standoff) — the higher-priority robot's call just resets its
        # stall/waiting state and retries the SAME path (see Known Bugs #3 /
        # agent.py::_force_yield docstring). Calling _should_step_aside()
        # here is read-only (only compares priorities/robotId), so this
        # replicates the real branch instead of assuming every force_yield
        # is a reroute — a reset-only call is recorded separately, not as a
        # replan trigger, to avoid overstating "unnecessary reroutes".
        steps_aside = self._should_step_aside()
        peer_id = self._blocked_by_peer or self._waiting_on
        if steps_aside and self.state and self.state.currentPath:
            wp = self.state.currentPath[0]
            prof.replan_events.append({
                "tick": prof._ctx_tick, "robot_id": self.robot_id, "trigger": "force_yield",
                "avoided_cell": (wp.x, wp.y), "peer_id": peer_id, "predicted_tick": prof._ctx_tick + 1,
            })
        else:
            prof.reset_only_deadlock_events.append({
                "tick": prof._ctx_tick, "robot_id": self.robot_id, "peer_id": peer_id,
            })
    return _orig_force_yield(self)


def _patched_planner_plan(self, start, goal, blocked_cells=None, avoid_intervals=None, start_tick=0):
    prof = _ACTIVE
    if prof is not None and prof._current is not None:
        prof.planner_calls_during_run += 1
    return _orig_planner_plan(self, start, goal, blocked_cells, avoid_intervals, start_tick)


class _Patches:
    """Applies every monkeypatch on __enter__, restores the originals on
    __exit__ unconditionally — even if the run raises."""

    def __enter__(self):
        agent_mod.RobotAgent.tick = _patched_tick
        agent_mod.RobotAgent._force_yield = _patched_force_yield
        detection_mod.ConflictDetector.detect = _patched_detect
        resolution_mod.ConflictResolver.resolve = _patched_resolve
        runner_mod.GridAStarPlanner.plan = _patched_planner_plan
        return self

    def __exit__(self, *exc_info):
        agent_mod.RobotAgent.tick = _orig_tick
        agent_mod.RobotAgent._force_yield = _orig_force_yield
        detection_mod.ConflictDetector.detect = _orig_detect
        resolution_mod.ConflictResolver.resolve = _orig_resolve
        runner_mod.GridAStarPlanner.plan = _orig_planner_plan
        return False


# ── Per-tick bucket classification ───────────────────────────────────────────

def _bucket(ev: dict) -> str:
    if ev["pos_before"] != ev["pos_after"]:
        return "progress"
    status = ev["status_after"]
    if status == "OFFLINE":
        return "offline"
    if ev["conflict_type"] is not None:
        return "conflict_wait"
    if status == "WAITING":
        return "residual_wait"
    if status == "BLOCKED":
        return "blocked_or_noplan"
    if status == "IDLE":
        return "idle_done"
    return "other_stall"


# ── One (scenario, seed) profiling run ───────────────────────────────────────

def profile_one(scenario_id: str, seed: int, warehouse_map: WarehouseMap) -> dict:
    global _ACTIVE
    scenario = get_scenario(scenario_id, seed, warehouse_map=warehouse_map)

    dist_from_goal = {
        r["robotId"]: _bfs_dist_from(scenario.warehouse_map, r["goal"])
        for r in scenario.robots
    }
    ideal_ticks = {
        r["robotId"]: dist_from_goal[r["robotId"]].get((r["start"].x, r["start"].y))
        for r in scenario.robots
    }

    prof = TickLossProfiler(dist_from_goal)
    runner = SimulationRunner(backend_url=BACKEND_URL)
    _ACTIVE = prof
    try:
        with _Patches():
            metric = runner.run(
                scenario_id, mode="DECENTRALIZED_PROPOSED", seed=seed,
                speed="BATCH", max_ticks=scenario.max_ticks, warehouse_map=warehouse_map,
            )
    finally:
        _ACTIVE = None

    completed = runner.last_run_completed
    completion_ticks = dict(runner.last_run_completion_ticks_per_robot)
    final_tick = runner.current_tick

    per_robot = {}
    for r in scenario.robots:
        rid = r["robotId"]
        arrival = completion_ticks.get(rid, final_tick)
        events = [e for e in prof.tick_events if e["robot_id"] == rid and e["tick"] <= arrival]
        buckets = collections.Counter()
        moving_ticks = 0
        deadlock_recovery_ticks = 0
        for e in events:
            b = _bucket(e)
            if e["deadlock_fired"]:
                deadlock_recovery_ticks += 1
            if b == "progress":
                moving_ticks += 1
            elif b != "idle_done":
                buckets[b] += 1
        ideal = ideal_ticks[rid] or 0
        detour_extra = max(0, moving_ticks - ideal)
        per_robot[rid] = {
            "reachedDestination": rid in completion_ticks,
            "arrivalTick": completion_ticks.get(rid),
            "totalTicksObserved": len(events),
            "movingTicks": moving_ticks,
            "idealTicks": ideal,
            "detourExtraTicks": detour_extra,
            "waitBuckets": dict(buckets),
            "deadlockRecoveryTicks": deadlock_recovery_ticks,
        }

    # Post-hoc necessity check for each replan trigger.
    unnecessary = 0
    for rp in prof.replan_events:
        if rp["avoided_cell"] is None or rp["peer_id"] is None:
            continue
        peer_events = [e for e in prof.tick_events if e["robot_id"] == rp["peer_id"]]
        window_end = (rp["predicted_tick"] or rp["tick"]) + 1
        was_there = any(
            rp["tick"] <= e["tick"] <= window_end and e["pos_after"] == rp["avoided_cell"]
            for e in peer_events
        )
        if not was_there:
            unnecessary += 1
            rp["foundUnnecessary"] = True
        else:
            rp["foundUnnecessary"] = False

    yields_by_robot = collections.Counter(y["own_id"] for y in prof.yield_events)

    return {
        "scenarioId": scenario_id, "seed": seed, "completed": completed,
        "finalTick": final_tick,
        "perRobot": per_robot,
        "totalReplanTriggers": len(prof.replan_events),
        "unnecessaryReplanTriggers": unnecessary,
        "replanEvents": prof.replan_events,
        "totalYieldVerdicts": sum(yields_by_robot.values()),
        "yieldVerdictsByRobot": dict(yields_by_robot),
        "yieldEvents": prof.yield_events,
        "resetOnlyDeadlockEvents": prof.reset_only_deadlock_events,
        "plannerCallsDuringRun": prof.planner_calls_during_run,
        "collisionCount": metric.collisionCount,
        "deadlockCount": metric.deadlockCount,
    }


# ── Aggregation + reporting ──────────────────────────────────────────────────

def aggregate_scenario(runs: list[dict]) -> dict:
    n = len(runs)
    all_buckets = collections.Counter()
    total_moving = total_ideal = total_detour = total_deadlock_recovery = 0
    total_replans = total_unnecessary = 0
    total_yields = 0
    wrong_robot_yields = 0  # a yield where the yielding robot had LOWER remaining cost than the peer it yielded to
    yield_cost_pairs = 0
    for run in runs:
        for rid, rob in run["perRobot"].items():
            total_moving += rob["movingTicks"]
            total_ideal += rob["idealTicks"]
            total_detour += rob["detourExtraTicks"]
            total_deadlock_recovery += rob["deadlockRecoveryTicks"]
            for b, c in rob["waitBuckets"].items():
                all_buckets[b] += c
        total_replans += run["totalReplanTriggers"]
        total_unnecessary += run["unnecessaryReplanTriggers"]
        total_yields += run["totalYieldVerdicts"]
        for y in run["yieldEvents"]:
            if y["own_remaining"] is not None and y["peer_remaining"] is not None:
                yield_cost_pairs += 1
                if y["own_remaining"] < y["peer_remaining"]:
                    wrong_robot_yields += 1

    return {
        "runs": n,
        "meanMovingTicksPerRobotPerRun": total_moving / n if n else 0,
        "meanIdealTicksPerRobotPerRun": total_ideal / n if n else 0,
        "meanDetourExtraTicksPerRobotPerRun": total_detour / n if n else 0,
        "meanDeadlockRecoveryTicksPerRobotPerRun": total_deadlock_recovery / n if n else 0,
        "waitBucketTotals": dict(all_buckets),
        "meanWaitBucketsPerRun": {k: v / n for k, v in all_buckets.items()} if n else {},
        "totalReplanTriggers": total_replans,
        "unnecessaryReplanTriggers": total_unnecessary,
        "unnecessaryReplanRate": (total_unnecessary / total_replans) if total_replans else 0.0,
        "totalYieldVerdicts": total_yields,
        "yieldEventsWithBothCosts": yield_cost_pairs,
        "yieldsWhereYielderHadLowerRemainingCost": wrong_robot_yields,
        "wrongRobotYieldRate": (wrong_robot_yields / yield_cost_pairs) if yield_cost_pairs else 0.0,
    }


def main(argv=None) -> dict:
    parser = argparse.ArgumentParser(description="Phase 1 tick-loss profiler.")
    parser.add_argument("--scenarios", nargs="+", default=DEFAULT_SCENARIOS)
    parser.add_argument("--seeds", nargs="+", type=int, default=DEFAULT_SEEDS)
    parser.add_argument("--out", default=None, help="Optional path to write the full JSON result.")
    args = parser.parse_args(argv)

    wm = build_benchmark_warehouse_map()
    all_results: dict[str, list[dict]] = {}
    for sid in args.scenarios:
        runs = []
        for seed in args.seeds:
            r = profile_one(sid, seed, wm)
            runs.append(r)
            print(f"[{sid}] seed={seed} completed={r['completed']} "
                  f"replans={r['totalReplanTriggers']} (unnecessary={r['unnecessaryReplanTriggers']}) "
                  f"yields={r['totalYieldVerdicts']} collisions={r['collisionCount']} "
                  f"deadlocks={r['deadlockCount']}")
        all_results[sid] = runs

    print("\n" + "=" * 100)
    print("TICK-LOSS BREAKDOWN PER SCENARIO (mean per robot per run, DECENTRALIZED_PROPOSED)")
    print("=" * 100)
    aggs = {}
    for sid, runs in all_results.items():
        agg = aggregate_scenario(runs)
        aggs[sid] = agg
        print(f"\n--- {sid} ({agg['runs']} runs) ---")
        print(f"  mean moving ticks/robot:            {agg['meanMovingTicksPerRobotPerRun']:.2f}")
        print(f"  mean ideal (shortest-path) ticks:   {agg['meanIdealTicksPerRobotPerRun']:.2f}")
        print(f"  mean detour-extra ticks/robot:       {agg['meanDetourExtraTicksPerRobotPerRun']:.2f}")
        print(f"  mean deadlock-recovery ticks/robot:  {agg['meanDeadlockRecoveryTicksPerRobotPerRun']:.2f}")
        print(f"  wait buckets (total across all runs/robots): {agg['waitBucketTotals']}")
        print(f"  mean wait buckets/run: { {k: round(v,2) for k,v in agg['meanWaitBucketsPerRun'].items()} }")
        print(f"  replan triggers: {agg['totalReplanTriggers']} (unnecessary: {agg['unnecessaryReplanTriggers']}, "
              f"rate={agg['unnecessaryReplanRate']*100:.1f}%)")
        print(f"  yield verdicts: {agg['totalYieldVerdicts']} "
              f"(yielder had LOWER remaining cost than peer: {agg['yieldsWhereYielderHadLowerRemainingCost']}/"
              f"{agg['yieldEventsWithBothCosts']} = {agg['wrongRobotYieldRate']*100:.1f}%)")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({"perScenarioAggregate": aggs, "rawRuns": all_results}, indent=2, default=str), encoding="utf-8")
        print(f"\nFull detail written to {out_path}")

    return {"perScenarioAggregate": aggs, "rawRuns": all_results}


if __name__ == "__main__":
    main()
