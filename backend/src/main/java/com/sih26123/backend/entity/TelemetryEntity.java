package com.sih26123.backend.entity;

import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * TelemetryEntity — a PERIODIC (not per-tick) robot position/battery sample.
 * Owner: Member 6
 *
 * docs/06_BACKEND.md §8.6 explicitly forbids persisting every simulation tick
 * as a permanent raw row per robot. TelemetryIngestController samples one row
 * every TELEMETRY_SAMPLE_INTERVAL ticks per robot instead, giving a bounded
 * historical trail rather than unbounded raw storage.
 */
@Entity
@Table(name = "telemetry_snapshots")
public class TelemetryEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String robotId;

    @Embedded
    private PositionEmbeddable position;

    private double battery;
    private boolean obstacleDetected;
    private String sensorHealth;
    private int tick;

    public TelemetryEntity() {
    }

    public TelemetryEntity(String robotId, PositionEmbeddable position, double battery,
                            boolean obstacleDetected, String sensorHealth, int tick) {
        this.robotId = robotId;
        this.position = position;
        this.battery = battery;
        this.obstacleDetected = obstacleDetected;
        this.sensorHealth = sensorHealth;
        this.tick = tick;
    }

    public Long getId() {
        return id;
    }

    public String getRobotId() {
        return robotId;
    }

    public int getTick() {
        return tick;
    }
}
