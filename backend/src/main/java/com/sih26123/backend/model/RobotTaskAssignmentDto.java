package com.sih26123.backend.model;

/**
 * RobotTaskAssignmentDto — the real, current Task+TaskAssignment data for one
 * robot, as sent from Java to Python's POST /control/start (taskAssignments
 * field). Owner: Member 6.
 *
 * Not itself a shared/python/models.py contract — it's a join of the two
 * frozen contracts Task and TaskAssignment (docs/00_SHARED_CONTRACTS.md),
 * assembled here because Python's simulation needs both a task's
 * pickup/drop/priority (from Task) and which robot currently holds it (from
 * TaskAssignment) in a single per-robot payload at run-start time. See
 * TaskAllocationService.currentAssignmentsForSimulation().
 */
public class RobotTaskAssignmentDto {
    public String robotId;
    public String taskId;
    public PositionDto pickupPosition;
    public PositionDto dropPosition;
    public int priority;
}
