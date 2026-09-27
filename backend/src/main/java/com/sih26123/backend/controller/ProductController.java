package com.sih26123.backend.controller;

import com.sih26123.backend.model.ProductSessionStatusDto;
import com.sih26123.backend.service.ProductSessionService;
import com.sih26123.backend.service.SimulationClient;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * ProductController — Java-side entry points for the live "Product" tab.
 * Owner: Member 6 (Phase 2, product-mode).
 *
 * POST /api/product/session/start  body: {seed?, robotCount?, speed?, config?}
 * POST /api/product/session/stop
 * GET  /api/product/session        → ProductSessionStatusDto
 * POST /api/product/inject         body: {kind, cell?, robotId?} — proxies to
 *                                   Python /control/inject
 *
 * A completely separate path from SimulationControlController (scenario
 * runs, /api/simulation/*) — that controller is not touched by this file.
 * Failures from SimulationClient are handled by the existing
 * GlobalExceptionHandler, unchanged.
 */
@RestController
@RequestMapping("/api/product")
public class ProductController {

    private static final int DEFAULT_ROBOT_COUNT = 5;
    private static final int MIN_ROBOT_COUNT = 4;
    private static final int MAX_ROBOT_COUNT = 6;

    private final ProductSessionService productSessionService;
    private final SimulationClient simulationClient;

    public ProductController(ProductSessionService productSessionService, SimulationClient simulationClient) {
        this.productSessionService = productSessionService;
        this.simulationClient = simulationClient;
    }

    @PostMapping("/session/start")
    public ResponseEntity<?> startSession(@RequestBody(required = false) Map<String, Object> body) {
        if (productSessionService.isRunning()) {
            throw new IllegalArgumentException("A product session is already running.");
        }
        Map<String, Object> req = body == null ? Map.of() : body;

        Long seed = req.get("seed") == null ? null : ((Number) req.get("seed")).longValue();
        String speed = (String) req.getOrDefault("speed", "BATCH");
        @SuppressWarnings("unchecked")
        Map<String, Object> config = (Map<String, Object>) req.getOrDefault("config", new LinkedHashMap<>());

        int robotCount = DEFAULT_ROBOT_COUNT;
        if (config.get("robotCount") != null) {
            robotCount = ((Number) config.get("robotCount")).intValue();
        }
        robotCount = Math.max(MIN_ROBOT_COUNT, Math.min(MAX_ROBOT_COUNT, robotCount));
        config.put("robotCount", robotCount);

        // Python is the source of truth for sessionId/seed (it generates a
        // random seed itself when none is supplied) — Java's own
        // ProductSessionService tags every event it emits with THIS exact
        // sessionId, never one generated independently here, so Java- and
        // Python-originated events for the same session always correlate.
        productSessionService.prepareNewSession();
        Map<String, Object> pythonResult = simulationClient.startProduct(seed, speed, config);
        String sessionId = (String) pythonResult.get("sessionId");
        long actualSeed = ((Number) pythonResult.get("seed")).longValue();

        productSessionService.start(sessionId, actualSeed, robotCount);

        Map<String, Object> ack = new LinkedHashMap<>();
        ack.put("message", "Product session started");
        ack.put("sessionId", sessionId);
        ack.put("seed", actualSeed);
        ack.put("robotCount", robotCount);
        ack.put("speed", speed);
        return ResponseEntity.ok(ack);
    }

    @PostMapping("/session/stop")
    public ResponseEntity<?> stopSession() {
        productSessionService.stop();
        simulationClient.stopProduct();
        return ResponseEntity.ok(Map.of("message", "Product session stop requested"));
    }

    @GetMapping("/session")
    public ResponseEntity<ProductSessionStatusDto> session() {
        return ResponseEntity.ok(productSessionService.status());
    }

    /** "Mark as fixed" for a broken-down robot - see ProductSessionService.fixRobot. */
    @PostMapping("/robot/{robotId}/fix")
    public ResponseEntity<?> fixRobot(@PathVariable String robotId) {
        productSessionService.fixRobot(robotId);
        return ResponseEntity.ok(Map.of("robotId", robotId, "message", "Recovery requested; the robot becomes available "
                + "for new tasks once it reports IDLE"));
    }

    @PostMapping("/inject")
    public ResponseEntity<?> inject(@RequestBody Map<String, Object> body) {
        if (!productSessionService.isRunning()) {
            throw new IllegalArgumentException("No product session running.");
        }
        if (body == null || body.get("kind") == null) {
            throw new IllegalArgumentException("kind ('AISLE_BLOCK'|'ROBOT_OFFLINE'|'COMM_DELAY') is required.");
        }
        // Queued only — see SimulationClient.injectProductFault's javadoc:
        // the real accept/reject decision is reported asynchronously as a
        // SYSTEM SimulationEvent, never synchronously in this response.
        Map<String, Object> result = simulationClient.injectProductFault(body);
        return ResponseEntity.ok(result);
    }
}
