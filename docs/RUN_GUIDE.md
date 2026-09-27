# Run Guide — SIH 26123 Fleet Coordination System (Windows)

This is a beginner-friendly, exact-commands guide to running the full stack
(Python simulation engine → Java backend → React dashboard) on Windows.
Every command below was verified against this repository during the
2026-09-08 full-stack integration session (all three processes actually
started and talked to each other over real HTTP/WebSocket — not assumed).

Written for: **Windows + PowerShell**. Command Prompt equivalents are noted
where they differ.

---

## 1. Prerequisites

| Tool | Version required | Check with |
|---|---|---|
| Java | **17** (JDK, not just JRE) | `java -version` |
| Python | 3.11+ (verified working on 3.13) | `python --version` |
| Node.js | 18+ (verified working on v24) | `node --version` |
| npm | comes with Node | `npm --version` |

**Important Java note, verified on this machine**: your PATH `java` may
point at an *older* JDK (e.g. 1.8) even if a JDK 17 is installed elsewhere.
The backend's Maven wrapper (`mvnw.cmd`) needs `JAVA_HOME` to explicitly
point at a JDK 17+ install — see Terminal 2 below. Find your JDK 17 install
path once with:

```powershell
Get-ChildItem "C:\Program Files\Eclipse Adoptium" -ErrorAction SilentlyContinue
Get-ChildItem "C:\Program Files\Java" -ErrorAction SilentlyContinue
```

**Python dependencies**: the repository has no `requirements.txt` — the
only third-party packages the simulation engine needs are `fastapi` and
`uvicorn` (everything else it imports is Python's standard library). If
`python -m simulation.runner` fails with `ModuleNotFoundError`, install
them:

```powershell
pip install fastapi uvicorn
```

**Frontend dependencies**: standard npm install, done once (Terminal 3,
step 1 below).

---

## 2. Folder layout — which terminal opens where

Open **three separate PowerShell terminals**. All three read from the same
repository; only the working directory differs:

| Terminal | Working directory |
|---|---|
| 1 — Python simulation | repository root (e.g. `G:\SIH2026`) |
| 2 — Java backend | `G:\SIH2026\backend` |
| 3 — React frontend | `G:\SIH2026\dashboard` |

---

## 3. Terminal 1 — Python Simulation Engine

```powershell
cd G:\SIH2026
python -m simulation.runner
```

**Expected output** (a few seconds after launch):

```
INFO:     Started server process [....]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
```

This is the FastAPI control server on **port 8001**. It stays idle
(`{"running": false, ...}` on `GET /control/status`) until the Java backend
tells it to start a scenario.

If `python` is not recognized, try `py -3 -m simulation.runner` instead.

---

## 4. Terminal 2 — Java Backend

```powershell
cd G:\SIH2026\backend
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-17.0.12.7-hotspot"
.\mvnw.cmd spring-boot:run
```

Replace the `JAVA_HOME` path with wherever your own JDK 17 is installed
(see the prerequisites section above if unsure).

**Expected output**: a Spring Boot banner, then (first run downloads
Maven + dependencies, which can take a few minutes — subsequent runs are
fast, ~15-30s):

```
Tomcat initialized with port(s): 8080 (http)
...
Started BackendApplication in X.XXX seconds
```

This is on **port 8080** — the only address the frontend ever talks to. A
`sih26123.db` SQLite file is created in `backend/` on first run and persists
run history/metrics/events across restarts (see Troubleshooting if this
becomes a problem).

Verify it's up and can already see the Python engine, from any terminal:

```powershell
curl http://localhost:8080/api/simulation/status
```

Expected: `{"running":false,"currentTick":0,"scenarioId":null,"mode":"DECENTRALIZED_PROPOSED"}`

---

## 5. Terminal 3 — React Frontend

```powershell
cd G:\SIH2026\dashboard
npm install
npm run dev
```

(`npm install` is only needed the first time, or after `package.json`
changes.)

**Expected output**:

```
  VITE v5.4.21  ready in ### ms

  ➜  Local:   http://localhost:5173/
```

**Open `http://localhost:5173/` in your browser** — verified that Vite
binds to IPv6 localhost (`[::1]`) by default on this setup, so
`http://127.0.0.1:5173` may not connect while `http://localhost:5173`
does. Always use `localhost`, not `127.0.0.1`, for the frontend URL.

---

## 6. Startup order

**Python (Terminal 1) → Java backend (Terminal 2) → React frontend
(Terminal 3).**

In practice the Java backend will start fine even if Python isn't up yet —
it's designed to stay alive and report a clear error rather than crash (see
`docs/06_BACKEND.md` §13) — but starting Python first avoids seeing
avoidable `SIMULATION_ENGINE_ERROR` messages during your first
`POST /api/simulation/control` call. The frontend should always be started
last, since it immediately starts polling the backend.

