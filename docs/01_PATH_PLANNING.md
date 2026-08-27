# 01 — Path Planning / Warehouse Map — Implementation Specification
**Member 1 · Synced with `SIH_26123_Project_Overview.md` v2 · Canonical contracts: `docs/00_SHARED_CONTRACTS.md` / `shared/python/models.py`**

---

## 1. Module Purpose

You build the warehouse's spatial model and every path-planning algorithm the system uses: the grid map, standard A* for individual robots, windowed replanning that treats other robots' claimed cells as temporary obstacles, and later the centralized-reservation baseline used as a strong comparison point. Nearly everything downstream — coordination, movement, the dashboard's map view — is built on top of what you produce.

## 2. System Context

```text
React Dashboard ──REST/WS──▶ Java Backend ──REST(control)──▶ Python Sim Engine
                                    ▲                                │
                                    └────────REST(data push)─────────┘

Inside the Python Sim Engine, per tick:
  Edge (sensors) → RobotAgent.tick() → [ YOU: Planner ] → Coordination → Communication → move
```
Task assignment (which robot does which pickup/delivery) is centralized in the Java backend. Movement-level conflict resolution is decentralized between robot agents — that's the part that must keep working even with the backend down, and it's why your `RobotPath` output feeds a peer-to-peer negotiation, not a central scheduler, in the default mode.

## 3. Your Place in the Architecture

```text
WarehouseMap (you)
      ↓
plan(start, goal, blocked_cells) → RobotPath (you)
      ↓
broadcast as intent (Member 2) ──▶ ConflictDetector (Member 3)
      ↓
if conflict: replan with peer cells as temp obstacles (you, called again by Member 3)
```

## 4. What You Own

```text
planner/astar.py                    — A* implementation, windowed replanning
planner/warehouse_map.py            — grid/graph model, WarehouseMap builder
planner/centralized_baseline.py     — reservation-table planning (Phase 4+, strong baseline)
simulation/warehouse/demo_map.py    — the actual dense demo WarehouseMap instance
planner/tests/
```

## 5. Reads / Consumes

