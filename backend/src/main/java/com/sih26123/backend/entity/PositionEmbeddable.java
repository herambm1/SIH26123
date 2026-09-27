package com.sih26123.backend.entity;

import com.sih26123.backend.model.PositionDto;
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

/**
 * PositionEmbeddable — persistence-mapped form of shared/python/models.py Position.
 * Owner: Member 6
 *
 * Reused (with @AttributeOverrides) wherever an entity needs more than one
 * Position field, to avoid column-name collisions.
 */
@Embeddable
public class PositionEmbeddable {

    @Column
    private Integer x;

    @Column
    private Integer y;

    @Column(name = "tick_value")
    private Integer tick; // nullable — set on RobotPath waypoints, absent on snapshots

    public PositionEmbeddable() {
    }

    public PositionEmbeddable(Integer x, Integer y, Integer tick) {
        this.x = x;
        this.y = y;
        this.tick = tick;
    }

    public static PositionEmbeddable fromDto(PositionDto dto) {
        if (dto == null) {
            return null;
        }
        return new PositionEmbeddable(dto.x, dto.y, dto.tick);
    }

    public PositionDto toDto() {
        PositionDto dto = new PositionDto();
        dto.x = this.x == null ? 0 : this.x;
        dto.y = this.y == null ? 0 : this.y;
        dto.tick = this.tick;
        return dto;
    }

    public Integer getX() {
        return x;
    }

    public void setX(Integer x) {
        this.x = x;
    }

    public Integer getY() {
        return y;
    }

    public void setY(Integer y) {
        this.y = y;
    }

    public Integer getTick() {
        return tick;
    }

    public void setTick(Integer tick) {
        this.tick = tick;
    }
}