---

## 7. Judge-Demo Flow (recommended sequence)

1. Start Python simulation engine (Terminal 1) — wait for "Uvicorn running".
2. Start Java backend (Terminal 2) — wait for "Started BackendApplication".
3. Start React frontend (Terminal 3) — wait for "Local: http://localhost:5173/".
4. Open **http://localhost:5173** in a browser. The header should show both
   status badges green/reachable within ~1 second (status polls every 1s).
5. In the left panel: leave **Mode = DECENTRALIZED_PROPOSED** (the proposed
   system), set **Speed = LIVE** (paces at ~2 ticks/sec so movement is
   visible — BATCH runs instantly with no visible animation).
6. Pick a scenario from the list of 9 — recommended for a live crossing/
   negotiation demo: **b_intersection** or **i_parallel_aisles**; for
   resilience: **e_blocked_aisle** or **f_task_reassignment**; for scale:
   **g_high_load** (6 robots).
7. Click **▶ START**.
8. Watch the **live warehouse map** (center panel) — real robot markers
   moving tick by tick, sourced from `/ws/live`, not animated locally.
9. Switch the right-side tabs to **COMMS** to show real per-robot
   CONTINUE/WAIT/YIELD negotiation decisions, or **EVENTS** for the full
   scripted-event timeline (AISLE_BLOCKED / TASK_REASSIGNED / NEGOTIATION),
   or **STORY** (labeled **DEADLOCK** on `d_deadlock`) for a narrated
   approach → conflict → yield → resume sequence.
10. Click the **BENCHMARK & PROOF** tab in the header's view switcher.
11. Point to the headline card: **"21.74% faster in i_parallel_aisles"**
    (with the exact tick math shown underneath) — and to the 5 separated
    categories below it, and the **0 / 270 collision-safety** stat. Make
    clear to judges that this is the audited offline benchmark, not the
    just-run live demo.

---

## 8. Troubleshooting

**Python runner not reachable** (Java shows `SIMULATION_ENGINE_ERROR` /
`GET /api/simulation/status` returns an error body): Terminal 1 has
stopped or never started. Check that terminal for a traceback, restart
`python -m simulation.runner`, then retry the action from the dashboard —
the Java backend itself never crashes when this happens, by design.

**Java backend not starting**: almost always `JAVA_HOME` pointing at the
wrong JDK. Run `java -version` after setting `$env:JAVA_HOME` (step 4) and
confirm it reports `17.x`. If Maven itself can't resolve dependencies,
check your internet connection (first run only — needs to download plugins).

**Frontend cannot connect / status badges stay grey**: confirm the backend
is actually reachable — `curl http://localhost:8080/api/simulation/status`
from any terminal. `dashboard/src/api/client.ts` has the backend URL
hardcoded to `http://localhost:8080` — no `.env` file to configure.

**WebSocket disconnected** (banner reads "LIVE FEED DISCONNECTED —
RECONNECTING…"): the frontend auto-reconnects with backoff (1s → 8s) —
this is expected for a few seconds if the Java backend was just restarted.
If it never recovers, confirm Terminal 2 is still running and listening on
8080.

**SQLite busy / "database is locked"**: only run **one** Java backend
instance against `backend\sih26123.db` at a time — stop any previously
running instance first. To fully reset all stored run history (destructive,
only do this if you want a clean slate):

```powershell
# with the backend stopped:
Remove-Item G:\SIH2026\backend\sih26123.db -ErrorAction SilentlyContinue
```

A fresh database file is recreated automatically on the next backend start.

**Stale frontend state** (old robots/events still showing after a restart):
hard-refresh the browser tab (Ctrl+F5). The dashboard keeps all live-run
data in memory only — nothing is cached in `localStorage`.

**Port already in use** (`8001`, `8080`, or `5173`):

```powershell
# Find what's using a port (example: 8080):
Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue

# Stop it by PID:
Stop-Process -Id <PID> -Force
```

or with Command Prompt instead of PowerShell:

```cmd
netstat -ano | findstr :8080
taskkill /PID <PID> /F
```

---

## 9. Stop Procedure

Press **Ctrl+C** in each of the 3 terminals. Order doesn't matter — each
process is resilient to the others already being down (this is a tested,
documented property of the system, not an assumption):

- Stopping Python first: the Java backend stays up and returns a clear
  error on the next simulation-control call, instead of crashing.
- Stopping Java first: the frontend shows "LIVE FEED DISCONNECTED" and
  retries automatically; the Python engine keeps running standalone.
- Stopping the frontend: no effect on the other two.

If a terminal's Ctrl+C doesn't fully release its port (rare), use the
"port already in use" commands above to find and stop the leftover process.
