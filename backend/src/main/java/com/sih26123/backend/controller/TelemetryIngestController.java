package com.sih26123.backend.controller;

import com.sih26123.backend.entity.PositionEmbeddable;
import com.sih26123.backend.entity.RobotEntity;
import com.sih26123.backend.entity.TelemetryEntity;
import com.sih26123.backend.model.RobotStateDto;
import com.sih26123.backend.repository.RobotRepository;
import com.sih26123.backend.repository.TelemetryRepository;
import com.sih26123.backend.service.LiveUpdateBroadcaster;
import com.sih26123.backend.service.RobotCacheService;
import com.sih26123.backend.service.TaskAllocationService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * TelemetryIngestController — receives telemetry batches pushed by the
 * Python simulation runner. Owner: Member 6
 *
 * POST /api/telemetry/batch  body: RobotState[]  — once per simulation tick
 *
 * On receipt: validates, updates the in-memory cache, persists the latest
 * state per robot, samples a periodic TelemetryEntity row (not a row per
 * tick — see docs/06_BACKEND.md §8.6), triggers OFFLINE-robot task
 * reassignment, and broadcasts ROBOT_STATE_BATCH over WebSocket — all in the
 * same request (no polling).
 */
@RestController
@RequestMapping("/api/telemetry")
public class TelemetryIngestController {

    /** Persist one periodic sample per robot every N ticks, not every tick. */
    private static final int TELEMETRY_SAMPLE_INTERVAL = 10;

    private final RobotCacheService robotCacheService;
    private final RobotRepository robotRepository;
    private final TelemetryRepository telemetryRepository;
    private final TaskAllocationService taskAllocationService;
    private final LiveUpdateBroadcaster broadcaster;

    public TelemetryIngestController(RobotCacheService robotCacheService,
                                      RobotRepository robotRepository,
                                      TelemetryRepository telemetryRepository,
                                      TaskAllocationService taskAllocationService,
                                      LiveUpdateBroadcaster broadcaster) {
        this.robotCacheService = robotCacheService;
        this.robotRepository = robotRepository;
        this.telemetryRepository = telemetryRepository;
        this.taskAllocationService = taskAllocationService;
        this.broadcaster = broadcaster;
    }

    @PostMapping("/batch")
    public ResponseEntity<Void> ingest(@RequestBody List<RobotStateDto> batch) {
        if (batch == null) {
            throw new IllegalArgumentException("Telemetry batch body must be a JSON array of RobotState.");
        }
        int tick = robotCacheService.lastTick();
        for (RobotStateDto state : batch) {
            validate(state);

            robotCacheService.upsert(state);
            robotRepository.save(RobotEntity.fromDto(state));

            if (state.timestamp % TELEMETRY_SAMPLE_INTERVAL == 0) {
                telemetryRepository.save(new TelemetryEntity(
                        state.robotId,
                        state.position == null ? null
                                : new PositionEmbeddable(state.position.x, state.position.y, state.position.tick),
                        state.battery,
                        false,
                        "OK",
                        state.timestamp));
            }

            if ("OFFLINE".equals(state.status)) {
                taskAllocationService.handleRobotOffline(state.robotId);
            }
            tick = Math.max(tick, state.timestamp);
        }

        if (!batch.isEmpty()) {
            taskAllocationService.allocatePendingTasks();
            broadcaster.broadcastRobotStateBatch(tick, batch);
        }
        return ResponseEntity.ok().build();
    }

    private void validate(RobotStateDto state) {
        if (state == null) {
            throw new IllegalArgumentException("Telemetry batch contains a null RobotState entry.");
        }
        if (state.robotId == null || state.robotId.isBlank()) {
            throw new IllegalArgumentException("RobotState.robotId is required.");
        }
        if (state.status == null || state.status.isBlank()) {
            throw new IllegalArgumentException("RobotState.status is required for robot '" + state.robotId + "'.");
        }
    }
}
