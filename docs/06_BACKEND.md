# 06 — Backend + Integration — Implementation Specification
**Member 6 · Synced with `SIH_26123_Project_Overview.md` v2 · Canonical contracts: `docs/00_SHARED_CONTRACTS.md` / `shared/python/models.py`**

---

## 1. Module Purpose

You build the Java/Spring Boot backend: the single front door for the dashboard, the task management system, the persistence layer, and — critically — the bridge between the Python simulation engine and everything else. You're also the team's integration lead and own the repo-wide run tooling.

## 2. System Context

```text
React Dashboard ──REST/WS──▶ [ YOU: Java Backend ] ──REST(control)──▶ Python Sim Engine
                                    ▲                                        │
                                    └──────────────REST(data push)───────────┘
```
**This Python↔Java boundary is FROZEN, not a team decision to relitigate:** your backend is a REST *client* to the Python simulation's small FastAPI control server (start/stop/select scenario+mode), and a REST *server* that the Python side pushes telemetry/events/metrics into. The dashboard only ever talks to you.

## 3. Your Place in the Architecture

```text
Robot Agents (Python, Member 3) ──telemetry/events/metrics──▶ Backend (you)
                                                                    │
                                                              Postgres/SQLite
                                                                    │
                                                          REST + WebSocket
                                                                    ↓
                                                          Dashboard (Member 4)
```

## 4. What You Own

```text
backend/src/main/java/com/sih26123/backend/
  BackendApplication.java
  controller/RobotController.java
  controller/TaskController.java
  controller/WarehouseController.java
  controller/TelemetryIngestController.java
  controller/EventIngestController.java
  controller/MetricsController.java
  controller/SimulationControlController.java
  model/                              — Java DTOs mirroring shared/python/models.py
  service/TaskAllocationService.java
  service/SimulationClient.java       — HTTP client → Python FastAPI control server
  service/LiveUpdateBroadcaster.java
  websocket/LiveUpdateWebSocketHandler.java
  repository/
scripts/run_all.sh                    — one-command startup for the whole team
docker-compose.yml                    — optional, demo-day reliability
```

## 5. Reads / Consumes

Pushed from Python: `RobotState` (batched), `SimulationEvent`, `PerformanceMetric`. From the dashboard: task-creation requests, simulation control requests.

## 6. Produces

`Task`, `TaskAssignment` (sent to Python via the `/control/start` payload), REST responses and WebSocket frames (to the dashboard).

## 7. Must Not Modify

`planner/`, `collision_engine/`, `robot_agent/`, `edge/`, `simulation/`, `dashboard/`.

## 8. Complete Responsibilities & Implementation Requirements

**8.1 REST API.**
```text
GET  /api/robots                    → list of latest RobotState (from in-memory cache, refreshed by ingestion)
GET  /api/robots/{id}               → single RobotState
GET  /api/tasks                     → list of Task
POST /api/tasks                     → create a Task, status=PENDING
GET  /api/warehouse                 → WarehouseMap (fetched once from Python at run start, cached)
GET  /api/metrics?scenarioId=       → list of PerformanceMetric for that scenario, across modes
POST /api/simulation/control        → {action: "start"|"stop", scenarioId, mode, seed, speed}
                                       → delegates to SimulationClient → Python /control/*
GET  /api/simulation/status         → delegates to SimulationClient → Python /control/status
```

**8.2 Ingestion endpoints (Python pushes here).**
```text
POST /api/telemetry/batch  body: RobotState[]   — once per simulation tick
POST /api/events            body: SimulationEvent[] — once per tick, may be empty array
POST /api/metrics           body: PerformanceMetric — once at end of a run
```
Each ingestion handler updates the in-memory "latest state" cache used by `GET /api/robots`, persists to the database, and immediately republishes to `LiveUpdateBroadcaster` for WebSocket relay — ingest and broadcast in the same request, don't poll.

**8.3 Task allocation.** `TaskAllocationService`: a simple greedy/nearest-idle-robot heuristic. Do not add optimization (Hungarian algorithm, etc.) until this works — it's a reasonable Phase 5+ stretch, not a blocker. On `RobotState.status=OFFLINE` for a robot holding an active task, automatically reassign that task to the next nearest idle robot and emit an internal `TASK_REASSIGNED` record (this can be logged directly rather than round-tripping through Python, since task assignment is centralized here).

**8.4 `SimulationClient`.** A thin HTTP client wrapping calls to the Python FastAPI control server's `/control/start`, `/control/stop`, `/control/status` (default `http://localhost:8001`, configurable).

**8.5 WebSocket.** `/ws/live` — on connect, sends a snapshot (`ROBOT_STATE_BATCH` with current cache); thereafter, `LiveUpdateBroadcaster` pushes `ROBOT_STATE_BATCH`, `SIMULATION_EVENT`, and `METRIC_UPDATE` frames as ingestion happens, matching the envelope Member 4 expects (see `04_FRONTEND.md` §9).

