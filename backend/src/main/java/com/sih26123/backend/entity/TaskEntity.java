package com.sih26123.backend.entity;

import com.sih26123.backend.model.TaskDto;
import jakarta.persistence.AttributeOverride;
import jakarta.persistence.AttributeOverrides;
import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * TaskEntity — mirrors shared/python/models.py Task. Owner: Member 6
 */
@Entity
@Table(name = "tasks")
public class TaskEntity {

    @Id
    @Column(name = "task_id")
    private String taskId;

    @Embedded
    @AttributeOverrides({
            @AttributeOverride(name = "x", column = @Column(name = "pickup_x")),
            @AttributeOverride(name = "y", column = @Column(name = "pickup_y")),
            @AttributeOverride(name = "tick", column = @Column(name = "pickup_tick"))
    })
    private PositionEmbeddable pickupPosition;

    @Embedded
    @AttributeOverrides({
            @AttributeOverride(name = "x", column = @Column(name = "drop_x")),
            @AttributeOverride(name = "y", column = @Column(name = "drop_y")),
            @AttributeOverride(name = "tick", column = @Column(name = "drop_tick"))
    })
    private PositionEmbeddable dropPosition;

    private int priority;
    private String status;

    @Column(name = "created_at_tick")
    private int createdAtTick;

    public TaskEntity() {
    }

    public static TaskEntity fromDto(TaskDto dto) {
        TaskEntity e = new TaskEntity();
        e.taskId = dto.taskId;
        e.pickupPosition = PositionEmbeddable.fromDto(dto.pickupPosition);
        e.dropPosition = PositionEmbeddable.fromDto(dto.dropPosition);
        e.priority = dto.priority;
        e.status = dto.status;
        e.createdAtTick = dto.createdAtTick;
        return e;
    }

    public TaskDto toDto() {
        TaskDto dto = new TaskDto();
        dto.taskId = this.taskId;
        dto.pickupPosition = this.pickupPosition == null ? null : this.pickupPosition.toDto();
        dto.dropPosition = this.dropPosition == null ? null : this.dropPosition.toDto();
        dto.priority = this.priority;
        dto.status = this.status;
        dto.createdAtTick = this.createdAtTick;
        return dto;
    }

    public String getTaskId() {
        return taskId;
    }

    public PositionEmbeddable getPickupPosition() {
        return pickupPosition;
    }

    public PositionEmbeddable getDropPosition() {
        return dropPosition;
    }

    public int getPriority() {
        return priority;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
