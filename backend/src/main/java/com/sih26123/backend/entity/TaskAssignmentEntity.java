package com.sih26123.backend.entity;

import com.sih26123.backend.model.TaskAssignmentDto;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * TaskAssignmentEntity — mirrors shared/python/models.py TaskAssignment.
 * Owner: Member 6
 *
 * Each row is a historical robot&lt;-&gt;task assignment record (reassignment
 * creates a new row rather than mutating the old one, so the assignment
 * history is preserved for the demo's audit trail).
 */
@Entity
@Table(name = "task_assignments")
public class TaskAssignmentEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "task_id")
    private String taskId;

    @Column(name = "robot_id")
    private String robotId;

    @Column(name = "assigned_at_tick")
    private int assignedAtTick;

    @Column(name = "estimated_completion_tick")
    private Integer estimatedCompletionTick;

    public TaskAssignmentEntity() {
    }

    public TaskAssignmentEntity(String taskId, String robotId, int assignedAtTick, Integer estimatedCompletionTick) {
        this.taskId = taskId;
        this.robotId = robotId;
        this.assignedAtTick = assignedAtTick;
        this.estimatedCompletionTick = estimatedCompletionTick;
    }

    public TaskAssignmentDto toDto() {
        TaskAssignmentDto dto = new TaskAssignmentDto();
        dto.taskId = this.taskId;
        dto.robotId = this.robotId;
        dto.assignedAtTick = this.assignedAtTick;
        dto.estimatedCompletionTick = this.estimatedCompletionTick;
        return dto;
    }

    public Long getId() {
        return id;
    }

    public String getTaskId() {
        return taskId;
    }

    public String getRobotId() {
        return robotId;
    }

    public int getAssignedAtTick() {
        return assignedAtTick;
    }
}
