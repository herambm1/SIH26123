package com.sih26123.backend.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * EventIngestController — receives SimulationEvent lists pushed by Python runner.
 * Owner: Member 6
 *
 * POST /api/events  body: SimulationEvent[]  — once per tick, may be empty array
 *
 * On receipt: persist events, broadcast over WebSocket to dashboard alerts feed.
 *
 * Implementation: Member 6's responsibility.
 */
@RestController
@RequestMapping("/api/events")
public class EventIngestController {

    @PostMapping
    public ResponseEntity<Void> ingestEvents(@RequestBody List<Object> events) {
        // TODO: Member 6 — persist, broadcast
        return ResponseEntity.status(501).build();
    }
}
