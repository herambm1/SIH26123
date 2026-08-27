package com.sih26123.backend.model;

/**
 * PerformanceMetricDto — mirrors shared/python/models.py PerformanceMetric.
 * Owner: Member 6
 * Source of truth: docs/00_SHARED_CONTRACTS.md / shared/python/models.py
 *
 * mode ∈ {STOP_AND_WAIT, CENTRALIZED_RESERVATION, DECENTRALIZED_PROPOSED}
 */
public class PerformanceMetricDto {
    public String runId;
    public String scenarioId;
    public String mode;               // STOP_AND_WAIT|CENTRALIZED_RESERVATION|DECENTRALIZED_PROPOSED
    public int totalCompletionTicks;
    public double avgCompletionTicks;
    public int collisionCount;        // from the independent referee — never ConflictDetector's count
    public int deadlockCount;
    public int rerouteCount;
    public int idleTicksTotal;
    public int messageCount;
    public long seed;
}
