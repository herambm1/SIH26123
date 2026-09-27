package com.sih26123.backend.service;

import com.sih26123.backend.model.RobotStateDto;
import org.springframework.stereotype.Service;

import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * RobotCacheService — in-memory "latest RobotState per robot" cache.
 * Owner: Member 6
 *
 * GET /api/robots and GET /api/robots/{id} read from here, not from the
 * database, per docs/06_BACKEND.md §8.1/8.2 — updated synchronously by
 * TelemetryIngestController on every ingested batch (no polling).
 *
 * A plain ConcurrentHashMap is sufficient: the single-threaded MVP simulation
 * pushes telemetry from one Python process, and reads from the dashboard/tests
 * are simple lookups — no need for anything heavier.
 */
@Service
public class RobotCacheService {

    private final Map<String, RobotStateDto> latestByRobotId = new ConcurrentHashMap<>();
    private final AtomicInteger lastTick = new AtomicInteger(0);

    public void upsert(RobotStateDto state) {
        if (state == null || state.robotId == null) {
            return;
        }
        latestByRobotId.put(state.robotId, state);
        if (state.timestamp > lastTick.get()) {
            lastTick.set(state.timestamp);
        }
    }

    public List<RobotStateDto> getAll() {
        return List.copyOf(latestByRobotId.values());
    }

    public Optional<RobotStateDto> get(String robotId) {
        return Optional.ofNullable(latestByRobotId.get(robotId));
    }

    public Collection<RobotStateDto> values() {
        return latestByRobotId.values();
    }

    public int lastTick() {
        return lastTick.get();
    }

    /**
     * Forget every cached robot and restart the tick counter. Only ever called when a NEW product session is about to start
     * (ProductSessionService.prepareNewSession): lastTick() otherwise only increases for the life of the backend process, so
     * a second session's Java-side tick logic (task generation, stall clock) and the WebSocket envelope tick stayed pinned at
     * the previous session's highest tick until the new session's own ticks caught up.
     */
    public void reset() {
        latestByRobotId.clear();
        lastTick.set(0);
    }
}
