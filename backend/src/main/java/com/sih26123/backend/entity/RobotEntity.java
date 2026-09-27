package com.sih26123.backend.entity;

import com.fasterxml.jackson.core.type.TypeReference;
import com.sih26123.backend.model.PositionDto;
import com.sih26123.backend.model.RobotStateDto;
import com.sih26123.backend.util.JsonUtil;
import jakarta.persistence.AttributeOverride;
import jakarta.persistence.AttributeOverrides;
import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;

import java.util.List;

/**
 * RobotEntity — persisted LATEST RobotState per robot (one row per robot,
 * upserted on every telemetry ingestion). Mirrors shared/python/models.py
 * RobotState. Owner: Member 6
 *
 * Deliberately NOT a row-per-tick table — see docs/06_BACKEND.md §8.6:
 * "keep the latest RobotState per robot ... not a row per tick per robot."
 * Per-tick history (aggregated) lives in TelemetryEntity instead.
 */
@Entity
@Table(name = "robots")
public class RobotEntity {

    @Id
    @Column(name = "robot_id")
    private String robotId;

    @Embedded
    @AttributeOverrides({
            @AttributeOverride(name = "x", column = @Column(name = "position_x")),
            @AttributeOverride(name = "y", column = @Column(name = "position_y")),
            @AttributeOverride(name = "tick", column = @Column(name = "position_tick"))
    })
    private PositionEmbeddable position;

    private double velocity;
    private double battery;

    @Column(name = "current_task_id")
    private String currentTaskId;

    @Embedded
    @AttributeOverrides({
            @AttributeOverride(name = "x", column = @Column(name = "destination_x")),
            @AttributeOverride(name = "y", column = @Column(name = "destination_y")),
            @AttributeOverride(name = "tick", column = @Column(name = "destination_tick"))
    })
    private PositionEmbeddable destination;

    @Lob
    @Column(name = "current_path_json")
    private String currentPathJson;

    private String status;

    private int timestamp;

    public RobotEntity() {
    }

    public static RobotEntity fromDto(RobotStateDto dto) {
        RobotEntity e = new RobotEntity();
        e.robotId = dto.robotId;
        e.position = PositionEmbeddable.fromDto(dto.position);
        e.velocity = dto.velocity;
        e.battery = dto.battery;
        e.currentTaskId = dto.currentTaskId;
        e.destination = PositionEmbeddable.fromDto(dto.destination);
        e.currentPathJson = JsonUtil.toJson(dto.currentPath);
        e.status = dto.status;
        e.timestamp = dto.timestamp;
        return e;
    }

    public RobotStateDto toDto() {
        RobotStateDto dto = new RobotStateDto();
        dto.robotId = this.robotId;
        dto.position = this.position == null ? null : this.position.toDto();
        dto.velocity = this.velocity;
        dto.battery = this.battery;
        dto.currentTaskId = this.currentTaskId;
        dto.destination = this.destination == null ? null : this.destination.toDto();
        List<PositionDto> path = JsonUtil.toListOrEmpty(this.currentPathJson, new TypeReference<List<PositionDto>>() {
        });
        dto.currentPath = path;
        dto.status = this.status;
        dto.timestamp = this.timestamp;
        return dto;
    }

    public String getRobotId() {
        return robotId;
    }

    public String getStatus() {
        return status;
    }

    public int getTimestamp() {
        return timestamp;
    }

    public String getCurrentTaskId() {
        return currentTaskId;
    }
}
