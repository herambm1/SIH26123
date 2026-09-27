# SIH 2026 — Project Overview
## Problem Statement 26123: Edge-AI Based Distributed Fleet Coordination for Autonomous Mobile Robots (AMRs) in Smart Warehouses
### Sponsor: Bharat Electronics Limited | Category: Software | Theme: Smart Automation

**Version: v2 — 2026-08-27.** This supersedes v1. Everything architectural from v1 still holds (hybrid centralization, the honest decentralization claim, MVP scope, Phase-0 requirement); v2 makes the previously-open implementation questions concrete and frozen, and is now backed by six fully detailed role documents in `docs/` and a real shared contracts module at `shared/python/models.py`. This document is the highest-level source of truth — it must not contradict the role documents; if you ever find a contradiction, the role documents win for implementation detail and this file should be corrected to match.

---

## 1. Project Goal

A software-first simulation and coordination framework for a fleet of AMRs (4–6 for demo purposes) operating inside a smart warehouse. Multiple robots may want the same aisle or intersection, approach each other head-on, deadlock, hit a newly blocked aisle, or need their tasks reassigned. Robots must make **local, real-time movement and conflict-resolution decisions** and communicate directly with nearby robots, rather than waiting on a central server for every step.

Demonstrated capabilities: robot-to-robot communication for conflict avoidance, multi-agent path planning, collision detection/avoidance, deadlock detection/resolution, dynamic rerouting, task allocation/reassignment, a live fleet dashboard, an architecture where movement intelligence lives at the robot/edge level, zero inter-robot collisions (independently verified), and a measurable improvement over **two** baselines, not one.

## 2. Scope Decision

Software category. No physical robot fleet. Primary deliverable: a multi-robot warehouse simulation + hybrid coordination software + live dashboard, running entirely without hardware. Physical hardware (Raspberry Pi/ESP32) is an optional, fully isolated bonus demo (see §14) whose failure cannot affect the core demonstration.

## 3. Core Architectural Principle

> **We are honest about what's centralized and what's decentralized, instead of pretending everything is decentralized.**

Real AMR fleets (Amazon Robotics, Locus, Geek+, OTTO) run centralized fleet managers on local networks as standard practice — LAN latency (1–5ms) is irrelevant at warehouse robot speeds, so latency is not the argument for decentralization. The actual argument is **resilience**: movement-level coordination must keep working if the backend or network is degraded or unreachable.

| Decision | Where it happens | Why |
|---|---|---|
| Task assignment | Java Backend (centralized) | Global optimization needs global visibility; a bad assignment just gets reassigned, no robustness cost. |
| Warehouse map | Loaded once at sim start, replicated everywhere | Static; no reason to negotiate it. |
| Path planning (initial route) | Robot Agent (local, Python) | Each robot computes its own route. |
| Conflict detection & resolution | Robot Agents, peer-to-peer | Must survive the backend being slow, down, or unreachable — the actual decentralization argument. |
| Deadlock detection & recovery | Robot Agents, peer-to-peer | Same reasoning. |
| Monitoring, analytics, dashboard | Java Backend (centralized) | Naturally centralized. |

**Demo proof, not just a claim:** the live demo includes killing the Java backend mid-run and showing robots continue planning, communicating, and avoiding each other — see §18.

## 4. Technology Stack & Process Boundary (FROZEN)

| Component | Technology | Role |
|---|---|---|
| Simulation engine (`planner/`, `robot_agent/`, `collision_engine/`, `edge/`, `simulation/`) | Python 3.11+ | The actual robot world: planning, communication, coordination, sensing. |
| Backend (`backend/`) | Java 17 + Spring Boot | Task management, persistence, single facade for the dashboard, bridge to the Python engine. |
| Dashboard (`dashboard/`) | TypeScript + React | Live fleet monitoring; talks only to the Java backend. |

**The Python↔Java boundary, previously left open, is now frozen:**

```text
React Dashboard ──REST/WS──▶ Java Backend ──REST (control)──▶ Python Sim Engine (FastAPI)
                                    ▲                                     │
                                    └─────────REST (data push)────────────┘
```

- Python's `simulation/runner.py` exposes a small FastAPI control server (default port 8001): `POST /control/start {scenarioId, mode, seed, speed}`, `POST /control/stop`, `GET /control/status`.
- Java's backend is the REST *client* for those, and a REST *server* for `POST /api/telemetry/batch`, `POST /api/events`, `POST /api/metrics`, which Python pushes to once per tick (telemetry/events) or once at run end (metrics).
- The dashboard never talks to Python directly.

**Simulation model:** discrete ticks, 2D grid, at most one cell of movement per robot per tick. Two run speeds: `LIVE` (throttled ~2 ticks/sec, for the judge-facing demo) and `BATCH` (unthrottled, for the 10–20 repeated evaluation runs).

**Contracts are real code, not just documentation.** `shared/python/models.py` is one importable module (dataclasses) used by all five Python modules — true single source within Python. Java and TypeScript carry their own mirrored DTOs/interfaces (unavoidable across languages); `docs/00_SHARED_CONTRACTS.md` is the arbiter if a mirror ever disagrees with the Python source.

