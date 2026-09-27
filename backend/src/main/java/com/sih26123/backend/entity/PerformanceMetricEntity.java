package com.sih26123.backend.entity;

import com.sih26123.backend.model.PerformanceMetricDto;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.Instant;

/**
 * PerformanceMetricEntity — mirrors shared/python/models.py PerformanceMetric.
 * Owner: Member 6
 *
 * One row per completed run (runId is unique per run) — not a growth-unbounded
 * table, since a run only pushes metrics once, at the end.
 */
@Entity
@Table(name = "performance_metrics")
public class PerformanceMetricEntity {

    @Id
    @Column(name = "run_id")
    private String runId;

    @Column(name = "scenario_id")
    private String scenarioId;

    private String mode;

    @Column(name = "total_completion_ticks")
    private int totalCompletionTicks;

    @Column(name = "avg_completion_ticks")
    private double avgCompletionTicks;

    @Column(name = "collision_count")
    private int collisionCount;

    @Column(name = "deadlock_count")
    private int deadlockCount;

    @Column(name = "reroute_count")
    private int rerouteCount;

    @Column(name = "idle_ticks_total")
    private int idleTicksTotal;

    @Column(name = "message_count")
    private int messageCount;

    private long seed;

    @Column(name = "recorded_at")
    private Instant recordedAt;

    public PerformanceMetricEntity() {
    }

    public static PerformanceMetricEntity fromDto(PerformanceMetricDto dto) {
        PerformanceMetricEntity e = new PerformanceMetricEntity();
        e.runId = dto.runId;
        e.scenarioId = dto.scenarioId;
        e.mode = dto.mode;
        e.totalCompletionTicks = dto.totalCompletionTicks;
        e.avgCompletionTicks = dto.avgCompletionTicks;
        e.collisionCount = dto.collisionCount;
        e.deadlockCount = dto.deadlockCount;
        e.rerouteCount = dto.rerouteCount;
        e.idleTicksTotal = dto.idleTicksTotal;
        e.messageCount = dto.messageCount;
        e.seed = dto.seed;
        e.recordedAt = Instant.now();
        return e;
    }

    public PerformanceMetricDto toDto() {
        PerformanceMetricDto dto = new PerformanceMetricDto();
        dto.runId = this.runId;
        dto.scenarioId = this.scenarioId;
        dto.mode = this.mode;
        dto.totalCompletionTicks = this.totalCompletionTicks;
        dto.avgCompletionTicks = this.avgCompletionTicks;
        dto.collisionCount = this.collisionCount;
        dto.deadlockCount = this.deadlockCount;
        dto.rerouteCount = this.rerouteCount;
        dto.idleTicksTotal = this.idleTicksTotal;
        dto.messageCount = this.messageCount;
        dto.seed = this.seed;
        return dto;
    }

    public String getRunId() {
        return runId;
    }

    public String getScenarioId() {
        return scenarioId;
    }
}
