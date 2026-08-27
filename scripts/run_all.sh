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
#   - Python 3.11+ with FastAPI and uvicorn installed
#     (pip install fastapi uvicorn)
#   - Java 17 + Maven installed
#   - Node.js 18+ for the dashboard (run separately)
#
# NOTE: This script is a placeholder. It prints startup instructions and attempts
# to start the services. Full automation is Member 6's implementation responsibility.

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "======================================================="
echo " SIH 2026 — Project 26123  |  Fleet Coordination System"
echo "======================================================="
echo ""
echo "Starting Python Simulation Engine (FastAPI, port 8001)..."
cd "$REPO_ROOT"
python -m simulation.runner &
SIM_PID=$!
echo "  [SIM] PID=$SIM_PID  →  http://localhost:8001"
echo ""

echo "Starting Java Backend (Spring Boot, port 8080)..."
cd "$REPO_ROOT/backend"
mvn -q spring-boot:run &
BACKEND_PID=$!
echo "  [BACKEND] PID=$BACKEND_PID  →  http://localhost:8080"
echo ""

echo "-------------------------------------------------------"
echo " Dashboard: open a NEW terminal and run:"
echo "   cd dashboard && npm install && npm run dev"
echo " Then open: http://localhost:5173"
echo "-------------------------------------------------------"
echo ""
echo "Press Ctrl+C to stop all services."
echo ""

wait $SIM_PID $BACKEND_PID
