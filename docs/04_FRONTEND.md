# 04 — Frontend / Fleet Dashboard — Implementation Specification
**Member 4 · Synced with `SIH_26123_Project_Overview.md` v2 · Canonical contracts: `docs/00_SHARED_CONTRACTS.md` / `shared/python/models.py`**

---

## 1. Module Purpose

You build the live fleet monitoring dashboard — the thing a judge actually watches during the demo. You are a leaf node in the dependency graph: nobody depends on your output, which means you should never be blocked by anyone else either.

## 2. System Context

```text
[ YOU: React Dashboard ] ──REST/WS──▶ Java Backend ──REST(control)──▶ Python Sim Engine
                                              ▲                                │
                                              └────────REST(data push)─────────┘
```
You talk **only** to the Java backend — never directly to the Python simulation engine. The backend is the single facade for everything you need.

## 3. Your Place in the Architecture

```text
Backend REST (initial load) + WebSocket (live updates)
      ↓
   Dashboard (you)
      ↓
Warehouse map · Robot status · Task panel · Alerts · Performance
```

## 4. What You Own

```text
dashboard/src/api/client.ts       — real API client
dashboard/src/api/mock.ts         — mock data source, schema-identical to real contracts
dashboard/src/components/*.tsx
dashboard/src/types/contracts.ts  — TS interfaces mirroring shared/python/models.py
dashboard/src/App.tsx
```

## 5. Reads / Consumes

Via Java backend: `GET /api/robots`, `GET /api/tasks`, `GET /api/warehouse`, `GET /api/metrics`, and the `/ws/live` WebSocket feed (see §9). Before integration: your own mock data in `mock.ts`.

## 6. Produces

Nothing consumed by other modules — you're a display leaf.

## 7. Must Not Modify

`backend/` (Member 6), `planner/`, `robot_agent/`, `collision_engine/`, `edge/` (Members 1/2/3/5).

## 8. Complete Responsibilities & Implementation Requirements

**8.1 Warehouse map view.** Render the grid: walls/obstacles, choke points, pickup/drop points, robots (current position + heading), planned routes (from `RobotState.currentPath`), and dynamically blocked cells. Update live as `RobotState` batches arrive over WebSocket.

