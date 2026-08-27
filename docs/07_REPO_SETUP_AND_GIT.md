# 07 — Repository Setup & Git Instructions (For Antigravity)

**Paste this whole file into Antigravity. It is a scaffolding task, not an implementation task — see §H for the hard boundary.**

---

## A. Repository Tree

Create exactly this structure. Where a file is listed, create it with the described minimal placeholder content — do not implement real logic (see §H).

```text
sih-26123/
├── SIH_26123_Project_Overview.md      # already exists — do not overwrite
├── README.md                          # short: project name, one-paragraph description, link to docs/
├── .gitignore                         # Python + Java + Node + IDE + OS entries (see §D)
├── docker-compose.yml                 # optional — see §D.4
├── scripts/
│   └── run_all.sh                     # starts Python sim engine, Java backend, prints dashboard start instructions
├── docs/
│   ├── 00_SHARED_CONTRACTS.md         # already provided — copy in as-is
│   ├── 01_PATH_PLANNING.md            # already provided — copy in as-is
│   ├── 02_ROBOT_COMMUNICATION.md      # already provided — copy in as-is
│   ├── 03_COORDINATION.md             # already provided — copy in as-is
│   ├── 04_FRONTEND.md                 # already provided — copy in as-is
│   ├── 05_EDGE_ECE.md                 # already provided — copy in as-is
│   ├── 06_BACKEND.md                  # already provided — copy in as-is
│   └── 07_REPO_SETUP_AND_GIT.md       # this file — copy in as-is
├── shared/
│   └── python/
│       ├── __init__.py
│       └── models.py                  # already provided — copy in as-is, this is the canonical contract module
├── planner/
│   ├── __init__.py
│   ├── astar.py                       # empty module with the function signatures from docs/01_PATH_PLANNING.md §9, bodies = `raise NotImplementedError`
│   ├── warehouse_map.py               # same treatment
│   ├── centralized_baseline.py        # same treatment
│   └── tests/__init__.py
├── robot_agent/
│   ├── __init__.py
│   ├── agent.py                       # RobotAgent class skeleton per docs/03_COORDINATION.md §8.4 — leave as a real skeleton, not NotImplementedError, since it's the Phase-0 co-written shell
│   ├── communication/
│   │   ├── __init__.py
│   │   ├── transport.py               # Transport ABC + stub classes per docs/02_ROBOT_COMMUNICATION.md §9
│   │   └── messages.py                # stub per docs/02_ROBOT_COMMUNICATION.md §9
│   └── tests/__init__.py
├── collision_engine/
│   ├── __init__.py
│   ├── detection.py                   # stub per docs/03_COORDINATION.md §9
│   ├── deadlock.py                    # stub per docs/03_COORDINATION.md §9
│   ├── resolution.py                  # stub per docs/03_COORDINATION.md §9
│   └── tests/__init__.py
├── edge/
│   ├── __init__.py
│   ├── sensor_source.py               # stub per docs/05_EDGE_ECE.md §9
│   ├── fault_injection.py             # stub per docs/05_EDGE_ECE.md §9
│   ├── heartbeat.py                   # stub per docs/05_EDGE_ECE.md §9
│   ├── hardware/__init__.py           # empty, isolated
│   └── tests/__init__.py
├── simulation/
│   ├── __init__.py
│   ├── warehouse/
│   │   └── demo_map.py                # empty, `raise NotImplementedError` placeholder
│   ├── runner.py                      # FastAPI app skeleton with the three routes from docs/03_COORDINATION.md §9, handlers raise NotImplementedError
│   ├── referee.py                     # stub per docs/03_COORDINATION.md §9
│   ├── scenarios/
│   │   ├── __init__.py
│   │   ├── a_normal.py
│   │   ├── b_intersection.py
│   │   ├── c_narrow_aisle.py
│   │   ├── d_deadlock.py
│   │   ├── e_blocked_aisle.py
│   │   ├── f_task_reassignment.py
│   │   ├── g_high_load.py
│   │   └── h_negative_control.py      # all eight: empty file with a one-line docstring naming the scenario
│   └── tests/__init__.py
├── backend/                           # Spring Boot skeleton — see §D.2
│   ├── pom.xml
│   └── src/
│       ├── main/
│       │   ├── java/com/sih26123/backend/
│       │   │   ├── BackendApplication.java
│       │   │   ├── controller/        # empty controller classes, one per docs/06_BACKEND.md §8.1/8.2 endpoint group, methods return 501/NotImplemented placeholders
│       │   │   ├── model/             # empty DTO classes, one per contract in docs/00_SHARED_CONTRACTS.md
│       │   │   ├── service/           # empty service classes named per docs/06_BACKEND.md §4
│       │   │   ├── websocket/
│       │   │   └── repository/
│       │   └── resources/application.properties   # SQLite datasource config
│       └── test/java/...
└── dashboard/                         # Vite + React + TS skeleton — see §D.3
    ├── package.json
    ├── src/
    │   ├── api/
    │   │   ├── client.ts              # function signatures from docs/04_FRONTEND.md §9, bodies throw "not implemented"
    │   │   └── mock.ts                # empty fixture exports
    │   ├── components/
    │   │   ├── WarehouseMap.tsx
    │   │   ├── RobotStatusPanel.tsx
    │   │   ├── TaskPanel.tsx
    │   │   ├── AlertsFeed.tsx
    │   │   └── PerformancePanel.tsx   # each a minimal placeholder component that renders its name
    │   ├── types/
    │   │   └── contracts.ts           # TS interfaces from docs/04_FRONTEND.md §9, copied in fully (these ARE real, not stubs — they're just type declarations)
    │   └── App.tsx
    └── public/
```

