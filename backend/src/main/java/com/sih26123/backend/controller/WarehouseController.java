package com.sih26123.backend.controller;

import com.sih26123.backend.model.ApiErrorDto;
import com.sih26123.backend.model.WarehouseMapDto;
import com.sih26123.backend.service.WarehouseCacheService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * WarehouseController — serves the WarehouseMap to the dashboard.
 * Owner: Member 6
 *
 * GET /api/warehouse  → cached WarehouseMap
 *
 * See WarehouseCacheService for the cross-module gap this endpoint is built
 * around: simulation/runner.py does not currently expose any mechanism (pull
 * endpoint or push) to deliver a WarehouseMap to the backend, so the cache
 * starts empty and this returns 503 until populated. POST /api/warehouse is
 * added here as the natural extension of the existing push-ingestion pattern
 * (telemetry/events/metrics) — unused by Python today, but ready the moment
 * that gap is closed on the Python side.
 */
@RestController
@RequestMapping("/api/warehouse")
public class WarehouseController {

    private final WarehouseCacheService warehouseCacheService;

    public WarehouseController(WarehouseCacheService warehouseCacheService) {
        this.warehouseCacheService = warehouseCacheService;
    }

    @GetMapping
    public ResponseEntity<?> getWarehouseMap() {
        WarehouseMapDto map = warehouseCacheService.get();
        if (map == null) {
            return ResponseEntity.status(503).body(new ApiErrorDto(
                    "WAREHOUSE_MAP_UNAVAILABLE",
                    "No WarehouseMap has been received yet. Python's control server does not currently "
                            + "expose a mechanism to publish one — see POST /api/warehouse."));
        }
        return ResponseEntity.ok(map);
    }

    @PostMapping
    public ResponseEntity<Void> setWarehouseMap(@RequestBody WarehouseMapDto map) {
        if (map == null || map.gridWidth <= 0 || map.gridHeight <= 0) {
            throw new IllegalArgumentException("gridWidth and gridHeight must be positive.");
        }
        warehouseCacheService.set(map);
        return ResponseEntity.accepted().build();
    }
}
