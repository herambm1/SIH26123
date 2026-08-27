package com.sih26123.backend.model;

import java.util.List;

/**
 * WarehouseMapDto — mirrors shared/python/models.py WarehouseMap.
 * Owner: Member 6
 * Source of truth: docs/00_SHARED_CONTRACTS.md / shared/python/models.py
 */
public class WarehouseMapDto {
    public int gridWidth;
    public int gridHeight;
    public List<PositionDto> obstacles;
    public List<PositionDto> chokePoints;
    public List<PositionDto> pickupPoints;
    public List<PositionDto> dropPoints;
    public List<PositionDto> blockedCells;
}
