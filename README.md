# SIH 2026 — Project 26123
## Edge-AI Based Distributed Fleet Coordination for Autonomous Mobile Robots (AMRs) in Smart Warehouses

A software-first simulation and coordination framework for a fleet of Autonomous Mobile Robots operating inside a smart warehouse. The system demonstrates decentralized, peer-to-peer conflict avoidance and deadlock recovery that continues to work even when the central backend is offline.

**Sponsor:** Bharat Electronics Limited | **Category:** Software | **Theme:** Smart Automation

---

## Quick Start

See [`scripts/run_all.sh`](scripts/run_all.sh) for full startup instructions.

## Documentation

All architecture and role documents live in [`docs/`](docs/):

| Document | Contents |
|---|---|
| [`docs/00_SHARED_CONTRACTS.md`](docs/00_SHARED_CONTRACTS.md) | Canonical cross-module data contracts |
| [`docs/01_PATH_PLANNING.md`](docs/01_PATH_PLANNING.md) | Member 1 — Path planning & warehouse map |
| [`docs/02_ROBOT_COMMUNICATION.md`](docs/02_ROBOT_COMMUNICATION.md) | Member 2 — Robot communication bus |
| [`docs/03_COORDINATION.md`](docs/03_COORDINATION.md) | Member 3 — Coordination, simulation runner, scenarios |
| [`docs/04_FRONTEND.md`](docs/04_FRONTEND.md) | Member 4 — Fleet dashboard |
| [`docs/05_EDGE_ECE.md`](docs/05_EDGE_ECE.md) | Member 5 — Edge/sensor/fault injection |
| [`docs/06_BACKEND.md`](docs/06_BACKEND.md) | Member 6 — Java backend & integration |
| [`docs/07_REPO_SETUP_AND_GIT.md`](docs/07_REPO_SETUP_AND_GIT.md) | Repository structure & Git setup |
| [`SIH_26123_Project_Overview.md`](SIH_26123_Project_Overview.md) | Overall project architecture (highest-level source of truth) |

## Repository Structure

```
planner/              → Member 1 (Path planning & map)
robot_agent/          → Member 3 (agent.py) + Member 2 (communication/)
collision_engine/     → Member 3 (Conflict detection/resolution)
simulation/           → Member 3 (Runner, referee, scenarios)
edge/                 → Member 5 (Sensors, fault injection)
backend/              → Member 6 (Java/Spring Boot)
dashboard/            → Member 4 (React/TypeScript)
shared/python/        → Shared (canonical Python contracts)
```

## Technology Stack

- **Python 3.11+** — Simulation engine (planner, robot_agent, collision_engine, edge, simulation)
- **Java 17 + Spring Boot 3.x** — Backend (task management, persistence, REST/WebSocket facade)
- **TypeScript + React + Vite** — Fleet dashboard
