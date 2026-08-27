package com.sih26123.backend.service;

/**
 * LiveUpdateBroadcaster — broadcasts ingested data to all connected WebSocket clients.
 * Owner: Member 6
 *
 * Envelope format (consumed by dashboard /ws/live):
 *   { "type": "ROBOT_STATE_BATCH" | "SIMULATION_EVENT" | "METRIC_UPDATE",
 *     "tick": <int>, "payload": <...> }
 *
 * Called by ingestion controllers immediately after cache update — ingest and broadcast
 * in the same request (no polling).
 *
 * Implementation: Member 6's responsibility.
 */
public class LiveUpdateBroadcaster {

    /**
     * Broadcast a ROBOT_STATE_BATCH frame.
     * No-op if no WebSocket clients are connected.
     * Implementation: Member 6's responsibility.
     */
    public void broadcastRobotStateBatch(int tick, Object robotStates) {
        throw new UnsupportedOperationException("Not implemented");
    }

    /**
     * Broadcast a SIMULATION_EVENT frame.
     * Implementation: Member 6's responsibility.
     */
    public void broadcastEvent(int tick, Object event) {
        throw new UnsupportedOperationException("Not implemented");
    }

    /**
     * Broadcast a METRIC_UPDATE frame.
     * Implementation: Member 6's responsibility.
     */
    public void broadcastMetric(int tick, Object metric) {
        throw new UnsupportedOperationException("Not implemented");
    }
}
