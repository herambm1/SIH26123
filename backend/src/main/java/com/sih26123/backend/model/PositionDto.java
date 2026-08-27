package com.sih26123.backend.model;

/**
 * PositionDto — mirrors shared/python/models.py Position.
 * Owner: Member 6
 * Source of truth: docs/00_SHARED_CONTRACTS.md / shared/python/models.py
 *
 * tick is set on RobotPath waypoints (space-time); null on current-position snapshots.
 */
public class PositionDto {
    public int x;
    public int y;
    public Integer tick; // nullable
}
