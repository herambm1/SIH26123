"""simulation/product/world_faults.py — seeded, state-reactive world-fault
generator + guarded application, for Product-mode sessions only.

Exactly 3 world faults, per the Product-mode design brief:
  AISLE_BLOCK  — reuses the existing agent._blocked_cells + _replan_requested
                 mechanism every scenario's scripted AISLE_BLOCKED event
                 already uses (simulation/runner.py's per-tick event loop);
                 adds a timed clear (removal + a fresh replan request) that
                 no scripted scenario event currently has.
  ROBOT_OFFLINE — sets SimulationSensorSource.fault_config.offline_after_tick
                 at runtime on the target's real sensor instance, the exact
                 same field simulation/runner.py already sets at
                 construction time for scenario f_task_reassignment, just
                 mutated after the fact instead of pre-configured.
  COMM_DELAY   — sets InProcessBus's own MessageFaultConfig.delay_ticks to 1
                 for a bounded number of ticks, the same field/mechanism
                 scenario d_deadlock already exercises (bus-wide, read fresh
                 every _enqueue() call — nothing new added to the bus).

No decision logic in collision_engine/, robot_agent/agent.py, or the
detector/resolver/deadlock classes is touched or reimplemented anywhere in
this file — every fault is applied through a mutation point the existing
runner already uses for scripted scenario events, just triggered live
instead of pre-scripted.

KNOWN, DISCLOSED LIMITATION (see docs/PRODUCT_MODE.md): a Phase 0 read of
robot_agent/agent.py confirmed OFFLINE is one-way there — _apply_telemetry()
only ever SETS status="OFFLINE", nothing in agent.py ever clears it. So
ROBOT_OFFLINE has no live "recovery" in this codebase; the offline robot's
task must instead be reassigned to a different robot via a fresh
POST /control/task (Java-authoritative, per the Product-mode plan — this
module does not itself reassign anything).
"""

from __future__ import annotations

import random

from shared.python.models import Position


class FaultGuardRejected(Exception):
    """Raised internally when a candidate/manual fault fails a guard check.
    Always caught by the caller and turned into a SYSTEM "fault skipped"
    event with the message as the reason — never allowed to propagate and
    crash the tick loop."""


