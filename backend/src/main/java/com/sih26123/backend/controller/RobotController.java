package com.sih26123.backend.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * RobotController — serves the latest RobotState snapshots to the dashboard.
 * Owner: Member 6
 *
 * GET  /api/robots       → list of latest RobotState (from in-memory cache)
 * GET  /api/robots/{id}  → single RobotState by robot ID
 *
 * Implementation: Member 6's responsibility.
 */
@RestController
@RequestMapping("/api/robots")
public class RobotController {

    @GetMapping
    public ResponseEntity<?> getRobots() {
        return ResponseEntity.status(501).body("Not implemented");
    }

    @GetMapping("/{id}")
    public ResponseEntity<?> getRobotById(@PathVariable String id) {
        return ResponseEntity.status(501).body("Not implemented");
    }
}
