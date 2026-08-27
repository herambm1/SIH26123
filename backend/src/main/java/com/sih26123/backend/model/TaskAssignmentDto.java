package com.sih26123.backend.model;

/**
 * TaskAssignmentDto — mirrors shared/python/models.py TaskAssignment.
 * Owner: Member 6
 * Source of truth: docs/00_SHARED_CONTRACTS.md / shared/python/models.py
 */
public class TaskAssignmentDto {
    public String taskId;
    public String robotId;
    public int assignedAtTick;
    public Integer estimatedCompletionTick; // nullable
}
