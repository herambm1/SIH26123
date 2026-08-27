package com.sih26123.backend.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * MetricsController — receives PerformanceMetric at end of each simulation run,
 * and serves metrics to the dashboard.
 * Owner: Member 6
 *
 * POST /api/metrics           body: PerformanceMetric  — once at end of a run
 * GET  /api/metrics?scenarioId=  → list of PerformanceMetric for that scenario, across modes
 *
 * Implementation: Member 6's responsibility.
 */
@RestController
@RequestMapping("/api/metrics")
public class MetricsController {

    @PostMapping
    public ResponseEntity<Void> ingestMetric(@RequestBody Object metric) {
        // TODO: Member 6 — persist, broadcast METRIC_UPDATE over WebSocket
        return ResponseEntity.status(501).build();
    }

    @GetMapping
    public ResponseEntity<?> getMetrics(@RequestParam(required = false) String scenarioId) {
        return ResponseEntity.status(501).body("Not implemented");
    }
}
