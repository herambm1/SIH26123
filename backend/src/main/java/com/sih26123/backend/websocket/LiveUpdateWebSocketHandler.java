package com.sih26123.backend.websocket;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sih26123.backend.model.RobotStateDto;
import com.sih26123.backend.service.RobotCacheService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArraySet;

/**
 * LiveUpdateWebSocketHandler — handles /ws/live WebSocket connections.
 * Owner: Member 6
 *
 * On new client connect: sends a ROBOT_STATE_BATCH snapshot of the current
 * robot cache. Thereafter, LiveUpdateBroadcaster pushes frames here as
 * ingestion happens. Zero connected clients is a valid, no-op state.
 */
@Component
public class LiveUpdateWebSocketHandler extends TextWebSocketHandler {

    private static final Logger log = LoggerFactory.getLogger(LiveUpdateWebSocketHandler.class);

    private final Set<WebSocketSession> sessions = new CopyOnWriteArraySet<>();
    private final RobotCacheService robotCacheService;
    private final ObjectMapper objectMapper;

    public LiveUpdateWebSocketHandler(RobotCacheService robotCacheService, ObjectMapper objectMapper) {
        this.robotCacheService = robotCacheService;
        this.objectMapper = objectMapper;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) throws IOException {
        sessions.add(session);
        List<RobotStateDto> snapshot = robotCacheService.getAll();
        Map<String, Object> envelope = new LinkedHashMap<>();
        envelope.put("type", "ROBOT_STATE_BATCH");
        envelope.put("tick", robotCacheService.lastTick());
        envelope.put("payload", snapshot);
        sendQuietly(session, objectMapper.writeValueAsString(envelope));
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        sessions.remove(session);
    }

    @Override
    public void handleTransportError(WebSocketSession session, Throwable exception) {
        sessions.remove(session);
    }

    /** Broadcast a pre-serialized JSON envelope to every connected client. No-op if none. */
    public void broadcast(String json) {
        if (sessions.isEmpty()) {
            return;
        }
        for (WebSocketSession session : sessions) {
            sendQuietly(session, json);
        }
    }

    private void sendQuietly(WebSocketSession session, String json) {
        try {
            if (session.isOpen()) {
                session.sendMessage(new TextMessage(json));
            }
        } catch (IOException e) {
            log.warn("Failed to send WebSocket frame to session {}, dropping it: {}", session.getId(), e.getMessage());
            sessions.remove(session);
        }
    }

    public int connectedClientCount() {
        return sessions.size();
    }
}
