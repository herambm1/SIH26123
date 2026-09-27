package com.sih26123.backend.model;

/**
 * SimulationControlRequestDto — body of POST /api/simulation/control.
 * Owner: Member 6
 *
 * Not a shared/python/models.py contract (simulation control is a Java<->Python
 * concern, not a cross-team data contract) — field names per docs/06_BACKEND.md §8.1:
 *   { "action": "start"|"stop", "scenarioId", "mode", "seed", "speed" }
 */
public class SimulationControlRequestDto {
    public String action;      // "start" | "stop"
    public String scenarioId;
    public String mode;
    public Long seed;
    public String speed;
}
