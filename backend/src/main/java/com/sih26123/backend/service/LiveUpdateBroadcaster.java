package com.sih26123.backend.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sih26123.backend.websocket.LiveUpdateWebSocketHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * LiveUpdateBroadcaster — formats ingested data into the live-update envelope
 * and pushes it to LiveUpdateWebSocketHandler for delivery to /ws/live clients.
 * Owner: Member 6
 *
 * Envelope format (consumed by dashboard, see dashboard/src/types/contracts.ts
 * LiveWsMessage — matches exactly):
 *   { "type": "ROBOT_STATE_BATCH" | "SIMULATION_EVENT" | "METRIC_UPDATE",
 *     "tick": <int>, "payload": <...> }
 *
 * Called by ingestion controllers immediately after cache update/persistence —
 * ingest and broadcast happen in the same request, no polling. A no-op when
 * zero WebSocket clients are connected (handled inside the handler).
 */
@Service
public class LiveUpdateBroadcaster {

    private static final Logger log = LoggerFactory.getLogger(LiveUpdateBroadcaster.class);

    private final LiveUpdateWebSocketHandler handler;
    private final ObjectMapper objectMapper;

    public LiveUpdateBroadcaster(LiveUpdateWebSocketHandler handler, ObjectMapper objectMapper) {
        this.handler = handler;
        this.objectMapper = objectMapper;
    }

    public void broadcastRobotStateBatch(int tick, Object robotStates) {
        broadcast("ROBOT_STATE_BATCH", tick, robotStates);
    }

    public void broadcastEvent(int tick, Object event) {
        broadcast("SIMULATION_EVENT", tick, event);
    }

    public void broadcastMetric(int tick, Object metric) {
        broadcast("METRIC_UPDATE", tick, metric);
    }

    private void broadcast(String type, int tick, Object payload) {
        try {
            Map<String, Object> envelope = new LinkedHashMap<>();
            envelope.put("type", type);
            envelope.put("tick", tick);
            envelope.put("payload", payload);
            handler.broadcast(objectMapper.writeValueAsString(envelope));
        } catch (Exception e) {
            // A broadcast/serialization failure must never break the ingestion
            // request that triggered it (docs/06_BACKEND.md §13).
            log.warn("Failed to broadcast {} frame: {}", type, e.getMessage());
        }
    }
}
