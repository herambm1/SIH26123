package com.sih26123.backend.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sih26123.backend.websocket.LiveUpdateWebSocketHandler;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.Mockito.verify;

/**
 * Zero-WebSocket-client broadcasting must be a safe no-op, never an error
 * (docs/06_BACKEND.md §13).
 */
@ExtendWith(MockitoExtension.class)
class LiveUpdateBroadcasterTest {

    @Mock
    private LiveUpdateWebSocketHandler handler;

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void broadcastWithNoClients_doesNotThrow() {
        LiveUpdateBroadcaster broadcaster = new LiveUpdateBroadcaster(handler, objectMapper);

        assertThatCode(() -> {
            broadcaster.broadcastRobotStateBatch(1, java.util.List.of());
            broadcaster.broadcastEvent(1, java.util.Map.of("type", "TEST"));
            broadcaster.broadcastMetric(1, java.util.Map.of("runId", "r1"));
        }).doesNotThrowAnyException();

        // The broadcaster still delegates to the handler each time — the
        // handler itself is what no-ops when its session set is empty.
        verify(handler, org.mockito.Mockito.times(3)).broadcast(org.mockito.ArgumentMatchers.anyString());
    }
}
