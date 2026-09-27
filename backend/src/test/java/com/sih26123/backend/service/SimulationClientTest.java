package com.sih26123.backend.service;

import com.sih26123.backend.model.PositionDto;
import com.sih26123.backend.model.RobotTaskAssignmentDto;
import com.sih26123.backend.model.SimulationStatusDto;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.nio.charset.StandardCharsets;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * SimulationClientTest — exercises SimulationClient against a local mock HTTP
 * server standing in for Python's FastAPI control server, per docs/06_BACKEND.md
 * §15 ("SimulationClient test: against a local mock HTTP server"). No real
 * Python process required.
 */
class SimulationClientTest {

    private HttpServer server;

    @AfterEach
    void tearDown() {
        if (server != null) {
            server.stop(0);
        }
    }

    private SimulationClient clientFor(int port) {
        return new SimulationClient("http://localhost:" + port, 1000, 1000);
    }

    @Test
    void start_success_doesNotThrow() throws IOException {
        server = HttpServer.create(new InetSocketAddress("localhost", 0), 0);
        server.createContext("/control/start", exchange -> respondJson(exchange, 200,
                "{\"message\":\"Simulation started\"}"));
        server.start();

        clientFor(server.getAddress().getPort()).start("a_normal", "DECENTRALIZED_PROPOSED", 42L, "BATCH");
        // No exception thrown = success.
    }

    @Test
    void start_withTaskAssignments_sendsRealAssignmentInRequestBody() throws IOException {
        // Proves requirement (1) "Java can send an assignment" at the actual
        // HTTP boundary — not just that a Java object was constructed.
        StringBuilder capturedBody = new StringBuilder();
        server = HttpServer.create(new InetSocketAddress("localhost", 0), 0);
        server.createContext("/control/start", exchange -> {
            ByteArrayOutputStream buf = new ByteArrayOutputStream();
            exchange.getRequestBody().transferTo(buf);
            capturedBody.append(buf.toString(StandardCharsets.UTF_8));
            respondJson(exchange, 200, "{\"message\":\"Simulation started\"}");
        });
        server.start();

        RobotTaskAssignmentDto assignment = new RobotTaskAssignmentDto();
        assignment.robotId = "R1";
        assignment.taskId = "task_42";
        assignment.pickupPosition = pos(1, 1);
        assignment.dropPosition = pos(9, 9);
        assignment.priority = 4;

        clientFor(server.getAddress().getPort())
                .start("a_normal", "DECENTRALIZED_PROPOSED", 42L, "BATCH", List.of(assignment));

        String body = capturedBody.toString();
        assertThat(body).contains("\"taskAssignments\"");
        assertThat(body).contains("\"robotId\":\"R1\"");
        assertThat(body).contains("\"taskId\":\"task_42\"");
        assertThat(body).contains("\"priority\":4");
    }

    private PositionDto pos(int x, int y) {
        PositionDto p = new PositionDto();
        p.x = x;
        p.y = y;
        return p;
    }

    @Test
    void stop_success_doesNotThrow() throws IOException {
        server = HttpServer.create(new InetSocketAddress("localhost", 0), 0);
        server.createContext("/control/stop", exchange -> respondJson(exchange, 200,
                "{\"message\":\"Simulation stop signaled\"}"));
        server.start();

        clientFor(server.getAddress().getPort()).stop();
    }

    @Test
    void releaseRobot_postsRobotAndTaskToControlRelease() throws IOException {
        StringBuilder capturedBody = new StringBuilder();
        server = HttpServer.create(new InetSocketAddress("localhost", 0), 0);
        server.createContext("/control/release", exchange -> {
            ByteArrayOutputStream buf = new ByteArrayOutputStream();
            exchange.getRequestBody().transferTo(buf);
            capturedBody.append(buf.toString(StandardCharsets.UTF_8));
            respondJson(exchange, 200, "{\"message\":\"Robot release queued\"}");
        });
        server.start();

        clientFor(server.getAddress().getPort()).releaseRobot("PR3", "task_s_7");

        assertThat(capturedBody.toString()).contains("\"robotId\":\"PR3\"").contains("\"taskId\":\"task_s_7\"");
    }

    @Test
    void releaseRobot_noProductSession_throwsWithEngineReachableTrue() throws IOException {
        server = HttpServer.create(new InetSocketAddress("localhost", 0), 0);
        server.createContext("/control/release", exchange -> respondJson(exchange, 400,
                "{\"error\":\"No product session running.\"}"));
        server.start();

        assertThatThrownBy(() -> clientFor(server.getAddress().getPort()).releaseRobot("PR3", "task_s_7"))
                .isInstanceOf(SimulationEngineException.class)
                .satisfies(e -> assertThat(((SimulationEngineException) e).isEngineReachable()).isTrue());
    }

    @Test
    void recoverRobot_postsRobotIdToControlRecover() throws IOException {
        StringBuilder capturedBody = new StringBuilder();
        server = HttpServer.create(new InetSocketAddress("localhost", 0), 0);
        server.createContext("/control/recover", exchange -> {
            ByteArrayOutputStream buf = new ByteArrayOutputStream();
            exchange.getRequestBody().transferTo(buf);
            capturedBody.append(buf.toString(StandardCharsets.UTF_8));
            respondJson(exchange, 200, "{\"message\":\"Robot recovery queued\"}");
        });
        server.start();

        clientFor(server.getAddress().getPort()).recoverRobot("PR3");

        assertThat(capturedBody.toString()).contains("\"robotId\":\"PR3\"");
    }

    @Test
    void status_success_parsesResponseFields() throws IOException {
        server = HttpServer.create(new InetSocketAddress("localhost", 0), 0);
        server.createContext("/control/status", exchange -> respondJson(exchange, 200,
                "{\"running\":true,\"currentTick\":17,\"scenarioId\":\"a_normal\",\"mode\":\"DECENTRALIZED_PROPOSED\"}"));
        server.start();

        SimulationStatusDto status = clientFor(server.getAddress().getPort()).status();

        assertThat(status.running).isTrue();
        assertThat(status.currentTick).isEqualTo(17);
        assertThat(status.scenarioId).isEqualTo("a_normal");
        assertThat(status.mode).isEqualTo("DECENTRALIZED_PROPOSED");
    }

    @Test
    void start_pythonRejects_throwsWithEngineReachableTrue() throws IOException {
        server = HttpServer.create(new InetSocketAddress("localhost", 0), 0);
        server.createContext("/control/start", exchange -> respondJson(exchange, 400,
                "{\"error\":\"Simulation is already running.\"}"));
        server.start();

        assertThatThrownBy(() -> clientFor(server.getAddress().getPort())
                .start("a_normal", "DECENTRALIZED_PROPOSED", 42L, "BATCH"))
                .isInstanceOf(SimulationEngineException.class)
                .satisfies(e -> assertThat(((SimulationEngineException) e).isEngineReachable()).isTrue());
    }

    @Test
    void status_pythonUnreachable_throwsWithEngineReachableFalse() throws IOException {
        int deadPort = findClosedPort();

        assertThatThrownBy(() -> clientFor(deadPort).status())
                .isInstanceOf(SimulationEngineException.class)
                .satisfies(e -> assertThat(((SimulationEngineException) e).isEngineReachable()).isFalse());
    }

    private int findClosedPort() throws IOException {
        try (ServerSocket socket = new ServerSocket(0)) {
            return socket.getLocalPort(); // freed the instant this try-block exits — nothing listens on it
        }
    }

    private void respondJson(com.sun.net.httpserver.HttpExchange exchange, int status, String json) throws IOException {
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().add("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }
}
