package com.sih26123.backend.controller;

import com.sih26123.backend.entity.ScenarioEntity;
import com.sih26123.backend.entity.SimulationRunEntity;
import com.sih26123.backend.model.RobotTaskAssignmentDto;
import com.sih26123.backend.model.SimulationControlRequestDto;
import com.sih26123.backend.model.SimulationStatusDto;
import com.sih26123.backend.repository.ScenarioRepository;
import com.sih26123.backend.repository.SimulationRunRepository;
import com.sih26123.backend.service.SimulationClient;
import com.sih26123.backend.service.TaskAllocationService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * SimulationControlController — bridges dashboard requests to the Python
 * simulation engine. Owner: Member 6
 *
 * POST /api/simulation/control  body: {action: "start"|"stop", scenarioId, mode, seed, speed}
 * GET  /api/simulation/status   → delegates to SimulationClient → Python /control/status
 *
 * Failures from SimulationClient (Python unreachable, or Python rejects the
 * request) are handled by GlobalExceptionHandler — this backend stays alive
 * and returns a clear error either way (docs/06_BACKEND.md §13).
 */
@RestController
@RequestMapping("/api/simulation")
public class SimulationControlController {

    private final SimulationClient simulationClient;
    private final SimulationRunRepository simulationRunRepository;
    private final ScenarioRepository scenarioRepository;
    private final TaskAllocationService taskAllocationService;

    public SimulationControlController(SimulationClient simulationClient,
                                        SimulationRunRepository simulationRunRepository,
                                        ScenarioRepository scenarioRepository,
                                        TaskAllocationService taskAllocationService) {
        this.simulationClient = simulationClient;
        this.simulationRunRepository = simulationRunRepository;
        this.scenarioRepository = scenarioRepository;
        this.taskAllocationService = taskAllocationService;
    }

    @PostMapping("/control")
    public ResponseEntity<?> control(@RequestBody SimulationControlRequestDto body) {
        if (body == null || body.action == null) {
            throw new IllegalArgumentException("action ('start' or 'stop') is required.");
        }

        if ("start".equalsIgnoreCase(body.action)) {
            if (body.scenarioId == null || body.scenarioId.isBlank()) {
                throw new IllegalArgumentException("scenarioId is required to start a simulation.");
            }
            String mode = body.mode == null ? "DECENTRALIZED_PROPOSED" : body.mode;
            long seed = body.seed == null ? 42L : body.seed;
            String speed = body.speed == null ? "BATCH" : body.speed;

            // Real, current Task/TaskAssignment data (Member 6's centralized
            // allocation) rides along with the start request so it actually
            // reaches the decentralized Python simulation — see
            // TaskAllocationService.currentAssignmentsForSimulation() and
            // CLAUDE.md Known Integration Gaps #3 (closed this session).
            List<RobotTaskAssignmentDto> assignments = taskAllocationService.currentAssignmentsForSimulation();
            simulationClient.start(body.scenarioId, mode, seed, speed, assignments);

            String runId = "run_" + body.scenarioId + "_" + mode + "_" + seed + "_" + UUID.randomUUID();
            simulationRunRepository.save(new SimulationRunEntity(runId, body.scenarioId, mode, seed, speed,
                    "STARTED", Instant.now()));
            scenarioRepository.save(new ScenarioEntity(body.scenarioId, Instant.now(), Instant.now()));

            Map<String, Object> ack = new LinkedHashMap<>();
            ack.put("message", "Simulation start requested");
            ack.put("runId", runId);
            ack.put("scenarioId", body.scenarioId);
            ack.put("mode", mode);
            ack.put("seed", seed);
            ack.put("speed", speed);
            return ResponseEntity.ok(ack);
        }

        if ("stop".equalsIgnoreCase(body.action)) {
            simulationClient.stop();
            return ResponseEntity.ok(Map.of("message", "Simulation stop requested"));
        }

        throw new IllegalArgumentException("Unknown action '" + body.action + "' — must be 'start' or 'stop'.");
    }

    @GetMapping("/status")
    public ResponseEntity<SimulationStatusDto> status() {
        return ResponseEntity.ok(simulationClient.status());
    }
}
