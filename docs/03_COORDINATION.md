# 03 — Multi-Agent Coordination — Implementation Specification
**Member 3 · Synced with `SIH_26123_Project_Overview.md` v2 · Canonical contracts: `docs/00_SHARED_CONTRACTS.md` / `shared/python/models.py`**

---

## 1. Module Purpose

You own the most cross-cutting part of the system: conflict detection and resolution, deadlock recovery, the `RobotAgent` orchestration loop that every other Python module plugs into, the simulation runner (including the FastAPI control server that the Java backend talks to), the demo scenarios, and the independent collision referee. This is a large role by design — it's the integration point of the robot-side system, so it needs someone who can see across all the other modules.

## 2. System Context

```text
React Dashboard ──REST/WS──▶ Java Backend ──REST(control: start/stop/scenario/mode)──▶ [ YOU: simulation/runner.py ]
                                    ▲                                                         │
                                    └────────────────REST(data push: telemetry/events/metrics)─┘

Inside simulation/runner.py, per tick, per robot:
  Edge.read() → [ YOU: RobotAgent.tick() ] → Planner.plan() → Communication.broadcast/receive
      → [ YOU: ConflictDetector/Resolver/DeadlockDetector ] → move → report
```
Task assignment is centralized in the Java backend; movement-level conflict resolution — the part you own — is decentralized between robot agents and must keep working even if the backend is unreachable.

## 3. Your Place in the Architecture

```text
RobotPath (Member 1) ─┐
                       ├─→ ConflictDetector (you) → Conflict → ConflictResolver (you) → action
Incoming intents (Member 2) ─┘
                                                       ↓
                                          RobotAgent.tick() (you) orchestrates
                                    Planner + Communication + Edge every tick
                                                       ↓
                                     simulation/runner.py (you) drives N agents,
                                  switches STOP_AND_WAIT / CENTRALIZED_RESERVATION /
                                       DECENTRALIZED_PROPOSED, pushes results to Java
```

## 4. What You Own

```text
collision_engine/detection.py     — ConflictDetector
collision_engine/deadlock.py      — DeadlockDetector
collision_engine/resolution.py    — ConflictResolver, priority rules
robot_agent/agent.py              — RobotAgent, tick() orchestration loop
                                     (written together with the whole team in the Phase-0
                                     kickoff as a skeleton; you maintain it afterward)
simulation/runner.py              — FastAPI control server, tick driver, mode switching,
                                     STOP_AND_WAIT stripped-down agent
simulation/referee.py             — independent collision referee (ground-truth, NOT
                                     using your own ConflictDetector — see §8.6)
simulation/scenarios/*.py         — all eight demo scenarios
collision_engine/tests/, robot_agent/tests/test_agent.py, simulation/tests/
```

## 5. Reads / Consumes

`RobotPath` (Member 1), incoming intent messages (Member 2), `Telemetry` (Member 5), `WarehouseMap` (Member 1), `TaskAssignment` (from Java backend, delivered to the control server on `/control/start`).

## 6. Produces

`Conflict`, resolution actions, `SimulationEvent(CONFLICT_DETECTED / DEADLOCK_DETECTED / REROUTE)`, `PerformanceMetric` (at end of each run), and the `RobotState` that gets pushed to the Java backend every tick.

## 7. Must Not Modify

`robot_agent/communication/` (Member 2), `planner/` (Member 1, except calling its public `plan()`/`plan_centralized()` functions), `edge/` (Member 5, except calling `SensorSource.read()`), `backend/`, `dashboard/`. Because `agent.py` and `runner.py` call into everything, it's tempting to "just fix" another module's stub during integration — don't; flag it to the owner instead.

## 8. Complete Responsibilities & Implementation Requirements

**8.1 `ConflictDetector`.** From broadcast intents (not ground truth — this must work from what robots *tell each other*, which is the realistic constraint): detect same-cell/same-time occupancy, crossing paths, and narrow-aisle head-on approaches, by comparing your own `RobotPath` waypoints against peers' broadcast `plannedPath`.

**8.2 `ConflictResolver`.** Deterministic priority rules, in order: (1) emergency/high-priority task, (2) higher `Task.priority`, (3) robot already inside the contested cell/critical section, (4) lower estimated rerouting cost, (5) `robotId` as a final tie-breaker. Returns one of `CONTINUE | WAIT | YIELD | REROUTE | REASSIGN_TASK`.

**8.3 `DeadlockDetector` — simplified by design.** Full wait-for-graph cycle detection is more than an MVP needs. Implement: if a robot has made no progress for `N` ticks while waiting on a specific peer, force the lower-priority robot in that pair to yield and replan. This covers the 2-robot and typical 3-robot deadlocks in your demo scenarios with a fraction of the code. True cycle detection is an optional Phase 4+ enhancement, not required.