**Database:** SQLite for local dev, Postgres-compatible via JPA/Hibernate (a config change, not a code change).

## 5. High-Level Architecture

```text
                         ┌──────────────────────────┐
                         │     FLEET DASHBOARD       │
                         │   (React, mock-first)     │
                         └────────────┬──────────────┘
                                      │ REST / WebSocket
                         ┌────────────▼──────────────┐
                         │   BACKEND (Spring Boot)     │
                         │  Task mgmt · Ingestion       │
                         │  Sim control · Persistence   │
                         └────────────┬──────────────┘
                                      │ REST (control) / REST (data push)
                         ┌────────────▼──────────────┐
                         │  PYTHON SIM ENGINE (FastAPI)│
                         │  simulation/runner.py       │
                         └────────────┬──────────────┘
             ┌────────────────────────┼────────────────────────┐
             ▼                        ▼                        ▼
       ┌───────────┐            ┌───────────┐            ┌───────────┐
       │ROBOT AGENT│◄──────────►│ROBOT AGENT│◄──────────►│ROBOT AGENT│
       │(agent.py) │  P2P msg   │(agent.py) │  P2P msg   │(agent.py) │
       │  bus (InProcessBus)     │           │            │           │
       │ Planner · ConflictDet   │           │            │           │
       │ Deadlock · Reroute      │           │            │           │
       │ Edge/Sensor             │           │            │           │
       └───────────┘            └───────────┘            └───────────┘
```

## 6. Robot Agent

Owner: Member 3 (`robot_agent/agent.py`), built as a skeleton together in the Phase-0 kickoff, maintained afterward. Full signature and tick logic: `docs/03_COORDINATION.md` §8.4 and §9. Composition: `RobotState`, `Planner` (Member 1), `Transport`/communication (Member 2), `ConflictDetector`/`DeadlockDetector`/`ConflictResolver` (Member 3), `SensorSource` (Member 5).

## 7. Path Planning — Windowed Prioritized A\*

Owner: Member 1. This is a named, recognized MAPF technique (related to Cooperative A*/WHCA*) — say so to judges rather than presenting it as ad hoc. Each robot's path is computed independently, then replanned around peer-broadcast (cell, tick) claims when conflicts are detected. Full interface: `docs/01_PATH_PLANNING.md` §9. **The demo warehouse map's choke-point density is a deliberate design decision** — a sparse map makes conflicts rare and the whole improvement claim unconvincing.

## 8. Multi-Agent Coordination