class WorldFaultGenerator:
    """Seeded generator + shared guard logic for both auto-generated and
    manually (judge-)injected faults.

    Uses its OWN random.Random(seed) — never the InProcessBus RNG or the
    per-robot SimulationSensorSource RNGs, which stay exactly as
    simulation.runner already seeds them. This is a fully separate stream,
    so toggling auto-generation on/off never perturbs anything else's
    reproducibility.
    """

    def __init__(
        self,
        seed: int,
        *,
        cooldown_ticks: int = 15,
        max_concurrent: int = 2,
        max_concurrent_offline: int = 1,
        aisle_block_clear_after: int = 10,
        comm_delay_episode_ticks: int = 5,
        generation_probability: float = 0.25,
    ) -> None:
        self._rng = random.Random(f"world_faults:{seed}")
        self.cooldown_ticks = cooldown_ticks
        self.max_concurrent = max_concurrent
        # At most this many robots may be broken down (ROBOT_OFFLINE) at once, on top of the combined max_concurrent limit. 1 keeps a
        # Product session readable: one robot needs attention at a time, and "Mark as fixed" frees the slot for the next breakdown.
        self.max_concurrent_offline = max_concurrent_offline
        self.aisle_block_clear_after = aisle_block_clear_after
        self.comm_delay_episode_ticks = comm_delay_episode_ticks
        self.generation_probability = generation_probability

        self._last_fault_tick: int = -cooldown_ticks
        # (x, y) -> tick at which to clear
        self.active_aisle_blocks: dict[tuple[int, int], int] = {}
        self.active_offline_robots: set[str] = set()
        self._comm_delay_clear_tick: int | None = None

    # ── Candidate selection (from LIVE state, never fabricated) ────────────

    def _candidate_aisle_cells(self, agents: dict, gt_positions: dict) -> list[tuple[int, int]]:
        """Cells a couple of steps ahead of some currently-moving robot's own
        real planned path — never the cell it's about to step into next
        (that would be indistinguishable from just blocking the robot), and
        never a cell any robot currently occupies."""
        occupied = {(p.x, p.y) for p in gt_positions.values()}
        candidates: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        for agent in agents.values():
            state = agent.state
            if not state or not state.currentPath or state.status == "OFFLINE":
                continue
            # skip the immediate next cell (index 0); look 1-3 cells further out
            for wp in state.currentPath[1:4]:
                cell = (wp.x, wp.y)
                if cell in occupied or cell in seen:
                    continue
                seen.add(cell)
                candidates.append(cell)
        return candidates

    def _candidate_offline_targets(self, agents: dict) -> list[str]:
        """Robots currently carrying a task and not already offline — taking
        an idle/parked robot offline would be an inert, meaningless fault.

        "Carrying a task" requires BOTH a real destination AND a live
        (non-IDLE) status — destination alone is not enough: robot_agent.
        agent.py's own arrival logic (_advance_one_cell_if_clear) clears
        status/currentPath/currentTaskId on arrival but deliberately never
        clears `destination` itself, so a just-completed, IDLE robot would
        otherwise still look "en route" to this check."""
        out = []
        for rid, agent in agents.items():
            state = agent.state
            if not state or state.status in ("OFFLINE", "IDLE") or rid in self.active_offline_robots:
                continue
            if state.destination is not None:
                out.append(rid)
        return out

    # ── Feasibility guard (real planner, never a heuristic guess) ──────────

    @staticmethod
    def _feasible_after_block(planner, agents: dict, candidate_cell: tuple[int, int]) -> bool:
        """True only if EVERY agent with a live destination still has a real
        path (via the same GridAStarPlanner every agent's own replan already
        uses) once candidate_cell is added to its blocked-cell set, in
        addition to whatever it already has blocked. Reuses the planner
        exactly as robot_agent/agent.py's own _needs_replan()/plan() call
        does — no reimplementation of pathfinding."""
        extra_blocked = Position(x=candidate_cell[0], y=candidate_cell[1])
        for agent in agents.values():
            state = agent.state
            if not state or not state.destination or state.status == "OFFLINE":
                continue
            if state.position.x == state.destination.x and state.position.y == state.destination.y:
                continue
            blocked = list(agent._blocked_cells) + [extra_blocked]
            result = planner.plan(state.position, state.destination, blocked_cells=blocked, start_tick=0)
            if not result.waypoints:
                return False
        return True

    # ── Guarded apply (shared by auto-generation AND manual injection) ─────

    def try_apply_aisle_block(self, tick: int, cell: tuple[int, int], agents: dict, gt_positions: dict, planner) -> None:
        """Raises FaultGuardRejected with a human-readable reason on failure.
        On success, mutates every agent's _blocked_cells + _replan_requested
        (the exact mechanism scripted AISLE_BLOCKED events already use) and
        records the clear tick. Caller is responsible for emitting the
        resulting event(s)."""
        if tick - self._last_fault_tick < self.cooldown_ticks:
            raise FaultGuardRejected(f"cooldown active ({tick - self._last_fault_tick}/{self.cooldown_ticks} ticks since last fault)")
        if len(self.active_aisle_blocks) + len(self.active_offline_robots) >= self.max_concurrent:
            raise FaultGuardRejected(f"max concurrent faults reached ({self.max_concurrent})")
        occupied = {(p.x, p.y) for p in gt_positions.values()}
        if cell in occupied:
            raise FaultGuardRejected(f"cell {cell} is currently occupied by a robot")
        if cell in self.active_aisle_blocks:
            raise FaultGuardRejected(f"cell {cell} is already blocked")
        if not self._feasible_after_block(planner, agents, cell):
            raise FaultGuardRejected(f"blocking {cell} would strand at least one active/pending task (no path found)")

        blocked_pos = Position(x=cell[0], y=cell[1])
        for agent in agents.values():
            agent._blocked_cells.append(blocked_pos)
            agent._replan_requested = True
        self.active_aisle_blocks[cell] = tick + self.aisle_block_clear_after
        self._last_fault_tick = tick

    def clear_expired_aisle_blocks(self, tick: int, agents: dict) -> list[tuple[int, int]]:
        """Remove any aisle block whose clear tick has arrived. Returns the
        list of cells cleared this tick (empty if none), for event emission."""
        cleared = []
        for cell, clear_tick in list(self.active_aisle_blocks.items()):
            if tick >= clear_tick:
                for agent in agents.values():
                    agent._blocked_cells = [b for b in agent._blocked_cells if (b.x, b.y) != cell]
                    agent._replan_requested = True
                del self.active_aisle_blocks[cell]
                cleared.append(cell)
        return cleared

    def try_apply_robot_offline(self, tick: int, robot_id: str, agents: dict) -> None:
        if tick - self._last_fault_tick < self.cooldown_ticks:
            raise FaultGuardRejected(f"cooldown active ({tick - self._last_fault_tick}/{self.cooldown_ticks} ticks since last fault)")
        if len(self.active_aisle_blocks) + len(self.active_offline_robots) >= self.max_concurrent:
            raise FaultGuardRejected(f"max concurrent faults reached ({self.max_concurrent})")
        agent = agents.get(robot_id)
        if agent is None:
            raise FaultGuardRejected(f"unknown robotId {robot_id!r}")
        if len(self.active_offline_robots) >= self.max_concurrent_offline:
            raise FaultGuardRejected(
                f"max concurrent broken-down robots reached ({self.max_concurrent_offline}) - fix the broken robot first"
            )
        if not agent.state or agent.state.status == "OFFLINE":
            raise FaultGuardRejected(f"{robot_id} is already offline or has no state")
        if robot_id in self.active_offline_robots:
            raise FaultGuardRejected(f"{robot_id} is already offline")

        # Same field simulation/runner.py already sets at construction time
        # (offline_after_tick=offline_schedule.get(rid)) — mutated here
        # instead of pre-configured. The next sensor.read() call (this
        # robot's own next tick()) will see current_tick >= this value and
        # return OFFLINE telemetry, exactly like a scripted scenario fault.
        agent.sensor.fault_config.offline_after_tick = tick
        self.active_offline_robots.add(robot_id)
        self._last_fault_tick = tick

    @staticmethod
    def _adjacent_pair_exists(gt_positions: dict, threshold: int = 2) -> bool:
        """True if any two robots' ground-truth positions are within
        `threshold` Manhattan cells of each other. Ground-truth only — the
        same gt_positions dict try_apply_aisle_block's own occupied-cell
        check already uses — no path/tick/priority reasoning, so this is
        not a reimplementation of collision_engine's detection logic."""
        positions = list(gt_positions.values())
        for i, p1 in enumerate(positions):
            for p2 in positions[i + 1:]:
                if abs(p1.x - p2.x) + abs(p1.y - p2.y) <= threshold:
                    return True
        return False

    def try_apply_comm_delay(self, tick: int, transport_bus, gt_positions: dict) -> None:
        if tick - self._last_fault_tick < self.cooldown_ticks:
            raise FaultGuardRejected(f"cooldown active ({tick - self._last_fault_tick}/{self.cooldown_ticks} ticks since last fault)")
        if self._comm_delay_clear_tick is not None:
            raise FaultGuardRejected("a COMM_DELAY episode is already active")
        if self._adjacent_pair_exists(gt_positions):
            raise FaultGuardRejected(
                "two robots are currently within 2 cells of each other — activating "
                "COMM_DELAY now could blind a robot to a nearby peer for one tick"
            )
        transport_bus._fault.delay_ticks = 1
        self._comm_delay_clear_tick = tick + self.comm_delay_episode_ticks
        self._last_fault_tick = tick

    def clear_expired_comm_delay(self, tick: int, transport_bus) -> bool:
        if self._comm_delay_clear_tick is not None and tick >= self._comm_delay_clear_tick:
            transport_bus._fault.delay_ticks = 0
            self._comm_delay_clear_tick = None
            return True
        return False

    # ── Auto-generation (calls the same guarded apply methods above) ───────

    def maybe_generate(self, tick: int, agents: dict, gt_positions: dict, planner, transport_bus):
        """Returns (kind, detail, error) for a SYSTEM event, or None if
        nothing was attempted this tick (the common case — generation is
        probabilistic and cooldown-gated, not every eligible tick fires)."""
        if tick - self._last_fault_tick < self.cooldown_ticks:
            return None
        if len(self.active_aisle_blocks) + len(self.active_offline_robots) >= self.max_concurrent:
            return None
        if self._rng.random() > self.generation_probability:
            return None

        kind = self._rng.choice(["AISLE_BLOCK", "ROBOT_OFFLINE", "COMM_DELAY"])
        try:
            if kind == "AISLE_BLOCK":
                candidates = self._candidate_aisle_cells(agents, gt_positions)
                if not candidates:
                    return ("AISLE_BLOCK", None, "no eligible cell (no robot currently has a planned path 1-3 cells ahead)")
                cell = self._rng.choice(candidates)
                self.try_apply_aisle_block(tick, cell, agents, gt_positions, planner)
                return ("AISLE_BLOCK", {"cell": cell}, None)
            elif kind == "ROBOT_OFFLINE":
                if len(self.active_offline_robots) >= self.max_concurrent_offline:
                    return None  # breakdown cap reached: nothing to attempt, and no "fault skipped" noise in the feed
                candidates = self._candidate_offline_targets(agents)
                if not candidates:
                    return ("ROBOT_OFFLINE", None, "no eligible robot (none currently carrying a task)")
                robot_id = self._rng.choice(candidates)
                self.try_apply_robot_offline(tick, robot_id, agents)
                return ("ROBOT_OFFLINE", {"robotId": robot_id}, None)
            else:
                self.try_apply_comm_delay(tick, transport_bus, gt_positions)
                return ("COMM_DELAY", {"delayTicks": 1, "episodeTicks": self.comm_delay_episode_ticks}, None)
        except FaultGuardRejected as e:
            return (kind, None, str(e))