**8.4 `RobotAgent.tick()`.** The shell every other module plugs into. Written together by the whole team in the Phase-0 kickoff (2–3 hours) as a skeleton with stub calls, so everyone sees the shape before splitting off — you maintain and extend it afterward, in small PRs, because many other members' work depends on its call signatures staying predictable:
```python
def tick(self, current_tick: int) -> RobotState:
    telemetry = self.sensor.read(self.robot_id)                    # Member 5
    self.state = self._apply_telemetry(self.state, telemetry, current_tick)
    if self._needs_replan():
        self.state.currentPath = self.planner.plan(                # Member 1
            self.state.position, self.state.destination,
            self._known_blocked_cells())
    incoming = self.transport.receive(self.robot_id)                # Member 2
    conflict = self.detector.detect(self.state, self.state.currentPath, incoming)
    if conflict:
        action = self.resolver.resolve(conflict, self.state, incoming)
        self._apply_action(action, conflict)
    if self.deadlock.check(self.robot_id, self._stall_ticks, self._waiting_on):
        self._force_yield()
    self._advance_one_cell_if_clear()
    self.transport.broadcast(build_intent_message(self.state))      # Member 2
    self.state.timestamp = current_tick
    return self.state
```

**8.5 `simulation/runner.py` — the FastAPI control server and tick driver.** Exposes:
```text
POST /control/start   {scenarioId, mode, seed}
POST /control/stop
GET  /control/status  -> {running, currentTick, scenarioId, mode}
```
On `/control/start`, loads the named scenario, constructs N `RobotAgent`s (`DECENTRALIZED_PROPOSED` mode) or runs the stripped-down `stop_and_wait_step()` driver (`STOP_AND_WAIT` mode) or calls `planner.plan_centralized()` once up front then just executes the resulting schedule (`CENTRALIZED_RESERVATION` mode). Runs at `LIVE` speed (throttled ~2 ticks/sec, sleeping between ticks) or `BATCH` speed (unthrottled) depending on a request flag. Every tick, batches all robots' `RobotState` plus any `SimulationEvent`s generated that tick and `POST`s them to the Java backend's `/api/telemetry/batch` and `/api/events`. At run end, computes and `POST`s a `PerformanceMetric` to `/api/metrics`.

**8.6 `simulation/referee.py` — independent collision check.** A separate, simple ground-truth bounding-box/cell-overlap checker reading actual robot positions directly — **not** using `ConflictDetector`. This is deliberate: don't let the same logic that avoids collisions also certify that none happened, that's circular and won't survive a sharp judge's question. Called every tick by the runner; tallied into `PerformanceMetric.collisionCount`.

