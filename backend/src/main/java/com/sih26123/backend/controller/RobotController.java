package com.sih26123.backend.controller;

import com.sih26123.backend.model.ApiErrorDto;
import com.sih26123.backend.model.RobotStateDto;
import com.sih26123.backend.service.RobotCacheService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * RobotController — serves the latest RobotState snapshots to the dashboard.
 * Owner: Member 6
 *
 * GET  /api/robots       → list of latest RobotState (from in-memory cache)
 * GET  /api/robots/{id}  → single RobotState by robot ID
 */
@RestController
@RequestMapping("/api/robots")
public class RobotController {

    private final RobotCacheService robotCacheService;

    public RobotController(RobotCacheService robotCacheService) {
        this.robotCacheService = robotCacheService;
    }

    @GetMapping
    public ResponseEntity<List<RobotStateDto>> getRobots() {
        return ResponseEntity.ok(robotCacheService.getAll());
    }

    @GetMapping("/{id}")
    public ResponseEntity<?> getRobotById(@PathVariable String id) {
        return robotCacheService.get(id)
                .<ResponseEntity<?>>map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.status(404)
                        .body(new ApiErrorDto("ROBOT_NOT_FOUND", "No known robot with id '" + id + "'.")));
    }
}