**8.2 Robot status panel.** Per robot: ID, position, battery, current task, status (`IDLE|MOVING|WAITING|BLOCKED|CHARGING|OFFLINE` — style each distinctly, `OFFLINE` should be visually unmistakable since it's a key demo moment), current route.

**8.3 Task panel.** Grouped by status: Pending / In Progress / Completed / Reassigned, sourced from `Task`.

**8.4 Alerts feed.** Driven directly by `SimulationEvent` — render a human-readable line per event type (`CONFLICT_DETECTED`, `DEADLOCK_DETECTED`, `AISLE_BLOCKED`, `ROBOT_UNAVAILABLE`, `TASK_REASSIGNED`, `REROUTE`), newest first, with the tick number.

**8.5 Performance panel.** Sourced from `PerformanceMetric`, keyed by `mode`: total/avg completion ticks, collision count, deadlock count, reroutes, throughput, and a clear visual comparison across `STOP_AND_WAIT`, `CENTRALIZED_RESERVATION`, `DECENTRALIZED_PROPOSED` — this is the judge-facing evidence, make the comparison the visual centerpiece, not an afterthought.

**8.6 Resilience demo affordance.** Since the demo script includes killing the Java backend mid-run to prove decentralization, the dashboard should degrade visibly-but-gracefully (e.g., "connection lost" banner) rather than crash or blank out — this is itself part of what you're proving.

## 9. Exact Interfaces

```typescript
// dashboard/src/types/contracts.ts
interface Position { x: number; y: number; tick?: number | null; }
interface RobotState {
  robotId: string; position: Position; velocity: number; battery: number;
  currentTaskId: string | null; destination: Position | null;
  currentPath: Position[]; status: "IDLE"|"MOVING"|"WAITING"|"BLOCKED"|"CHARGING"|"OFFLINE";
  timestamp: number;
}
interface Task { taskId: string; pickupPosition: Position; dropPosition: Position;
  priority: number; status: "PENDING"|"ASSIGNED"|"IN_PROGRESS"|"COMPLETED"|"REASSIGNED"|"FAILED";
  createdAtTick: number; }
interface SimulationEvent { eventId: string; type: string; tick: number; payload: Record<string, unknown>; }
interface PerformanceMetric { runId: string; scenarioId: string;
  mode: "STOP_AND_WAIT"|"CENTRALIZED_RESERVATION"|"DECENTRALIZED_PROPOSED";
  totalCompletionTicks: number; avgCompletionTicks: number; collisionCount: number;
  deadlockCount: number; rerouteCount: number; idleTicksTotal: number;
  messageCount: number; seed: number; }

// dashboard/src/api/client.ts
async function fetchRobots(): Promise<RobotState[]>;         // GET /api/robots
async function fetchTasks(): Promise<Task[]>;                 // GET /api/tasks
async function fetchWarehouseMap(): Promise<WarehouseMap>;    // GET /api/warehouse
async function fetchMetrics(scenarioId: string): Promise<PerformanceMetric[]>; // GET /api/metrics?scenarioId=
function connectLiveFeed(onMessage: (msg: LiveWsMessage) => void): WebSocket;  // /ws/live

// WebSocket envelope (matches backend's LiveUpdateBroadcaster)
type LiveWsMessage =
  | { type: "ROBOT_STATE_BATCH"; tick: number; payload: RobotState[] }
  | { type: "SIMULATION_EVENT"; tick: number; payload: SimulationEvent }
  | { type: "METRIC_UPDATE"; tick: number; payload: PerformanceMetric };
```

## 10. How My Module Affects Other Modules

Nothing downstream depends on your output — you're purely a consumer/display layer.

## 11. How Other Modules Affect My Module

```text
Backend REST endpoints (Member 6)
    → your initial data load (robots, tasks, warehouse map, metrics)
Backend /ws/live feed (Member 6, relaying Member 3's tick-by-tick pushes)
    → your live updates; if this changes shape, your rendering breaks
```

## 12. Integration Points

| My Module | Other Module | Data/Interface | Direction | Purpose |
|---|---|---|---|---|
| Dashboard | Backend | REST (`/api/robots`, `/api/tasks`, `/api/warehouse`, `/api/metrics`) | Backend → Dashboard | Initial load |
| Dashboard | Backend | WebSocket `/ws/live` | Backend → Dashboard | Live updates |

## 13. Failure / Missing-Dependency Behavior

- **Backend unreachable**: show a clear "disconnected" state, keep the last-known map/robot positions visible rather than blanking the screen — this directly supports the demo's resilience narrative (robots keep working even if you can't see them live for a moment).
- **WebSocket drops**: attempt reconnect with backoff; fall back to periodic REST polling if reconnect fails repeatedly.
- **Malformed/unexpected payload shape**: log and skip that update rather than crashing the whole render.

## 14. Mock-First Development

| Real dependency | Mock while developing | Integration replacement |
|---|---|---|
| `GET /api/robots`, `/api/tasks`, `/api/warehouse`, `/api/metrics` | `mock.ts` returning static, schema-compliant fixtures | Swap the data-fetching function only; rendering components never change |
| `/ws/live` | A mock WebSocket-like object emitting fixture `LiveWsMessage`s on a timer | Swap `connectLiveFeed()`'s implementation only |

Build every component against `mock.ts` first. Keep data-fetching and rendering strictly decoupled (e.g., components take data as props, never fetch internally) so the mock-to-real swap touches only `api/`, never `components/`.

## 15. Testing Strategy

- Component tests against fixture data matching the TS interfaces in §9 exactly.
- A manual "mock live feed" mode (timer-driven fake WebSocket messages) to visually verify the map/status/alerts update correctly before the real backend exists.

## 16. AI Coding Boundary

> You own `dashboard/`. Do not modify `backend/`, `planner/`, `robot_agent/`, `collision_engine/`, or `edge/`. Build against `mock.ts` matching the TS interfaces in §9 exactly — don't invent field names; if a real backend response looks different from these interfaces, that's a bug to report, not something to silently adapt around. Keep data-fetching and rendering decoupled. Inspect existing code before modifying. Show diffs. Write component tests. Don't restructure the repository.

## 17. Definition of Done

- Map, robot status, task panel, alerts, and performance panels all render correctly against `mock.ts`.
- Live updates via a mock WebSocket correctly update the map and alerts feed in real time.
- Real backend integration is a source-swap in `api/client.ts` only, not a component rewrite.
- Disconnection state is visually clear and doesn't crash the app.
- Performance panel makes the three-way mode comparison the visual centerpiece.