**8.7 Scenarios.** Eight scenario files, each constructing a `Scenario` (map reference, robot start/goal pairs, seed, scripted events like "block cell (10,5) at tick 50", max ticks): (a) normal movement, (b) intersection conflict, (c) narrow aisle head-on, (d) deadlock, (e) blocked aisle, (f) task reassignment (paired with Member 5's fault injection to knock a robot offline), (g) high fleet load, (h) **negative control** — a scenario with no possible conflicts, included specifically to preempt "did you only test easy cases?" from judges.

## 9. Exact Interfaces

```python
# collision_engine/detection.py
class ConflictDetector:
    def detect(self, own_state: RobotState, own_path: RobotPath,
               peer_intents: list[dict]) -> Conflict | None: ...

# collision_engine/resolution.py
class ConflictResolver:
    def resolve(self, conflict: Conflict, own_state: RobotState,
                peer_intents: list[dict]) -> str:
        """Returns one of CONTINUE|WAIT|YIELD|REROUTE|REASSIGN_TASK."""

# collision_engine/deadlock.py
class DeadlockDetector:
    def check(self, robot_id: str, stall_ticks: int, waiting_on: str | None) -> bool: ...

# robot_agent/agent.py
class RobotAgent:
    def __init__(self, robot_id: str, planner: Planner, transport: Transport,
                 sensor: SensorSource, detector: ConflictDetector,
                 resolver: ConflictResolver, deadlock: DeadlockDetector): ...
    def tick(self, current_tick: int) -> RobotState: ...

# simulation/referee.py
class CollisionReferee:
    def check(self, all_positions: dict[str, Position]) -> list[tuple[str, str]]:
        """Ground-truth overlap check. Returns colliding robot ID pairs this tick."""

# simulation/runner.py — FastAPI app, default port 8001
# POST /control/start {scenarioId: str, mode: str, seed: int, speed: "LIVE"|"BATCH"}
# POST /control/stop
# GET  /control/status
```

## 10. How My Module Affects Other Modules

```text
Coordination
    ↓
Conflict / resolution actions → Robot Agent movement (your own tick(), but conceptually a boundary)
    ↓
SimulationEvent(CONFLICT_DETECTED/DEADLOCK_DETECTED/REROUTE) → Backend → Dashboard alerts
    ↓
RobotState (batched every tick) → Backend → Dashboard's live map/status panels
    ↓
PerformanceMetric (end of run) → Backend → Dashboard's performance panel, the judge-facing evidence
    ↓
plan_centralized() invocation → Member 1's code, but the *decision* of when to call it is yours
```

## 11. How Other Modules Affect My Module

```text
RobotPath (Member 1)
    → primary input to ConflictDetector
Incoming intents (Member 2)
    → primary input to ConflictDetector; if the bus is degraded (fault injection),
      your detector sees fewer/late messages, which is intentionally part of the
      resilience story, not a bug to work around
Telemetry (Member 5)
    → folded into RobotState every tick inside tick(); OFFLINE sensorHealth
      triggers the task-reassignment path
TaskAssignment (Java backend, via /control/start payload)
    → determines each robot's start/goal for the scenario run
```

## 12. Integration Points

| My Module | Other Module | Data/Interface | Direction | Purpose |
|---|---|---|---|---|
| Coordination | Planner | `RobotPath` | Planner → Coordination | Conflict prediction |
| Coordination | Communication | intent messages | Communication → Coordination | Conflict detection input |
| Coordination | Edge | `Telemetry` | Edge → Coordination | Sensor/state updates in `tick()` |
| Simulation Runner | Backend | REST (control) | Backend → Runner | Start/stop/select scenario+mode |
| Simulation Runner | Backend | REST (data push) | Runner → Backend | Telemetry/events/metrics |

## 13. Failure / Missing-Dependency Behavior

- **Planner unavailable / raises `PlanningFailedError`**: robot enters `status=BLOCKED`, retries next tick — never crashes the loop.
- **No communication messages this tick**: treat as "no known conflicts," proceed — this is the resilience property, not an error state.
- **No sensor data / stale telemetry**: mark `sensorHealth != OK`, and after enough missed heartbeats, transition `RobotState.status = OFFLINE`, emit `SimulationEvent(ROBOT_UNAVAILABLE)`.
- **Backend unreachable** (control server can't reach `/api/telemetry/batch`): the simulation **keeps running** — this is the headline resilience demonstration. Buffer unsent batches locally and retry, don't halt the simulation on a failed POST.

## 14. Mock-First Development

| Real dependency | Mock while developing | Integration replacement |
|---|---|---|
| Real `RobotPath` from Member 1 | Two fabricated hardcoded `RobotPath` objects that overlap in (cell, tick) | Same `ConflictDetector.detect()` signature |
| Real messages from Member 2 | Fabricated intent dicts | Same `Transport.receive()` signature |
| Real `Telemetry` from Member 5 | Fabricated `Telemetry` objects | Same `SensorSource.read()` signature |
| Real Java backend | `curl`/Postman against your own FastAPI control server directly | Same REST contract either way |

## 15. Testing Strategy

- `ConflictDetector`: fabricated overlapping paths → confirm `Conflict` returned; non-overlapping paths → confirm `None`.
- `DeadlockDetector`: fabricated stalled-robot scenario → confirm yield triggered after `N` ticks.
- `CollisionReferee`: fabricated overlapping ground-truth positions → confirm flagged, independent of any `Conflict` object.
- Scenario tests: each of the 8 scenarios runs to completion within `max_ticks` in `BATCH` mode without crashing.
- `tick()` integration test: full loop with all dependencies mocked, confirm it returns a well-formed `RobotState`.

## 16. AI Coding Boundary

> You own `collision_engine/`, `robot_agent/agent.py`, `simulation/runner.py`, `simulation/referee.py`, `simulation/scenarios/`. Do not modify `robot_agent/communication/`, `planner/`, `edge/`, `backend/`, or `dashboard/` — even when integration reveals another module's stub looks wrong, flag it to that owner rather than fixing it yourself. Import contracts from `shared/python/models.py`. Keep changes to `agent.py` small and incremental — it's the most cross-cutting file in the repo and multiple other members' work depends on its call signatures. Never let the collision referee (`simulation/referee.py`) call into or depend on `collision_engine/detection.py` — they must stay independent. Inspect existing code before modifying. Show diffs. Write tests. Don't restructure the repository.

## 17. Definition of Done

- Conflict detection and priority resolution work against live paths and messages, tested.
- Deadlock recovery resolves the 2-robot and typical 3-robot cases across the demo scenarios.
- `tick()` is stable enough that Members 1, 2, and 5 haven't needed to change their call signatures in the final week.
- `simulation/runner.py`'s FastAPI server correctly starts/stops/reports status and survives the Java backend being killed mid-run.
- All eight scenarios run to completion in `BATCH` mode.
- `CollisionReferee` runs completely independently of `ConflictDetector` and both are exercised in tests.
- `PerformanceMetric` is correctly computed and pushed at the end of a run.
