package com.sih26123.backend.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.Instant;

/**
 * ScenarioEntity — a lightweight registry of scenario IDs seen by the backend
 * (first observed via a /control/start call or a metrics push). Owner: Member 6
 *
 * The scenario DEFINITION lives in Python (simulation/scenarios/), which the
 * backend must not modify or duplicate — this table only records that a given
 * scenarioId has been run, for dashboard convenience (e.g. metrics filters).
 */
@Entity
@Table(name = "scenarios")
public class ScenarioEntity {

    @Id
    @Column(name = "scenario_id")
    private String scenarioId;

    @Column(name = "first_seen_at")
    private Instant firstSeenAt;

    @Column(name = "last_run_at")
    private Instant lastRunAt;

    public ScenarioEntity() {
    }

    public ScenarioEntity(String scenarioId, Instant firstSeenAt, Instant lastRunAt) {
        this.scenarioId = scenarioId;
        this.firstSeenAt = firstSeenAt;
        this.lastRunAt = lastRunAt;
    }

    public String getScenarioId() {
        return scenarioId;
    }

    public Instant getLastRunAt() {
        return lastRunAt;
    }

    public void setLastRunAt(Instant lastRunAt) {
        this.lastRunAt = lastRunAt;
    }
}