- `shared/python/models.py` — `Position`, `RobotPath`, `WarehouseMap` (you also help define these, since you're their primary producer).
- Broadcast peer intents (from Member 2's transport) — used only for windowed replanning, read-only, never mutated by you.
- `SimulationEvent(type=AISLE_BLOCKED)` — tells you which cells just entered `blockedCells`.

## 6. Produces

- `WarehouseMap` — built once at simulation start, loaded by everyone.
- `RobotPath` — on every `plan()`/`replan()` call, consumed by `robot_agent/agent.py` (Member 3) and broadcast by `robot_agent/communication` (Member 2).

## 7. Must Not Modify

`robot_agent/agent.py`, `collision_engine/`, `robot_agent/communication/`, `simulation/runner.py`, `simulation/scenarios/`, `edge/`, `backend/`, `dashboard/`. If integration reveals one of these needs something different from you, say so to that module's owner — don't reach in and change it yourself.

## 8. Complete Responsibilities & Implementation Requirements

**8.1 Warehouse representation.** A 2D grid (`gridWidth × gridHeight`), not a graph — simpler to reason about, trivial to render on the dashboard, and standard for warehouse-aisle-style layouts. Each cell is walkable or an obstacle. `chokePoints` are specific cells you mark deliberately — narrow single-file aisles or intersections robots are likely to contest. **This is a first-class design task**: a sparse map with rare conflicts makes the whole system's improvement claim look weak, because stop-and-wait performs almost as well when robots rarely meet. Build the demo map with at least 2–3 unavoidable choke points that most start/goal pairs must pass through.

**8.2 A\*.** Standard grid A* with Manhattan-distance heuristic, 4-connected movement (no diagonals — keeps collision checking simple). Cost = number of ticks.

**8.3 Windowed replanning (the actual "decentralized MAPF" algorithm — name it this way to judges: related to Cooperative A\*/WHCA\*).** Each robot's `RobotPath` is computed independently first. When broadcast intents from other robots reveal a (cell, tick) collision with your own planned route, replan treating those specific (cell, tick) pairs as temporarily blocked. This is what makes "shared reservation-like" behavior possible without an actual central reservation table.

**8.4 Dynamic replanning on blockage.** On `SimulationEvent(AISLE_BLOCKED)`, invalidate the affected portion of the current path and replan around the newly blocked cells.

**8.5 Centralized-reservation baseline (Phase 4+).** A separate function, `plan_centralized(all_start_goals, warehouse_map) -> dict[robotId, RobotPath]`, that runs A* sequentially per robot against one shared space-time reservation table (each robot's chosen path reserves its (cell, tick) pairs before the next robot plans). This is what `CENTRALIZED_RESERVATION` mode uses — a strong, realistic baseline, not the weak stop-and-wait strawman.

## 9. Exact Interfaces

```python
# planner/warehouse_map.py
def build_warehouse_map(width: int, height: int, obstacles: list[Position],
                         choke_points: list[Position], pickup_points: list[Position],
                         drop_points: list[Position]) -> WarehouseMap: ...

# planner/astar.py
class Planner:
    def __init__(self, warehouse_map: WarehouseMap): ...

    def plan(self, start: Position, goal: Position, blocked_cells: list[Position],
             avoid_intervals: list[tuple[Position, int]] | None = None,
             start_tick: int = 0) -> RobotPath:
        """avoid_intervals: (cell, tick) pairs claimed by other robots' broadcast
        intents. Raises PlanningFailedError if no path exists — caller (RobotAgent)
        must catch this and set status=BLOCKED, not crash."""

    def replan(self, current_path: RobotPath, new_blocked_cells: list[Position],
               current_tick: int) -> RobotPath: ...

# planner/centralized_baseline.py
def plan_centralized(start_goals: dict[str, tuple[Position, Position]],
                      warehouse_map: WarehouseMap, seed: int) -> dict[str, RobotPath]:
    """Sequential prioritized planning against one shared reservation table.
    Order robots are planned in is determined by `seed` (deterministic, for
    reproducible evaluation runs)."""
```

## 10. How My Module Affects Other Modules

```text
Path Planning
    ↓
RobotPath → Coordination (Member 3): predicts conflicts, decides WAIT/YIELD/REROUTE
    ↓
RobotPath → Robot Agent (Member 3): the path it actually moves along
    ↓
RobotPath → Communication (Member 2): broadcast as intent for peer negotiation
    ↓
WarehouseMap → everyone: loaded once at sim start, including the dashboard's map view (via backend)
    ↓
plan_centralized() → simulation/runner.py (Member 3): powers the CENTRALIZED_RESERVATION comparison mode
```
If your `plan()` returns a bad path (crosses an obstacle, skips cells), every downstream module inherits the bug — this is the highest-leverage module to get right and test thoroughly.

## 11. How Other Modules Affect My Module

```text
WarehouseMap.blockedCells (mutated by simulation/scenarios, Member 3)
    → you must replan around it
Broadcast peer intents (Member 2's transport)
    → you use them for windowed replanning; if the bus is down, you plan without them (see §13)
Task.pickupPosition / Task.dropPosition (Member 6, via TaskAssignment)
    → become your start/goal inputs once real tasks exist
```

## 12. Integration Points

| My Module | Other Module | Data/Interface | Direction | Purpose |
|---|---|---|---|---|
| Planner | Coordination | `RobotPath` | Planner → Coordination | Conflict prediction |
| Planner | Robot Agent | `RobotPath` | Planner → Robot Agent | Movement |
| Planner | Communication | `RobotPath` | Planner → Communication | Broadcast as intent |
| Planner | Simulation Runner | `WarehouseMap`, `plan_centralized()` | Planner → Runner | Map load, baseline comparison |
| Communication | Planner | peer intents | Communication → Planner | Windowed replanning input |
| Simulation Scenarios | Planner | `blockedCells` updates | Scenarios → Planner | Dynamic replanning trigger |

## 13. Failure / Missing-Dependency Behavior

- **No peer intents available** (Member 2's bus not built yet, or genuinely empty this tick): `plan()` still works — `avoid_intervals` is optional and defaults to none. You are never blocked waiting on Member 2.
- **No path exists** (fully boxed in): raise `PlanningFailedError`; the caller (RobotAgent, Member 3) is responsible for setting `status=BLOCKED` and retrying later — you never crash the simulation.
- **`WarehouseMap` malformed** (e.g., start/goal on an obstacle cell): raise `InvalidMapError` at load time, fail loudly and early rather than producing a silently broken path.

## 14. Mock-First Development

| Real dependency | Mock while developing | Integration replacement |
|---|---|---|
| Real `Task` start/goal from backend | Hardcoded `(start, goal)` tuples | Swap the source of start/goal, `plan()` signature unchanged |
| Real peer intents from Member 2 | Empty list / hand-built fake intent list | `avoid_intervals` parameter is already optional — no code change needed |
| Real `AISLE_BLOCKED` events from Member 3's scenarios | Manually toggle `blocked_cells` in a test | Same `replan()` call, different trigger source |

You need nothing from anyone else to build and fully test this module.

## 15. Testing Strategy

- Unit tests: path validity (no obstacle overlap, connected waypoints, respects grid bounds) on a fixed hardcoded map.
- Windowed replanning test: two fabricated conflicting paths, confirm replanning avoids the claimed (cell, tick) pairs.
- `plan_centralized()` test: confirm no two robots' reserved (cell, tick) pairs collide across the whole batch.
- Run standalone with `python -m planner.astar` printing a path for a hardcoded start/goal — no other module needed.

## 16. AI Coding Boundary

> You own `planner/` and `simulation/warehouse/demo_map.py`. Do not modify `robot_agent/`, `collision_engine/`, `simulation/runner.py`, `simulation/scenarios/`, `edge/`, `backend/`, or `dashboard/` — if integrating with one of them reveals a problem, describe it, don't fix it yourself. Import contracts from `shared/python/models.py`; never redefine `Position`, `RobotPath`, or `WarehouseMap` locally. If a contract needs a new field, stop and propose it to the team rather than adding it silently. Inspect existing code before modifying it. Avoid unnecessary refactors. Show diffs before applying. Write tests for every function you add. Don't restructure the repository.

## 17. Definition of Done

- `plan()` produces valid, obstacle-free, tick-consistent paths on the demo map, unit-tested.
- Windowed replanning correctly avoids peer-claimed (cell, tick) pairs in a fabricated two-robot test.
- Demo map has ≥2 deliberate choke points verified to force conflicts in a basic 3+ robot run.
- `replan()` correctly reroutes around a newly blocked cell.
- `plan_centralized()` produces a collision-free schedule for the full fleet on the demo map, tested.
- All functions raise the documented exceptions instead of crashing on bad input.
