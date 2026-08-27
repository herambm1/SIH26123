package com.sih26123.backend.model;

import java.util.Map;

/**
 * SimulationEventDto — mirrors shared/python/models.py SimulationEvent.
 * Owner: Member 6
 * Source of truth: docs/00_SHARED_CONTRACTS.md / shared/python/models.py
 *
 * type ∈ {AISLE_BLOCKED, ROBOT_UNAVAILABLE, TASK_CREATED, CONFLICT_DETECTED,
 *          DEADLOCK_DETECTED, REROUTE, TASK_REASSIGNED}
 */
public class SimulationEventDto {
    public String eventId;
    public String type;
    public int tick;
    public Map<String, Object> payload;
}
