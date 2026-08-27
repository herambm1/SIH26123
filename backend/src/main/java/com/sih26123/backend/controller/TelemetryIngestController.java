package com.sih26123.backend.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * TelemetryIngestController — receives telemetry batches pushed by Python simulation runner.
 * Owner: Member 6
 *
 * POST /api/telemetry/batch  body: RobotState[]  — once per simulation tick
 *
 * On receipt: update in-memory cache, persist to DB, broadcast over WebSocket.
 *
 * Implementation: Member 6's responsibility.
 */
@RestController
@RequestMapping("/api/telemetry")
public class TelemetryIngestController {

    @PostMapping("/batch")
    public ResponseEntity<Void> ingest(@RequestBody List<Object> batch) {
        // TODO: Member 6 — update cache, persist, broadcast
        return ResponseEntity.status(501).build();
    }
}
