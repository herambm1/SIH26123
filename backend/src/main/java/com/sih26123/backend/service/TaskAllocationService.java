package com.sih26123.backend.service;

/**
 * TaskAllocationService — greedy/nearest-idle-robot task assignment.
 * Owner: Member 6
 *
 * Responsibilities:
 *   - Assign pending tasks to idle robots (greedy heuristic).
 *   - On RobotState.status=OFFLINE for a robot with an active task, automatically
 *     reassign that task to the next nearest idle robot.
 *
 * Implementation: Member 6's responsibility.
 */
public class TaskAllocationService {

    /**
     * Attempt to assign any PENDING tasks to currently IDLE robots.
     * Implementation: Member 6's responsibility.
     */
    public void allocatePendingTasks() {
        throw new UnsupportedOperationException("Not implemented");
    }

    /**
     * Handle a robot going OFFLINE while holding an active task.
     * Reassigns the task to the next nearest idle robot and emits a TASK_REASSIGNED record.
     *
     * @param offlineRobotId the robot that went OFFLINE
     * Implementation: Member 6's responsibility.
     */
    public void handleRobotOffline(String offlineRobotId) {
        throw new UnsupportedOperationException("Not implemented");
    }
}
