package com.sih26123.backend.model;

/**
 * TaskDto — mirrors shared/python/models.py Task.
 * Owner: Member 6
 * Source of truth: docs/00_SHARED_CONTRACTS.md / shared/python/models.py
 *
 * status ∈ {PENDING, ASSIGNED, IN_PROGRESS, COMPLETED, REASSIGNED, FAILED}
 */
public class TaskDto {
    public String taskId;
    public PositionDto pickupPosition;
    public PositionDto dropPosition;
    public int priority;           // 1 (low) .. 5 (high)
    public String status;          // PENDING|ASSIGNED|IN_PROGRESS|COMPLETED|REASSIGNED|FAILED
    public int createdAtTick;
}
