package com.sih26123.backend.model;

/**
 * SimulationStatusDto — mirrors the JSON actually returned by Python's
 * GET /control/status (simulation/runner.py):
 *   { "running": bool, "currentTick": int, "scenarioId": str|null, "mode": str }
 * Owner: Member 6
 *
 * NOT a shared/python/models.py contract — there is no SimulationStatus
 * dataclass in shared/python/models.py or docs/00_SHARED_CONTRACTS.md. This
 * type exists purely to mirror the actual (undocumented-as-a-contract, but
 * inspected) Python control-server response shape. See final report for the
 * compatibility note.
 */
public class SimulationStatusDto {
    public boolean running;
    public int currentTick;
    public String scenarioId; // nullable
    public String mode;

    public SimulationStatusDto() {
    }

    public SimulationStatusDto(boolean running, int currentTick, String scenarioId, String mode) {
        this.running = running;
        this.currentTick = currentTick;
        this.scenarioId = scenarioId;
        this.mode = mode;
    }
}
