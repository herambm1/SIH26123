package com.sih26123.backend.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.Instant;

/**
 * SimulationRunEntity — one row per start/stop control action issued by this
 * backend against the Python simulation engine. Owner: Member 6
 */
@Entity
@Table(name = "simulation_runs")
public class SimulationRunEntity {

    @Id
    @Column(name = "run_id")
    private String runId;

    @Column(name = "scenario_id")
    private String scenarioId;

    private String mode;
    private long seed;
    private String speed;
    private String status; // STARTED | STOPPED

    @Column(name = "started_at")
    private Instant startedAt;

    @Column(name = "ended_at")
    private Instant endedAt;

    public SimulationRunEntity() {
    }

    public SimulationRunEntity(String runId, String scenarioId, String mode, long seed, String speed,
                                String status, Instant startedAt) {
        this.runId = runId;
        this.scenarioId = scenarioId;
        this.mode = mode;
        this.seed = seed;
        this.speed = speed;
        this.status = status;
        this.startedAt = startedAt;
    }

    public String getRunId() {
        return runId;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public void setEndedAt(Instant endedAt) {
        this.endedAt = endedAt;
    }
}