## B. File Ownership

| Path | Owner | Others allowed to modify? |
|---|---|---|
| `planner/`, `simulation/warehouse/` | Member 1 | No — flag issues to Member 1 instead |
| `robot_agent/communication/` | Member 2 | No |
| `collision_engine/`, `robot_agent/agent.py`, `simulation/runner.py`, `simulation/referee.py`, `simulation/scenarios/` | Member 3 | No |
| `dashboard/` | Member 4 | No |
| `edge/` | Member 5 | No |
| `backend/`, `scripts/`, `docker-compose.yml` | Member 6 | No |
| `shared/python/models.py` | Collectively owned, frozen at Phase 0 | Yes, but requires review from at least 2 other members and a team-channel heads-up before merging |
| `docs/*.md` | Collectively owned | Yes, same rule as above for the contracts doc; role files should mainly be edited by their subject's owner |

## C. Shared / Conflict-Sensitive Files

Require a quick team ping before editing, even though nobody "owns" them exclusively:

```text
shared/python/models.py
docs/00_SHARED_CONTRACTS.md
robot_agent/agent.py            (Member 3 owns it, but many depend on its shape)
simulation/runner.py            (same reason)
README.md
.gitignore
docker-compose.yml
scripts/run_all.sh
backend/pom.xml
dashboard/package.json
```

## D. Initial Interfaces / Contracts / Configuration

**D.1 — `shared/python/models.py`**: copy the provided file exactly (dataclasses for `Position`, `RobotState`, `RobotPath`, `Task`, `TaskAssignment`, `Conflict`, `WarehouseMap`, `Telemetry`, `SimulationEvent`, `PerformanceMetric`). This is real code, not a stub — it's meant to be imported immediately.

**D.2 — Backend skeleton**: Spring Boot 3.x, Java 17, Maven. `application.properties` should point at a local SQLite file (`jdbc:sqlite:./sih26123.db`) via an appropriate Hibernate dialect dependency. Controllers should exist with correct method signatures and `@RequestMapping` paths matching `docs/06_BACKEND.md` §8.1/8.2 exactly, but return a placeholder (`ResponseEntity.status(501)`) rather than real logic.

**D.3 — Dashboard skeleton**: Vite + React + TypeScript. `contracts.ts` should be fully populated (real type declarations, not stubs — see `docs/04_FRONTEND.md` §9). Components should be minimal placeholders that render their own name so `npm run dev` produces a visibly working (if empty) app immediately.