Owner: Member 3. `ConflictDetector` compares broadcast paths for same-cell/same-time, crossing, and narrow-aisle head-on conflicts. `ConflictResolver` applies deterministic priority rules (task priority → in-critical-section → rerouting cost → robot ID tiebreak) to choose `CONTINUE|WAIT|YIELD|REROUTE|REASSIGN_TASK`. `DeadlockDetector` uses a simplified N-tick-stall-forces-yield heuristic (not full wait-for-graph cycle detection — that's optional/stretch). Full interfaces: `docs/03_COORDINATION.md` §9.

## 9. Communication

Owner: Member 2. Default transport: in-process publish/subscribe bus (`InProcessBus`), not real network sockets — deterministic and immune to venue Wi-Fi issues while still enforcing that agents only see each other through explicit messages. Fault injection (`MessageFaultConfig`: drop rate, delay) is a real feature that powers the deadlock and resilience demo scenarios. A real UDP/WebSocket transport is an isolated, optional stretch behind the same `Transport` interface. Full interface: `docs/02_ROBOT_COMMUNICATION.md` §9.

## 10. ECE / Edge

Owner: Member 5. Software-only by default: `SensorSource`/`SimulationSensorSource` plus a genuine, substantial deliverable — a **fault-injection framework** (`SensorFaultConfig`: noise, dropout, offline-after-tick) and heartbeat/health-check logic that drives the task-reassignment demo scenario. Not busywork. Optional hardware (`edge/hardware/`) is fully isolated and never required. "Edge-AI" is satisfied by decentralized local decision-making itself — no on-device neural net is required. Full interface: `docs/05_EDGE_ECE.md` §9.

## 11. Simulation, Scenarios, and the Independent Referee

Owner: Member 3 (`simulation/runner.py`, `simulation/scenarios/`, `simulation/referee.py`), map instance owner: Member 1 (`simulation/warehouse/demo_map.py`). Nine scenarios: normal movement, intersection conflict, narrow aisle, deadlock, blocked aisle, task reassignment, high fleet load, parallel aisles, and a **negative control** (no possible conflicts) to preempt "did you cherry-pick scenarios?" `simulation/referee.py` is a ground-truth collision checker **independent of `ConflictDetector`** — it must never call into or depend on collision_engine's own logic, so "zero collisions" is verified, not assumed by construction.

## 12. Task Allocation

Owner: Member 6 (Java backend), by design — task assignment is the centralized half of the hybrid architecture (§3). Simple greedy/nearest-idle-robot heuristic; advanced optimization is a Phase 5+ stretch. Robot going `OFFLINE` (from Member 5's fault injection, surfaced through `RobotState.status`) triggers automatic reassignment.

## 13. Fleet Dashboard

Owner: Member 4, mock-first, never blocked on the backend. Warehouse map, robot status, task panel, alerts (from `SimulationEvent`), and a performance panel whose visual centerpiece is the three-way comparison across `STOP_AND_WAIT` / `CENTRALIZED_RESERVATION` / `DECENTRALIZED_PROPOSED`. Must degrade gracefully (not crash) when the backend is deliberately killed mid-demo.

## 14. Simulation vs. Hardware

```text
             Robot Agent
                  ▲
          Common Telemetry (via SensorSource interface)
                  ▲
        ┌─────────┴─────────┐
        │                   │
 SimulationSensorSource  HardwareSensorSource (optional, isolated)
```

## 15. Shared Contracts

Canonical: `shared/python/models.py` (real, importable Python). Reference/mirror doc: `docs/00_SHARED_CONTRACTS.md`. Full field list, producer/consumer map, and cross-language mirror notes live there — not duplicated here to avoid a second copy drifting out of sync.

## 16. Repository Structure

See `docs/07_REPO_SETUP_AND_GIT.md` §A for the exact tree, including which files are real (`shared/python/models.py`, `dashboard/src/types/contracts.ts`) versus initial stubs.

## 17. Team Structure

| Member | Owns | Depends on (mockable) |
|---|---|---|
| 1 — Path Planning & Map | `planner/`, `simulation/warehouse/` | None to start |
| 2 — Robot Communication | `robot_agent/communication/` | None to start |
| 3 — Coordination | `collision_engine/`, `robot_agent/agent.py`, `simulation/runner.py`, `simulation/referee.py`, `simulation/scenarios/` | Members 1, 2, 5 (all mockable) |
| 4 — Frontend | `dashboard/` | Member 6 (mockable) |
| 5 — ECE/Edge | `edge/` | None to start |
| 6 — Backend + Integration | `backend/`, `scripts/`, `docker-compose.yml` | Member 3's Python engine (mockable via a fake POST script) |

Full implementation-ready specs, including exact function signatures, cross-role impact, failure behavior, and mock strategy per member: `docs/01_PATH_PLANNING.md` through `docs/06_BACKEND.md`.

## 18. SIH Demonstration Strategy

```text
Scenario starts (dense map, designed choke points)
      ↓
4+ robots receive tasks from backend
      ↓
robots calculate local routes (windowed A*), broadcast intent, resolve a conflict
      ↓
Java backend is killed mid-run — robots keep negotiating and moving (resilience proof)
      ↓
an aisle is blocked; affected robot reroutes
      ↓
a robot goes OFFLINE (fault injection); its task is reassigned
      ↓
backend restarted, dashboard reconnects and catches up
      ↓
three-way comparison: STOP_AND_WAIT vs CENTRALIZED_RESERVATION vs DECENTRALIZED_PROPOSED
```

## 19. Evaluation Methodology

Three modes compared on identical scenarios, same map/task batch/seed per run (paired comparison), 10–20 runs per scenario, all nine scenarios including the negative control. Collisions certified by the independent referee (§11), never by `ConflictDetector`'s own count. Headline metric for judges: total makespan on a fixed task batch, `DECENTRALIZED_PROPOSED` vs. `STOP_AND_WAIT`; everything else (vs. `CENTRALIZED_RESERVATION`, idle time, message count) is supporting evidence. Target: 0 referee-verified collisions, ≥20% makespan reduction vs. stop-and-wait.

## 20. Scope Control — MVP vs. Optional

| MVP (blocks demo) | Optional (never blocks) |
|---|---|
| In-process comms bus, windowed A*, simplified deadlock recovery | Real UDP/WebSocket transport |
| Dynamic rerouting, centralized task assignment | Full wait-for-graph deadlock cycle detection |
| Stop-and-wait AND centralized-reservation baselines | Advanced task-allocation optimization |
| Live dashboard (mock-first, then real), independent referee | Physical Raspberry Pi/ESP32 sensor demo, authentication |

## 21. Definition of Done

```text
✓ 4+ robots, dense choke-point warehouse map
✓ Decentralized P2P conflict/deadlock handling that survives the backend being killed
✓ Dynamic rerouting, task allocation & reassignment
✓ Live dashboard with alerts and the three-way performance comparison
✓ Referee-verified zero collisions, ≥20% makespan improvement, across seeded repeated runs
✓ Optional hardware segment, fully isolated
```

## 22. What Changed From v1 (for the team's awareness)

- Python↔Java boundary is now frozen (FastAPI control server + REST push), not left as "TBD."
- Contracts are now real, importable Python code (`shared/python/models.py`), not just markdown descriptions copied into six files.
- `simulation/runner.py`, `simulation/referee.py`, and all nine scenarios now have a named owner (Member 3) and Member 1 owns the concrete demo map instance — previously unowned.
- Exact function/class signatures are specified for every module (see the `docs/0X_*.md` files §9 in each).
- The independent collision referee is now explicit and structurally separated from `ConflictDetector`.
- Six fully detailed, implementation-ready role documents replace the earlier thin overviews.
