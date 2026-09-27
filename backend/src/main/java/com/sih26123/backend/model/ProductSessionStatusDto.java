package com.sih26123.backend.model;

/**
 * ProductSessionStatusDto — GET /api/product/session response shape.
 * Owner: Member 6
 *
 * Not a shared/python/models.py contract (Product mode has no such contract
 * — see the Product-mode design brief's preference for payload-only tagging
 * over new frozen fields). Counters are read directly off
 * ProductSessionService's own in-memory bookkeeping, never derived from
 * PerformanceMetric (which is a single-run, end-of-run contract that does
 * not fit a continuously-running session).
 */
public class ProductSessionStatusDto {
    public boolean running;
    public String sessionId;
    public Long seed;
    public int currentTick;
    public int tasksCreated;
    public int tasksInProgress;
    public int tasksCompleted;
    public int tasksReassigned;
    public int tasksPendingOrAssigned;
    /** Abandoned after repeatedly being assigned to a non-live (stale-cache)
     * robot — see ProductSessionService.MAX_STALE_ROBOT_REVERTS. Expected to
     * be 0 in ordinary operation. */
    public int tasksFailed;
    /** Robots currently "broken down": latched the first time a live robot of this session reports OFFLINE, cleared only by
     * a fix (POST /api/product/robot/{id}/fix). A Java-side overlay - deliberately NOT a RobotState.status value, because
     * Python's own OFFLINE label flickers (a dead robot's end-of-tick status can read BLOCKED) and RobotState is a frozen
     * contract. Sorted; empty when nothing is broken. */
    public java.util.List<String> brokenDownRobots = new java.util.ArrayList<>();
}
