#!/usr/bin/env bash
# scripts/run_all.sh
# Owner: Member 6
# Starts the Python simulation engine and Java backend.
# The React dashboard runs separately via `npm run dev` from the dashboard/ directory.
#
# Usage:
#   bash scripts/run_all.sh
#
# Requirements:
#   - Python 3.11+ with FastAPI and uvicorn installed (pip install fastapi uvicorn)
#   - Java 17 + Maven (or use the bundled ./backend/mvnw wrapper — no local
#     Maven install required, but JAVA_HOME must point at a JDK 17+)
#   - Node.js 18+ for the dashboard (run separately)
#
# WINDOWS NOTE: this is a bash/POSIX script. It runs as-is under Git Bash or
# WSL. Native PowerShell does NOT have bash — use scripts/run_all.ps1 instead
# on a plain Windows terminal (no Git Bash/WSL). Both scripts do the same
# thing; pick whichever matches your shell rather than assuming this one
# "just works" everywhere.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SIM_PID=""
BACKEND_PID=""

cleanup() {
    echo ""
    echo "Shutting down..."
    [[ -n "$SIM_PID" ]] && kill "$SIM_PID" 2>/dev/null || true
    [[ -n "$BACKEND_PID" ]] && kill "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "======================================================="
echo " SIH 2026 — Project 26123  |  Fleet Coordination System"
echo "======================================================="
echo ""

if ! command -v python >/dev/null 2>&1 && ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python (or python3) not found on PATH. Install Python 3.11+." >&2
    exit 1
fi
PYTHON_BIN="$(command -v python || command -v python3)"

if [[ -z "${JAVA_HOME:-}" ]]; then
    echo "WARNING: JAVA_HOME is not set. ./backend/mvnw needs a JDK 17+ to run the backend." >&2
fi

echo "Starting Python Simulation Engine (FastAPI, port 8001)..."
cd "$REPO_ROOT"
"$PYTHON_BIN" -m simulation.runner &
SIM_PID=$!
echo "  [SIM] PID=$SIM_PID  ->  http://localhost:8001"
echo ""

echo "Starting Java Backend (Spring Boot, port 8080)..."
cd "$REPO_ROOT/backend"
if [[ -x "./mvnw" ]]; then
    ./mvnw -q spring-boot:run &
else
    mvn -q spring-boot:run &
fi
BACKEND_PID=$!
echo "  [BACKEND] PID=$BACKEND_PID  ->  http://localhost:8080"
echo ""

echo "-------------------------------------------------------"
echo " Dashboard: open a NEW terminal and run:"
echo "   cd dashboard && npm install && npm run dev"
echo " Then open: http://localhost:5173"
echo "-------------------------------------------------------"
echo ""
echo "Press Ctrl+C to stop all services."
echo ""

wait "$SIM_PID" "$BACKEND_PID"
