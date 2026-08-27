package com.sih26123.backend.websocket;

/**
 * LiveUpdateWebSocketHandler — handles /ws/live WebSocket connections.
 * Owner: Member 6
 *
 * On new client connect: send a snapshot (ROBOT_STATE_BATCH with current cache).
 * Ongoing: LiveUpdateBroadcaster pushes frames as ingestion happens.
 *
 * Implementation: Member 6's responsibility.
 */
public class LiveUpdateWebSocketHandler {
    // TODO: Member 6 — extend Spring's WebSocketHandler,
    // register at /ws/live in a WebSocket configuration class,
    // and integrate with LiveUpdateBroadcaster.
}
