package com.sih26123.backend.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * TaskController — task creation and retrieval.
 * Owner: Member 6
 *
 * GET  /api/tasks  → list of Task
 * POST /api/tasks  → create a Task, status=PENDING
 *
 * Implementation: Member 6's responsibility.
 */
@RestController
@RequestMapping("/api/tasks")
public class TaskController {

    @GetMapping
    public ResponseEntity<?> getTasks() {
        return ResponseEntity.status(501).body("Not implemented");
    }

    @PostMapping
    public ResponseEntity<?> createTask(@RequestBody Object body) {
        return ResponseEntity.status(501).body("Not implemented");
    }
}