**D.4 — `docker-compose.yml`** (optional): three services — `backend` (Java), `simulation` (Python/FastAPI), and a note that the dashboard runs via `npm run dev` separately in local dev (only bundle it into compose if the team wants a single demo-day command later; don't block on this).

**D.5 — `.gitignore`**: standard Python (`__pycache__/`, `.venv/`, `*.pyc`), Java (`target/`, `*.class`), Node (`node_modules/`, `dist/`), plus `.env`, `*.db`, `.idea/`, `.vscode/`, `.DS_Store`.

## E. Git Setup

```bash
git init
git checkout -b main
git commit --allow-empty -m "chore: initialize repository"
git checkout -b develop
git push -u origin main
git push -u origin develop
```

Then create the initial feature branches (empty, off `develop`, not yet pushed with content — each member pushes their own first commit):

```bash
git checkout develop
git checkout -b feature/astar-basic
git checkout develop
git checkout -b feature/robot-communication
git checkout develop
git checkout -b feature/coordination
git checkout develop
git checkout -b feature/dashboard-map
git checkout develop
git checkout -b feature/edge-interface
git checkout develop
git checkout -b feature/backend-api
git checkout develop
```

Do not create feature *folders* — only branches. See `SIH_26123_Project_Overview.md` for the difference.

## F. Branch-to-Folder Mapping

```text
feature/astar-basic, feature/dynamic-rerouting,
  feature/centralized-baseline           → planner/, simulation/warehouse/

feature/robot-communication,
  feature/fault-injection (comms)        → robot_agent/communication/

feature/coordination, feature/deadlock-detection,
  feature/agent-tick-loop, feature/scenarios → collision_engine/, robot_agent/agent.py,
                                               simulation/runner.py, simulation/referee.py,
                                               simulation/scenarios/

feature/dashboard-map, feature/dashboard-alerts,
  feature/dashboard-metrics               → dashboard/

feature/edge-interface, feature/fault-injection (sensor),
  feature/heartbeat                       → edge/

feature/backend-api, feature/backend-websocket,
  feature/simulation-control              → backend/
```

## G. Protected / Shared Files Requiring Team Approval

Same list as §C. Any PR touching these should be flagged in the team channel before merge, regardless of whose branch it's on.

## H. Initial Setup Only — Hard Boundary

> Antigravity should ONLY: create the repository structure in §A, create the configuration described in §D, create the initial interface/contract placeholders described in §A and §D.1–D.3, create `.gitignore`, create a minimal `README.md`, and get the project to a state where each piece can build/start (even if empty).
>
> Antigravity must NOT: implement the A* algorithm, the conflict detection/resolution logic, the communication bus internals, the sensor fault injection logic, the dashboard's real rendering logic, or the backend's real service logic. Every file listed as a "stub" above should raise `NotImplementedError` (Python), return a `501`/placeholder response (Java), or throw "not implemented" (TypeScript) — real implementation is each module owner's job, done from their own role document.
>
> Do not invent architecture beyond what's specified in `docs/00_SHARED_CONTRACTS.md` and the six role documents. Do not add dependencies, folders, or files not listed above without flagging it first.

## I. Verification Checklist

After setup, confirm:

- [ ] `git log` shows `main` and `develop` branches, plus the six initial feature branches off `develop`
- [ ] `cd backend && mvn spring-boot:run` starts without error (even with placeholder endpoints)
- [ ] `cd dashboard && npm install && npm run dev` starts and shows the placeholder components
- [ ] `python -c "from shared.python.models import RobotState"` succeeds from the repo root
- [ ] `python -m simulation.runner` starts the FastAPI control server without error (even with placeholder handlers)
- [ ] Every folder in §A exists with the described placeholder files
- [ ] `docs/*.md` all present and match the versions provided
- [ ] `.gitignore` is present and no `.env`, `*.db`, `node_modules/`, `target/`, `__pycache__/`, or IDE files are tracked
- [ ] No secrets, API keys, or credentials committed anywhere
- [ ] `scripts/run_all.sh` exists and at minimum prints clear instructions for starting all three processes, even if it doesn't fully automate it yet
