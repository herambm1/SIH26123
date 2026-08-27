package com.sih26123.backend.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * WarehouseController — serves the WarehouseMap to the dashboard.
 * Owner: Member 6
 *
 * GET /api/warehouse  → WarehouseMap (fetched once from Python at run start, cached)
 *
 * Implementation: Member 6's responsibility.
 */
@RestController
@RequestMapping("/api/warehouse")
public class WarehouseController {

    @GetMapping
    public ResponseEntity<?> getWarehouseMap() {
        return ResponseEntity.status(501).body("Not implemented");
    }
}
