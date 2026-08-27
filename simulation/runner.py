"""
simulation/runner.py — FastAPI control server and tick driver.
Owner: Member 3

Exposes the Python simulation engine's control API to the Java backend.
Default port: 8001.

API:
    POST /control/start   {scenarioId: str, mode: str, seed: int, speed: "LIVE"|"BATCH"}
    POST /control/stop
    GET  /control/status  -> {running: bool, currentTick: int, scenarioId: str, mode: str}

Python<->Java boundary (FROZEN):
    - Java calls this FastAPI server to start/stop/query the simulation.
    - This runner POSTs to Java's /api/telemetry/batch, /api/events, /api/metrics.
    - The dashboard never talks to this server directly.

Run with: python -m simulation.runner

Implementation: Member 3's responsibility.
"""

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="SIH 26123 — Simulation Control API", version="0.1.0")

# ── In-memory run state ──────────────────────────────────────────────────────
_running: bool = False
_current_tick: int = 0
_scenario_id: str | None = None
_mode: str | None = None


@app.post("/control/start")
async def control_start(body: dict):
    """Start a simulation run.

    Body: {scenarioId: str, mode: str, seed: int, speed: "LIVE"|"BATCH"}

    Loads the named scenario, constructs RobotAgents (DECENTRALIZED_PROPOSED mode),
    or uses the appropriate alternative driver for other modes.

    Implementation: Member 3's responsibility.
    """
    raise NotImplementedError


@app.post("/control/stop")
async def control_stop():
    """Stop the currently running simulation.

    Implementation: Member 3's responsibility.
    """
    raise NotImplementedError


@app.get("/control/status")
async def control_status():
    """Return current simulation status.

    Response: {running: bool, currentTick: int, scenarioId: str|null, mode: str|null}

    Implementation: Member 3's responsibility.
    """
    raise NotImplementedError


if __name__ == "__main__":
    uvicorn.run("simulation.runner:app", host="0.0.0.0", port=8001, reload=False)
