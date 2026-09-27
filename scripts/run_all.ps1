# scripts/run_all.ps1
# Owner: Member 6
# Windows PowerShell equivalent of scripts/run_all.sh — for a plain Windows
# terminal that doesn't have bash (Git Bash / WSL users can just run
# run_all.sh directly instead). Starts the Python simulation engine and the
# Java backend as background jobs; the dashboard is still run separately.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\run_all.ps1
#
# Requirements: same as run_all.sh — Python 3.11+ (fastapi, uvicorn), a JDK 17+
# on JAVA_HOME (or the plain `java`/`mvn` on PATH), Node.js 18+ for the dashboard.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "======================================================="
Write-Host " SIH 2026 -- Project 26123  |  Fleet Coordination System"
Write-Host "======================================================="
Write-Host ""

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Error "python not found on PATH. Install Python 3.11+."
    exit 1
}

Write-Host "Starting Python Simulation Engine (FastAPI, port 8001)..."
$simJob = Start-Job -ScriptBlock {
    param($root)
    Set-Location $root
    python -m simulation.runner
} -ArgumentList $repoRoot
Write-Host "  [SIM] Job Id=$($simJob.Id)  ->  http://localhost:8001"
Write-Host ""

Write-Host "Starting Java Backend (Spring Boot, port 8080)..."
$backendDir = Join-Path $repoRoot "backend"
$mvnw = Join-Path $backendDir "mvnw.cmd"
$backendJob = Start-Job -ScriptBlock {
    param($dir, $wrapper)
    Set-Location $dir
    if (Test-Path $wrapper) {
        & $wrapper -q spring-boot:run
    } else {
        mvn -q spring-boot:run
    }
} -ArgumentList $backendDir, $mvnw
Write-Host "  [BACKEND] Job Id=$($backendJob.Id)  ->  http://localhost:8080"
Write-Host ""

Write-Host "-------------------------------------------------------"
Write-Host " Dashboard: open a NEW terminal and run:"
Write-Host "   cd dashboard; npm install; npm run dev"
Write-Host " Then open: http://localhost:5173"
Write-Host "-------------------------------------------------------"
Write-Host ""
Write-Host "Press Ctrl+C to stop. Cleaning up background jobs on exit..."
Write-Host ""

try {
    Receive-Job -Job $simJob, $backendJob -Wait
} finally {
    Stop-Job -Job $simJob, $backendJob -ErrorAction SilentlyContinue | Out-Null
    Remove-Job -Job $simJob, $backendJob -Force -ErrorAction SilentlyContinue | Out-Null
}
