"""
collision_engine/detection.py — ConflictDetector.
Owner: Member 3

Detects same-cell, crossing, and narrow-aisle head-on conflicts from broadcast
peer intents. Works from what robots tell each other (not ground truth).

Import contracts from shared.python.models — do NOT redefine them here.
"""

from shared.python.models import Conflict, Position, RobotPath, RobotState


class ConflictDetector:
    """Detects conflicts between a robot's planned path and peers' broadcast intents.

    Conflict types detected (per docs/00_SHARED_CONTRACTS.md):
        SAME_CELL         — two robots planning to occupy the same cell at the same tick
        CROSSING          — two robots' paths cross each other within the window
        NARROW_AISLE_HEADON — two robots approaching each other in a single-file aisle

    Implementation: Member 3's responsibility.
    """

    def detect(
        self,
        own_state: RobotState,
        own_path: RobotPath,
        peer_intents: list,    # list[dict] — dicts from build_intent_message()
    ) -> Conflict | None:
        """Compare own path against peer intents and return the highest-priority conflict,
        or None if no conflict is detected.
        """
        if not own_path or not own_path.waypoints or not peer_intents:
            return None

        # Standardize own waypoints: list of (x, y, tick)
        own_wps = self._extract_waypoints(own_path.waypoints, own_state.timestamp)
        if not own_wps:
            return None

        candidates: list[Conflict] = []

        for peer in peer_intents:
            peer_id = peer.get("robotId")
            if not peer_id or peer_id == own_state.robotId:
                continue

            # Skip offline robots
            if peer.get("status") == "OFFLINE":
                continue

            peer_path_raw = peer.get("plannedPath") or []
            peer_ts = peer.get("timestamp", own_state.timestamp)
            peer_wps = self._extract_waypoints(peer_path_raw, peer_ts)
            if not peer_wps:
                continue

            # 1. Check for SAME_CELL conflict (same cell at same tick)
            same_cell_conflict = self._check_same_cell(
                own_state.robotId, peer_id, own_wps, peer_wps
            )
            if same_cell_conflict:
                candidates.append(same_cell_conflict)

            # 2. Check for CROSSING conflict (edge swap between t and t+1)
            crossing_conflict = self._check_crossing(
                own_state.robotId, peer_id, own_wps, peer_wps, own_state.position, peer.get("position")
            )
            if crossing_conflict:
                candidates.append(crossing_conflict)

            # 3. Check for NARROW_AISLE_HEADON conflict (approaching each other along an aisle)
            headon_conflict = self._check_headon(
                own_state.robotId, peer_id, own_wps, peer_wps
            )
            if headon_conflict:
                candidates.append(headon_conflict)

        if not candidates:
            return None

        # Return earliest predicted conflict; break ties with severity
        severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        candidates.sort(
            key=lambda c: (c.predictedTick, severity_order.get(c.severity, 99), c.conflictId)
        )
        return candidates[0]

    def _extract_waypoints(
        self, raw_waypoints: list, base_tick: int
    ) -> list[tuple[int, int, int]]:
        """Normalize waypoints into a list of (x, y, tick) tuples."""
        result: list[tuple[int, int, int]] = []
        for i, wp in enumerate(raw_waypoints):
            if isinstance(wp, Position):
                t = wp.tick if wp.tick is not None else (base_tick + i + 1)
                result.append((wp.x, wp.y, t))
            elif isinstance(wp, dict):
                x = wp.get("x")
                y = wp.get("y")
                t = wp.get("tick")
                if t is None:
                    t = base_tick + i + 1
                if x is not None and y is not None:
                    result.append((x, y, t))
            elif isinstance(wp, (tuple, list)) and len(wp) >= 2:
                x, y = wp[0], wp[1]
                t = wp[2] if len(wp) >= 3 and wp[2] is not None else (base_tick + i + 1)
                result.append((x, y, t))
        return result

    def _check_same_cell(
        self,
        own_id: str,
        peer_id: str,
        own_wps: list[tuple[int, int, int]],
        peer_wps: list[tuple[int, int, int]],
    ) -> Conflict | None:
        """Detect same cell occupancy at the same tick."""
        peer_dict = {(x, y, t) for (x, y, t) in peer_wps}
        for (x, y, t) in own_wps:
            if (x, y, t) in peer_dict:
                return Conflict(
                    conflictId=f"conf_same_{own_id}_{peer_id}_{t}",
                    robotIds=[own_id, peer_id],
                    type="SAME_CELL",
                    predictedCell=Position(x=x, y=y, tick=t),
                    predictedTick=t,
                    severity="HIGH",
                    resolutionAction=None,
                )
        return None

    def _check_crossing(
        self,
        own_id: str,
        peer_id: str,
        own_wps: list[tuple[int, int, int]],
        peer_wps: list[tuple[int, int, int]],
        own_pos: Position | None,
        peer_pos_raw,
    ) -> Conflict | None:
        """Detect edge-crossing (swap) where A moves u->v and B moves v->u between t and t+1."""
        # Build timeline for own: tick -> (x, y)
        own_by_tick = {t: (x, y) for (x, y, t) in own_wps}
        peer_by_tick = {t: (x, y) for (x, y, t) in peer_wps}

        # Include current positions at t_start if known
        all_ticks = sorted(set(own_by_tick.keys()) & set(peer_by_tick.keys()))
        for t in all_ticks:
            next_t = t + 1
            if next_t in own_by_tick and next_t in peer_by_tick:
                own_curr = own_by_tick[t]
                own_next = own_by_tick[next_t]
                peer_curr = peer_by_tick[t]
                peer_next = peer_by_tick[next_t]

                # Swap check: own moves u -> v, peer moves v -> u
                if own_curr == peer_next and own_next == peer_curr and own_curr != own_next:
                    return Conflict(
                        conflictId=f"conf_cross_{own_id}_{peer_id}_{next_t}",
                        robotIds=[own_id, peer_id],
                        type="CROSSING",
                        predictedCell=Position(x=own_next[0], y=own_next[1], tick=next_t),
                        predictedTick=next_t,
                        severity="HIGH",
                        resolutionAction=None,
                    )
        return None

    def _check_headon(
        self,
        own_id: str,
        peer_id: str,
        own_wps: list[tuple[int, int, int]],
        peer_wps: list[tuple[int, int, int]],
    ) -> Conflict | None:
        """Detect robots moving toward each other head-on along an aisle."""
        # Check if consecutive waypoint pairs move in opposite directions along same collinear cells
        own_coords = [(x, y) for (x, y, t) in own_wps]
        peer_coords = [(x, y) for (x, y, t) in peer_wps]

        for i in range(len(own_coords) - 1):
            u, v = own_coords[i], own_coords[i + 1]
            for j in range(len(peer_coords) - 1):
                p_u, p_v = peer_coords[j], peer_coords[j + 1]
                # Opposite movement on the same corridor segment: u->v vs v->u
                if u == p_v and v == p_u:
                    t_own = own_wps[i + 1][2]
                    t_peer = peer_wps[j + 1][2]
                    meeting_tick = max(t_own, t_peer)
                    return Conflict(
                        conflictId=f"conf_headon_{own_id}_{peer_id}_{meeting_tick}",
                        robotIds=[own_id, peer_id],
                        type="NARROW_AISLE_HEADON",
                        predictedCell=Position(x=v[0], y=v[1], tick=meeting_tick),
                        predictedTick=meeting_tick,
                        severity="HIGH",
                        resolutionAction=None,
                    )
        return None
