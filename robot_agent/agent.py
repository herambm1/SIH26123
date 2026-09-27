"""
robot_agent/agent.py — RobotAgent orchestration loop.
Owner: Member 3

This is the Phase-0 skeleton written collaboratively by the whole team.
It defines the tick() shape that every other Python module plugs into.
Member 3 maintains and extends it in small, incremental PRs.

IMPORTANT: Keep changes to this file small and announce them to the team —
it is the most cross-cutting file in the repo and all other members' work
depends on the call signatures staying stable.

Import contracts from shared.python.models — do NOT redefine them here.
"""

from shared.python.models import Position, RobotState, RobotPath


class RobotAgent:
    """Orchestration shell for a single robot in the simulation.

    Composition (all injected via constructor, all mockable independently):
        planner    → Member 1 (Planner)
        transport  → Member 2 (Transport)
        sensor     → Member 5 (SensorSource)
        detector   → Member 3 (ConflictDetector)
        resolver   → Member 3 (ConflictResolver)
        deadlock   → Member 3 (DeadlockDetector)

    The actual implementations are stubs until each member delivers them.
    """

    def __init__(
        self,
        robot_id: str,
        planner,          # planner.astar.Planner
        transport,        # robot_agent.communication.transport.Transport
        sensor,           # edge.sensor_source.SensorSource
        detector,         # collision_engine.detection.ConflictDetector
        resolver,         # collision_engine.resolution.ConflictResolver
        deadlock,         # collision_engine.deadlock.DeadlockDetector
    ):
        self.robot_id = robot_id
        self.planner = planner
        self.transport = transport
        self.sensor = sensor
        self.detector = detector
        self.resolver = resolver
        self.deadlock = deadlock

        # Internal state — assembled/updated each tick
        self.state: RobotState | None = None    # initialised by simulation runner before tick 0
        self._stall_ticks: int = 0
        self._waiting_on: str | None = None     # robot_id of the peer we're waiting on
        self._blocked_cells: list[Position] = []
        self._temporary_avoid_cells: list[Position] = []
        self._version: int = 1
        self._replan_requested: bool = False
        self._action_this_tick: str | None = None
        # Cells physically occupied by peers that are not moving this tick,
        # rebuilt from peer intents every tick: {(x, y): peerRobotId}.
        # Transient by design — never folded into _blocked_cells, which is
        # for map obstacles and must not be poisoned by a peer that has
        # merely paused.
        self._peer_held_cells: dict = {}
        # Peer physically blocking our next cell, if any. Distinct from
        # _waiting_on, which the resolver clears on a CONTINUE verdict: a
        # robot that keeps winning the priority argument but still cannot
        # move is stalled just the same, and must still be able to trip the
        # deadlock escape.
        self._blocked_by_peer: str | None = None
        # Last known task priority per peer, from their broadcast intents.
        self._peer_priorities: dict = {}
        # Last known RAW (x, y) per peer, rebuilt fresh every tick from this
        # tick's received intents, unfiltered by the peer's self-reported
        # status/plannedPath (unlike _peer_held_cells, which deliberately
        # trusts a "MOVING with somewhere to go" peer to vacate). Needed so
        # a resume decision can catch a peer whose status label says MOVING
        # but whose actual position still coincides with our next cell —
        # see _waiting_condition_cleared().
        self._peer_raw_positions: dict = {}
        # First planned waypoint (x, y) per peer, rebuilt fresh every tick from
        # this tick's received intents: {peerRobotId: (x, y)}. Used only by
        # _peer_to_hold_for().
        self._peer_next_cells: dict = {}

    def tick(self, current_tick: int) -> RobotState:
        """Execute one simulation tick for this robot.

        Tick sequence (Phase-0 skeleton — Member 3 fills in):
          1. Read sensor telemetry (Member 5)
          2. Apply telemetry to state
          3. Replan if needed (Member 1)
          4. Receive peer intents from bus (Member 2)
          5. Detect conflicts (Member 3)
          6. Resolve conflicts if any (Member 3)
          7. Check for deadlock (Member 3)
          8. Advance one cell if clear
          9. Broadcast own intent (Member 2)
          10. Stamp timestamp and return state

        Implementation: Member 3's responsibility.
        Returns a fully populated RobotState for this tick.
        """
        try:
            from robot_agent.communication.messages import build_intent_message  # noqa: import here to avoid circular at module load
        except ImportError:
            build_intent_message = None

        telemetry = None
        if self.sensor:
            try:
                telemetry = self.sensor.read(self.robot_id, current_tick)          # Member 5
            except Exception:
                telemetry = None

        self.state = self._apply_telemetry(self.state, telemetry, current_tick)

        # FIXED (was a documented, deliberately-deferred defect — see
        # CLAUDE.md Known Bugs #4 and the Product-mode Phase 3 soak-test
        # root-cause finding): this replan previously did not pass
        # start_tick, so the planner defaulted to 0 and every replanned path
        # was stamped with ticks 1,2,3... bearing no relation to the real
        # simulation clock. That made ConflictDetector's space-time checks
        # compare incomparable tick values for any robot that had replanned
        # — invisible in every one of the 9 benchmarked scenarios (which
        # replan rarely) but empirically produced real, referee-verified
        # collisions under Product mode's continuous task-reassignment
        # pattern (a robot gets a brand-new destination the instant it goes
        # idle, replanning far more often than any scenario). Passing
        # start_tick=current_tick - 1, exactly as previously documented
        # here, aligns replanned waypoint ticks with the real clock. See
        # CLAUDE.md for the full before/after benchmark and soak-test
        # verification this fix required before being trusted.
        if self._needs_replan() and self.planner and self.state.destination:
            try:
                plan_result = self.planner.plan(                    # Member 1
                    self.state.position,
                    self.state.destination,
                    self._known_blocked_cells(),
                    start_tick=current_tick - 1,
                )
                if hasattr(plan_result, "waypoints"):
                    self.state.currentPath = list(plan_result.waypoints)
                elif isinstance(plan_result, list):
                    self.state.currentPath = list(plan_result)
                self.state.status = "MOVING"
                self._version += 1
            except Exception:
                # Planner unavailable / raises PlanningFailedError: robot enters status=BLOCKED, retries next tick
                self.state.status = "BLOCKED"
                self.state.velocity = 0.0

        incoming = []
        if self.transport:
            try:
                incoming = self.transport.receive(self.robot_id) or []              # Member 2
            except Exception:
                incoming = []

        self._peer_held_cells = self._collect_peer_held_cells(incoming)

        conflict = None
        if self.detector:
            conflict = self.detector.detect(self.state, self._current_path_obj(), incoming)  # Member 3

        if conflict and self.resolver:
            action = self.resolver.resolve(conflict, self.state, incoming)
            self._apply_action(action, conflict)

        # A robot blocked by a peer's body is waiting on that peer even when
        # the resolver just told it to CONTINUE — otherwise the winner of a
        # head-on priority argument stalls forever without ever tripping the
        # deadlock escape (observed livelock in scenario d_deadlock).
        waiting_on = self._waiting_on or self._blocked_by_peer
        if self.deadlock and self.deadlock.check(self.robot_id, self._stall_ticks, waiting_on):
            self._force_yield()

        self._advance_one_cell_if_clear(conflict)

        # Broadcast intent
        if self.transport:
            intent_msg = None
            if build_intent_message:
                try:
                    intent_msg = build_intent_message(self.state)
                except Exception:
                    intent_msg = None
            if intent_msg is None:
                intent_msg = {
                    "robotId": self.state.robotId,
                    "position": self.state.position,
                    "destination": self.state.destination,
                    "plannedPath": list(self.state.currentPath or []),
                    "currentTask": self.state.currentTaskId,
                    "priority": getattr(self.state, "task_priority", 1),
                    "battery": self.state.battery,
                    "status": self.state.status,
                    "timestamp": current_tick,
                }
            try:
                self.transport.broadcast(intent_msg)                                # Member 2
            except Exception:
                pass

        self.state.timestamp = current_tick
        return self.state

    # ── Private helpers — implementations for Member 3 ─────────────────────

    def _apply_telemetry(self, state, telemetry, current_tick: int) -> RobotState:
        """Fold sensor telemetry into the current robot state."""
        if state is None:
            state = RobotState(
                robotId=self.robot_id,
                position=Position(x=0, y=0),
                velocity=0.0,
                battery=100.0,
                currentTaskId=None,
                destination=None,
                currentPath=[],
                status="IDLE",
                timestamp=current_tick,
            )

        if telemetry is not None:
            if hasattr(telemetry, "battery") and telemetry.battery is not None:
                state.battery = float(telemetry.battery)
            if hasattr(telemetry, "sensorHealth") and telemetry.sensorHealth == "OFFLINE":
                state.status = "OFFLINE"
                state.velocity = 0.0
            if hasattr(telemetry, "position") and telemetry.position is not None:
                if state.status != "OFFLINE":
                    state.position = Position(x=telemetry.position.x, y=telemetry.position.y)
        return state

    def _needs_replan(self) -> bool:
        """Return True if the robot needs a new path this tick."""
        if not self.state or self.state.status == "OFFLINE":
            return False
        if self._replan_requested:
            self._replan_requested = False
            return True
        if self.state.destination is not None:
            # Need replan if no path exists and we haven't reached destination
            has_no_path = not self.state.currentPath or len(self.state.currentPath) == 0
            not_at_goal = (
                self.state.position.x != self.state.destination.x
                or self.state.position.y != self.state.destination.y
            )
            return has_no_path and not_at_goal
        return False

    # Statuses meaning a peer will not vacate its cell this tick. OFFLINE is
    # included here (unlike in ConflictDetector, which negotiates and so
    # ignores OFFLINE peers): a dead robot is the most immovable obstacle on
    # the floor, and driving into it is still a collision.
    _PEER_STATIONARY_STATUSES = frozenset({"WAITING", "BLOCKED", "IDLE", "CHARGING", "OFFLINE"})

    def _collect_peer_held_cells(self, peer_intents: list) -> dict:
        """Map {(x, y): peerRobotId} for peers that are standing still.

        Uses only the peers' own broadcast intents (position + status +
        plannedPath) — no global robot registry, so this stays decentralized.

        Also refreshes self._peer_raw_positions — every reporting peer's raw
        current position, UNFILTERED by status/plannedPath (unlike `held`
        below, which deliberately trusts a "MOVING + has somewhere to go"
        peer to vacate soon). _waiting_condition_cleared() needs the
        unfiltered version: a peer's status label can lag reality — it only
        reflects what that peer believed when it composed its intent, which
        can itself be stuck (blocked by a third robot, or by us) while still
        broadcasting "MOVING". Trusting the label alone for a resume
        decision caused a referee-verified collision in `d_deadlock` during
        this fix's own validation (R1 self-reported MOVING while physically
        still occupying the cell R2 was about to resume into, delayed one
        tick by MessageFaultConfig) — see _waiting_condition_cleared().
        """
        held: dict = {}
        self._peer_priorities = {}
        self._peer_raw_positions = {}
        self._peer_next_cells = {}
        for peer in peer_intents or []:
            peer_id = peer.get("robotId") if isinstance(peer, dict) else None
            if not peer_id or peer_id == self.robot_id:
                continue
            try:
                self._peer_priorities[peer_id] = int(peer.get("priority", 1))
            except (TypeError, ValueError):
                self._peer_priorities[peer_id] = 1
            cell = self._peer_cell(peer.get("position"))
            if cell is not None:
                self._peer_raw_positions[peer_id] = cell
            status = peer.get("status")
            planned = peer.get("plannedPath") or []
            if planned:
                next_cell = self._peer_cell(planned[0])
                if next_cell is not None:
                    self._peer_next_cells[peer_id] = next_cell
            if status not in self._PEER_STATIONARY_STATUSES and planned:
                continue  # peer is moving and has somewhere to go — it will vacate
            if cell is not None:
                held[cell] = peer_id
        return held

    @staticmethod
    def _peer_cell(pos_raw):
        """Normalize a Position / dict / (x, y) tuple into (x, y), or None."""
        if pos_raw is None:
            return None
        if isinstance(pos_raw, Position):
            return (pos_raw.x, pos_raw.y)
        if isinstance(pos_raw, dict):
            x, y = pos_raw.get("x"), pos_raw.get("y")
            return (x, y) if x is not None and y is not None else None
        if isinstance(pos_raw, (tuple, list)) and len(pos_raw) >= 2:
            return (pos_raw[0], pos_raw[1])
        return None

    def _known_blocked_cells(self) -> list:    # list[Position]
        """Return the set of currently known blocked cells."""
        combined = list(self._blocked_cells)
        for p in self._temporary_avoid_cells:
            if not any(b.x == p.x and b.y == p.y for b in combined):
                combined.append(p)
        return combined

    def _current_path_obj(self) -> RobotPath:
        """Reconstruct a RobotPath object from the current state."""
        waypoints = list(self.state.currentPath) if self.state and self.state.currentPath else []
        ts = self.state.timestamp if self.state else 0
        return RobotPath(
            robotId=self.robot_id,
            waypoints=waypoints,
            generatedAtTick=ts,
            version=self._version,
        )

    def _apply_action(self, action: str, conflict) -> None:
        """Apply a conflict resolution action to this robot's state."""
        self._action_this_tick = action
        peer_id = None
        if conflict and hasattr(conflict, "robotIds"):
            peer_id = next((rid for rid in conflict.robotIds if rid != self.robot_id), None)

        if action == "CONTINUE":
            self._waiting_on = None
            if self.state.status == "WAITING":
                self.state.status = "MOVING"
            self.state.velocity = 1.0
        elif action == "WAIT":
            self.state.status = "WAITING"
            self.state.velocity = 0.0
            self._waiting_on = peer_id
        elif action == "YIELD":
            self.state.status = "WAITING"
            self.state.velocity = 0.0
            self._waiting_on = peer_id
            if conflict and hasattr(conflict, "predictedCell") and conflict.predictedCell:
                self._temporary_avoid_cells.append(conflict.predictedCell)
                self._replan_requested = True
        elif action == "REROUTE":
            self._waiting_on = None
            if conflict and hasattr(conflict, "predictedCell") and conflict.predictedCell:
                self._temporary_avoid_cells.append(conflict.predictedCell)
            self._replan_requested = True
        elif action == "REASSIGN_TASK":
            self.state.status = "BLOCKED"
            self.state.velocity = 0.0
            self._waiting_on = None

    def _force_yield(self) -> None:
        """Force the robot to yield and replan (deadlock recovery)."""
        # Route around whatever we have been stuck behind. Without this the
        # replan regenerates the identical path straight back into the same
        # contested cell, and the "recovery" recovers nothing — two robots
        # nose to nose in a corridor just stall until the run times out.
        #
        # Only the LOWER-priority robot steps aside, per the documented rule
        # in role/03_COORDINATION.md. If both sides of a standoff reroute at
        # once they simply collide somewhere else — which is exactly what
        # happened when this recovery was first added and both robots dodged
        # into the same neighbouring cell on the same tick.
        if self._should_step_aside() and self.state and self.state.currentPath:
            self._avoid_cell(self.state.currentPath[0])

        self.state.status = "WAITING"
        self.state.velocity = 0.0
        self._stall_ticks = 0
        self._waiting_on = None
        self._blocked_by_peer = None
        self._replan_requested = True

    def _should_step_aside(self) -> bool:
        """True if THIS robot is the one that should reroute out of a standoff.

        Mirrors ConflictResolver's priority order: higher task priority wins
        and holds its ground; ties break on robotId (lexicographically lower
        wins). With no known peer, stepping aside is the safe default.
        """
        peer_id = self._blocked_by_peer or self._waiting_on
        if not peer_id:
            return True
        own_priority = int(getattr(self.state, "task_priority", 1) or 1)
        peer_priority = int(self._peer_priorities.get(peer_id, 1))
        if own_priority != peer_priority:
            return own_priority < peer_priority
        return self.robot_id > peer_id

    def _avoid_cell(self, cell: Position) -> None:
        """Add a cell to the temporary avoid set (deduplicated)."""
        if not any(c.x == cell.x and c.y == cell.y for c in self._temporary_avoid_cells):
            self._temporary_avoid_cells.append(Position(x=cell.x, y=cell.y))

    def _peer_outranks(self, peer_id: str) -> bool:
        """True if `peer_id` wins a priority argument against THIS robot.

        Same order as ConflictResolver and _should_step_aside(): higher task
        priority wins; ties go to the lexicographically lower robotId.
        """
        own_priority = int(getattr(self.state, "task_priority", 1) or 1)
        peer_priority = int(self._peer_priorities.get(peer_id, 1))
        if own_priority != peer_priority:
            return peer_priority > own_priority
        return peer_id < self.robot_id

    def _peer_to_hold_for(self) -> str | None:
        """Peer this robot must NOT step in front of this tick, or None.

        Two situations, both decided from this tick's received intents only:

          1. Exact face-to-face: a peer's reported position is our next cell
             AND that peer's own next waypoint is the cell we are standing on.
             We would swap, or one of us would step into the other. The
             detector cannot see this pair (a robot's plannedPath never holds
             the cell it stands on), and _peer_held_cells deliberately trusts
             a MOVING peer to vacate.
          2. Shared next cell: a HIGHER-priority peer's reported next waypoint
             is our next cell. Only the loser holds, exactly as the resolver
             would have told it to; the winner is never held by this check.
             This uses the peer's next waypoint, not its reported position:
             under a 1-tick message delay a peer's reported position is a
             cell behind reality (the earlier-ticking peer has already moved
             this tick), while its reported next waypoint is where it
             actually is now.

        Everything else (a peer merely on our next cell but leaving, a peer
        behind us, a lower-priority peer sharing our next cell) returns None
        and follows the existing code path unchanged.
        """
        if not self.state or not self.state.currentPath:
            return None
        next_wp = self.state.currentPath[0]
        next_cell = (next_wp.x, next_wp.y)
        here = (self.state.position.x, self.state.position.y)
        for peer_id, peer_cell in self._peer_raw_positions.items():
            if peer_cell == next_cell and self._peer_next_cells.get(peer_id) == here:
                return peer_id
        for peer_id, peer_next in self._peer_next_cells.items():
            if peer_next == next_cell and self._peer_outranks(peer_id):
                return peer_id
        return None

    def _waiting_condition_cleared(self, conflict_this_tick) -> bool:
        """True if the specific reason THIS robot is WAITING has genuinely
        gone away, per this tick's own fresh information — never a bare
        timeout and never a blind "if WAITING: resume".

        Root cause this closes (see CLAUDE.md / role/03_COORDINATION.md):
        a robot that enters WAITING via a resolved WAIT/YIELD verdict, or via
        the physical peer-occupancy guard below, previously had no way to
        notice its blocker had moved on — `_apply_action()` (the only code
        that could flip status away from WAITING) only ever runs when
        `detector.detect()` finds a conflict THIS tick, so once the peer's
        broadcast path no longer contained the contested cell, nothing ever
        looked again. The robot then sat idle until DeadlockDetector's
        stall_threshold fired `_force_yield()`, which forces a full replan/
        detour — often unnecessary, since the original path was already
        fine the moment the peer cleared. Measured effect: `b_intersection`
        (a single, cleanly-prioritized two-robot crossing) took ~16 ticks
        instead of the ~9 a naive STOP_AND_WAIT baseline needs for the same
        conflict, almost entirely idle-stall + an unneeded detour.

        Deliberately conservative — BOTH signals below must agree, using
        only information this robot already has this tick (no new data
        source, no bypass of ConflictDetector, no change to priority rules):

          1. `detector.detect()` found NO conflict at all against this
             tick's actual received peer intents — the exact same detector
             every other decision in tick() already trusts.
          2. No peer is currently reported as physically holding the cell
             this robot would move into next (`_peer_held_cells`, rebuilt
             fresh every tick from this tick's `incoming` — the identical
             source `_advance_one_cell_if_clear`'s own physical guard below
             already relies on for every robot, waiting or not).
          3. The SPECIFIC peer we were waiting on has not itself reported
             its raw current position as our next cell — checked
             independently of its self-labeled status, because that label
             can lag reality (a peer stuck behind a third robot, or behind
             us, still broadcasts whatever status it believed when it
             composed its intent). Relying on the status label alone here
             produced a referee-verified collision in `d_deadlock` during
             this fix's own validation: R1 self-reported MOVING (with a
             non-empty planned path, the same shape a genuinely-departing
             peer uses) while, in ground truth, still occupying the exact
             cell R2 was about to resume into — one tick of message delay
             (MessageFaultConfig.delay_ticks) was enough to hide that R1
             was itself blocked. This check does not trust the label; it
             compares the peer's raw reported (x, y) directly.

        If ANY of the three still shows a block, this returns False and the
        robot stays exactly as WAITING as before:
          - a peer still genuinely there (still reported stationary in our
            path, or still physically holding our next cell) keeps failing
            check 1 and/or check 2 — this includes a genuine mutual deadlock,
            where nothing about the peer ever looks clear;
          - a peer whose departure hasn't been heard about yet because its
            message was delayed (MessageFaultConfig.delay_ticks) still shows
            its last-heard, still-blocking position in this tick's intents;
          - a different peer now occupying the same path is caught the same
            way a fresh conflict against it would be.

        A True result only ever lets the robot ATTEMPT to resume — it does
        not move anything itself. `_advance_one_cell_if_clear` re-runs its
        own unconditional physical-occupancy/blocked-cell checks immediately
        afterward, in the same call, before any position is actually
        mutated — the exact same checks a normally-MOVING robot already
        passes through every tick. This fix does not weaken that guard; it
        only lets a WAITING robot reach it again.
        """
        if not self.state or not self._waiting_on:
            # No specific peer on record (e.g. mid-way through a
            # _force_yield()-triggered replan, which already clears
            # _waiting_on to None) — nothing for this check to clear.
            # Leave that recovery path entirely alone.
            return False
        if conflict_this_tick is not None:
            return False
        if not self.state.currentPath:
            return True  # nothing left to be blocked on — harmless no-op resume
        next_wp = self.state.currentPath[0]
        next_cell = (next_wp.x, next_wp.y)
        if self._peer_held_cells.get(next_cell) is not None:
            return False
        if self._peer_raw_positions.get(self._waiting_on) == next_cell:
            return False
        return True

    def _advance_one_cell_if_clear(self, conflict_this_tick=None) -> None:
        """Move the robot one cell along its current path if the next cell is clear.

        conflict_this_tick: the Conflict object (or None) tick() just got
        back from detector.detect() this same tick — passed through only so
        a WAITING robot can re-check _waiting_condition_cleared() using the
        SAME already-computed detection result, never a second/bypassing
        call into the detector.
        """
        if self.state and self.state.status not in ("OFFLINE", "BLOCKED"):
            holder = self._peer_to_hold_for()
            if holder is not None:
                self.state.status = "WAITING"
                self.state.velocity = 0.0
                self._waiting_on = holder
                self._blocked_by_peer = holder
                self._stall_ticks += 1
                return

        if self.state and self.state.status == "WAITING" and self._waiting_condition_cleared(conflict_this_tick):
            # Resume-on-clear: fall through to the normal movement checks
            # below instead of returning early — they independently verify
            # physical occupancy/blocked cells before any position changes.
            self.state.status = "MOVING"
            self._waiting_on = None
            self._blocked_by_peer = None
            self.state.velocity = 1.0

        if not self.state or self.state.status in ("OFFLINE", "WAITING", "BLOCKED"):
            self.state.velocity = 0.0
            if self.state and self.state.status in ("WAITING", "BLOCKED"):
                self._stall_ticks += 1
            return

        if self.state.currentPath and len(self.state.currentPath) > 0:
            next_wp = self.state.currentPath[0]

            # A cell a stationary peer is standing in is not clear, whatever
            # the conflict resolver decided. Winning a priority argument does
            # not move the other robot out of the way: without this guard a
            # CONTINUE verdict drives straight into a peer that is parked or
            # waiting (referee-verified collisions in d_deadlock/g_high_load).
            holder = self._peer_held_cells.get((next_wp.x, next_wp.y))
            if holder is not None:
                self.state.status = "WAITING"
                self.state.velocity = 0.0
                self._waiting_on = holder
                self._blocked_by_peer = holder
                self._stall_ticks += 1
                return

            blocked = any(b.x == next_wp.x and b.y == next_wp.y for b in self._known_blocked_cells())
            if blocked:
                self.state.status = "BLOCKED"
                self.state.velocity = 0.0
                self._stall_ticks += 1
                self._replan_requested = True
                return

            # Advance
            self.state.currentPath.pop(0)
            old_pos = (self.state.position.x, self.state.position.y)
            self.state.position = Position(x=next_wp.x, y=next_wp.y, tick=None)
            new_pos = (self.state.position.x, self.state.position.y)

            if old_pos != new_pos:
                self._stall_ticks = 0
                self._waiting_on = None
                self._blocked_by_peer = None
                self.state.velocity = 1.0
            else:
                self._stall_ticks += 1

            # Check if destination reached
            if (
                self.state.destination
                and self.state.position.x == self.state.destination.x
                and self.state.position.y == self.state.destination.y
            ):
                self.state.status = "IDLE"
                self.state.velocity = 0.0
                self.state.currentTaskId = None
                self.state.currentPath = []
        else:
            self.state.velocity = 0.0
            if (
                self.state.destination
                and self.state.position.x == self.state.destination.x
                and self.state.position.y == self.state.destination.y
            ):
                self.state.status = "IDLE"
