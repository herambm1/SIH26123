package com.sih26123.backend.model;

import java.util.List;

/**
 * ConflictDto — mirrors shared/python/models.py Conflict.
 * Owner: Member 6
 * Source of truth: docs/00_SHARED_CONTRACTS.md / shared/python/models.py
 *
 * type ∈ {SAME_CELL, CROSSING, NARROW_AISLE_HEADON}
 * resolutionAction ∈ {CONTINUE, WAIT, YIELD, REROUTE, REASSIGN_TASK}
 */
public class ConflictDto {
    public String conflictId;
    public List<String> robotIds;  // exactly 2 in the MVP
    public String type;            // SAME_CELL|CROSSING|NARROW_AISLE_HEADON
    public PositionDto predictedCell;
    public int predictedTick;
    public String severity;        // LOW|MEDIUM|HIGH
    public String resolutionAction; // nullable
}
