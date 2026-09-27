package com.sih26123.backend.websocket;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sih26123.backend.model.PositionDto;
import com.sih26123.backend.model.RobotStateDto;
import com.sih26123.backend.service.RobotCacheService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * End-to-end test of /ws/live: snapshot-on-connect and live broadcast-on-ingest,
 * per docs/06_BACKEND.md §8.5 and §15.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class LiveUpdateWebSocketIntegrationTest {

    @LocalServerPort
    private int port;

    @Autowired
    private RobotCacheService robotCacheService;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void onConnect_receivesRobotStateBatchSnapshot() throws Exception {
        RobotStateDto seed = new RobotStateDto();
        seed.robotId = "WS_SNAPSHOT_ROBOT";
        seed.position = new PositionDto();
        seed.position.x = 1;
        seed.position.y = 1;
        seed.status = "IDLE";
        seed.timestamp = 2;
        robotCacheService.upsert(seed);

        BlockingQueue<String> received = new ArrayBlockingQueue<>(10);
        StandardWebSocketClient client = new StandardWebSocketClient();
        WebSocketSession session = client.execute(new TextWebSocketHandler() {
            @Override
            protected void handleTextMessage(WebSocketSession s, TextMessage message) {
                received.add(message.getPayload());
            }
        }, "ws://localhost:" + port + "/ws/live").get(5, TimeUnit.SECONDS);

        try {
            String firstFrame = received.poll(5, TimeUnit.SECONDS);
            assertThat(firstFrame).isNotNull();
            JsonNode envelope = objectMapper.readTree(firstFrame);
            assertThat(envelope.get("type").asText()).isEqualTo("ROBOT_STATE_BATCH");
            assertThat(envelope.has("tick")).isTrue();
            boolean containsSeeded = false;
            for (JsonNode node : envelope.get("payload")) {
                if ("WS_SNAPSHOT_ROBOT".equals(node.get("robotId").asText())) {
                    containsSeeded = true;
                }
            }
            assertThat(containsSeeded).isTrue();
        } finally {
            session.close();
        }
    }

    @Test
    void telemetryIngestion_broadcastsLiveToConnectedClient() throws Exception {
        BlockingQueue<String> received = new ArrayBlockingQueue<>(10);
        StandardWebSocketClient client = new StandardWebSocketClient();
        WebSocketSession session = client.execute(new TextWebSocketHandler() {
            @Override
            protected void handleTextMessage(WebSocketSession s, TextMessage message) {
                received.add(message.getPayload());
            }
        }, "ws://localhost:" + port + "/ws/live").get(5, TimeUnit.SECONDS);

        try {
            received.poll(5, TimeUnit.SECONDS); // drain the initial snapshot frame

            RobotStateDto dto = new RobotStateDto();
            dto.robotId = "WS_LIVE_ROBOT";
            dto.position = new PositionDto();
            dto.position.x = 5;
            dto.position.y = 5;
            dto.status = "MOVING";
            dto.timestamp = 9;

            WebTestClient.bindToServer().baseUrl("http://localhost:" + port).build()
                    .post().uri("/api/telemetry/batch")
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(List.of(dto))
                    .exchange()
                    .expectStatus().isOk();

            String liveFrame = received.poll(5, TimeUnit.SECONDS);
            assertThat(liveFrame).isNotNull();
            JsonNode envelope = objectMapper.readTree(liveFrame);
            assertThat(envelope.get("type").asText()).isEqualTo("ROBOT_STATE_BATCH");
            assertThat(envelope.get("payload").toString()).contains("WS_LIVE_ROBOT");
        } finally {
            session.close();
        }
    }
}
