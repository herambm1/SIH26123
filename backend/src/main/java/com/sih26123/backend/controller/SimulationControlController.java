package com.sih26123.backend.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * SimulationControlController — bridges dashboard requests to Python simulation engine.
 * Owner: Member 6
 *
 * POST /api/simulation/control  body: {action: "start"|"stop", scenarioId, mode, seed, speed}
 *                                → delegates to SimulationClient → Python /control/*
 * GET  /api/simulation/status   → delegates to SimulationClient → Python /control/status
 *
 * Implementation: Member 6's responsibility.
 */
@RestController
@RequestMapping("/api/simulation")
public class SimulationControlController {

    @PostMapping("/control")
    public ResponseEntity<?> control(@RequestBody Object body) {
        // TODO: Member 6 — call SimulationClient.start() or .stop()
        return ResponseEntity.status(501).body("Not implemented");
    }

    @GetMapping("/status")
    public ResponseEntity<?> status() {
        // TODO: Member 6 — call SimulationClient.status()
        return ResponseEntity.status(501).body("Not implemented");
    }
}