**8.6 Persistence.** SQLite for local dev (zero setup friction), Postgres-compatible via Spring Data JPA + Hibernate (swapping is a connection-string/dependency change, not a code change). Entities: `Robot`, `Task`, `TaskAssignment`, `Telemetry` (aggregated, not every raw tick), `Scenario`, `SimulationRun`, `PerformanceMetric`, `Event`. Don't persist every simulation tick permanently — aggregate/log sensibly (e.g., keep the latest `RobotState` per robot plus a periodic snapshot, not a row per tick per robot).

**8.7 Authentication.** Explicitly optional — do not build unless there's a concrete, stated reason to.

**8.8 `scripts/run_all.sh` / `docker-compose.yml`.** One command that starts the Python FastAPI simulation engine, the Java backend, and (in dev) points the team at `npm start` for the dashboard — so nobody has to remember four different "how do I run this" procedures.

## 9. Exact Interfaces

```java
// service/SimulationClient.java
public class SimulationClient {
    public void start(String scenarioId, String mode, long seed, String speed) { /* POST Python /control/start */ }
    public void stop() { /* POST Python /control/stop */ }
    public SimulationStatus status() { /* GET Python /control/status */ }
}

// controller/TelemetryIngestController.java
@PostMapping("/api/telemetry/batch")
public ResponseEntity<Void> ingest(@RequestBody List<RobotStateDto> batch) { ... }

// websocket envelope pushed via LiveUpdateBroadcaster, consumed by Member 4:
// { "type": "ROBOT_STATE_BATCH" | "SIMULATION_EVENT" | "METRIC_UPDATE",
//   "tick": <int>, "payload": <...> }
```

## 10. How My Module Affects Other Modules

```text
Backend
    ↓
Task, TaskAssignment → Python's simulation runner (via /control/start payload):
    determines each robot's start/goal for that run
    ↓
REST + WebSocket → Dashboard: everything Member 4 renders comes from you
    ↓
SimulationClient calls → Python's control server: starts/stops runs, selects mode
```

## 11. How Other Modules Affect My Module

```text
RobotState / SimulationEvent / PerformanceMetric (pushed by Member 3's runner)
    → your ingestion endpoints, cache, persistence, and WebSocket relay
```

## 12. Integration Points

| My Module | Other Module | Data/Interface | Direction | Purpose |
|---|---|---|---|---|
| Backend | Python Sim Engine | REST (`/control/*`) | Backend → Python | Start/stop/select scenario+mode |
| Backend | Python Sim Engine | REST (`/api/telemetry/batch`, `/api/events`, `/api/metrics`) | Python → Backend | Data ingestion |
| Backend | Dashboard | REST (`/api/*`) | Backend → Dashboard | Initial load |
| Backend | Dashboard | WebSocket `/ws/live` | Backend → Dashboard | Live updates |

## 13. Failure / Missing-Dependency Behavior

- **Python simulation engine unreachable** (control server down): `/api/simulation/control` returns a clear error to the dashboard; existing cached robot/task data continues to be served from the last known state — the backend doesn't crash just because its data source is temporarily gone.
- **A single ingestion POST is malformed**: log and reject that specific batch (HTTP 400), don't let it take down the ingestion endpoint for subsequent valid batches.
- **No WebSocket clients connected**: `LiveUpdateBroadcaster` should be a no-op broadcast, not an error.

## 14. Mock-First Development

| Real dependency | Mock while developing | Integration replacement |
|---|---|---|
| Real `Telemetry`/`SimulationEvent`/`PerformanceMetric` pushes from Python | A tiny script that POSTs fake telemetry batches at 1Hz to your own ingestion endpoints | No change needed — same endpoints, real data source |
| Real Python control server | `curl`/Postman against a stub that returns fixed status JSON | Swap `SimulationClient`'s base URL only |

All REST endpoints can return hardcoded/seeded data before any other module exists — you're never blocked at the start.

## 15. Testing Strategy

- Controller tests: each endpoint returns correctly-shaped JSON against seeded/mock data.
- `TelemetryIngestController` test: POST a batch, confirm the cache updates and a WebSocket frame is emitted.
- `SimulationClient` test: against a local mock HTTP server standing in for the Python control API.
- `TaskAllocationService` test: robot goes `OFFLINE` mid-task → task reassigned to another idle robot.

## 16. AI Coding Boundary

> You own `backend/` and repo tooling (`scripts/`, `docker-compose.yml`). Do not modify `planner/`, `collision_engine/`, `robot_agent/`, `edge/`, `simulation/`, or `dashboard/`. Follow the DTO field names in `docs/00_SHARED_CONTRACTS.md` exactly — they must mirror `shared/python/models.py`. Don't build authentication unless explicitly requested. Inspect existing code before modifying. Show diffs. Write tests. Don't restructure the repository, and don't assume Python-side implementation details beyond the documented `/control/*` and ingestion contracts — ask if unclear.

## 17. Definition of Done

- All listed REST endpoints work against real, persisted data.
- Ingestion endpoints correctly update cache, persist, and broadcast over WebSocket in the same request.
- `SimulationClient` successfully starts/stops/queries the real Python control server.
- Task assignment (simple heuristic) and offline-triggered reassignment work end-to-end.
- Backend keeps serving cached data and doesn't crash when the Python engine is killed mid-run — this is directly demoed as proof of resilience.
- `scripts/run_all.sh` reliably starts the whole system for any teammate.
