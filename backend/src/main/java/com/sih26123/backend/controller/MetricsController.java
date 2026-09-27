package com.sih26123.backend.controller;

import com.sih26123.backend.entity.PerformanceMetricEntity;
import com.sih26123.backend.model.PerformanceMetricDto;
import com.sih26123.backend.repository.PerformanceMetricRepository;
import com.sih26123.backend.service.LiveUpdateBroadcaster;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * MetricsController — receives PerformanceMetric at end of each simulation
 * run, and serves metrics to the dashboard. Owner: Member 6
 *
 * POST /api/metrics              body: PerformanceMetric — once at end of a run
 * GET  /api/metrics?scenarioId=  → list of PerformanceMetric for that scenario,
 *                                  across modes (or all metrics if omitted)
 */
@RestController
@RequestMapping("/api/metrics")
public class MetricsController {

    private final PerformanceMetricRepository metricRepository;
    private final LiveUpdateBroadcaster broadcaster;

    public MetricsController(PerformanceMetricRepository metricRepository, LiveUpdateBroadcaster broadcaster) {
        this.metricRepository = metricRepository;
        this.broadcaster = broadcaster;
    }

    @PostMapping
    public ResponseEntity<Void> ingestMetric(@RequestBody PerformanceMetricDto metric) {
        if (metric == null || metric.runId == null || metric.runId.isBlank()) {
            throw new IllegalArgumentException("PerformanceMetric.runId is required.");
        }
        if (metric.scenarioId == null || metric.scenarioId.isBlank()) {
            throw new IllegalArgumentException("PerformanceMetric.scenarioId is required.");
        }
        metricRepository.save(PerformanceMetricEntity.fromDto(metric));
        // PerformanceMetric has no single "current tick" field of its own —
        // totalCompletionTicks is the closest tick-like value available for
        // the live-update envelope.
        broadcaster.broadcastMetric(metric.totalCompletionTicks, metric);
        return ResponseEntity.ok().build();
    }

    @GetMapping
    public ResponseEntity<List<PerformanceMetricDto>> getMetrics(@RequestParam(required = false) String scenarioId) {
        List<PerformanceMetricEntity> entities = (scenarioId == null || scenarioId.isBlank())
                ? metricRepository.findAll()
                : metricRepository.findByScenarioId(scenarioId);
        return ResponseEntity.ok(entities.stream().map(PerformanceMetricEntity::toDto).toList());
    }
}
