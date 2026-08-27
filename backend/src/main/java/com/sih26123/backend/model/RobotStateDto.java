package com.sih26123.backend.model;

import java.util.List;

/**
 * RobotStateDto — mirrors shared/python/models.py RobotState.
 * Owner: Member 6
 * Source of truth: docs/00_SHARED_CONTRACTS.md / shared/python/models.py
 *
 * status ∈ {IDLE, MOVING, WAITING, BLOCKED, CHARGING, OFFLINE}
 */
public class RobotStateDto {
    public String robotId;
    public PositionDto position;
    public double velocity;        // cells/tick; 0 or 1 in the MVP
    public double battery;         // 0-100
    public String currentTaskId;   // nullable
    public PositionDto destination; // nullable
    public List<PositionDto> currentPath; // remaining waypoints
    public String status;          // IDLE|MOVING|WAITING|BLOCKED|CHARGING|OFFLINE
    public int timestamp;          // simulation tick of this snapshot
}
