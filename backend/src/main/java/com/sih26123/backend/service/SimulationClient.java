package com.sih26123.backend.service;

import com.sih26123.backend.model.PositionDto;
import com.sih26123.backend.model.RobotTaskAssignmentDto;
import com.sih26123.backend.model.SimulationStatusDto;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * SimulationClient — thin HTTP client for the Python FastAPI control server.
 * Owner: Member 6
 *
 * Default target: http://localhost:8001 (configurable via simulation.engine.url,
 * see application.properties). Calls the Python endpoints actually implemented
 * in simulation/runner.py (inspected directly, not assumed):
 *   POST /control/start  body: {scenarioId, mode, seed, speed}
 *   POST /control/stop
 *   GET  /control/status → {running, currentTick, scenarioId, mode}
 *
 * Never lets a Python failure propagate as an uncaught exception — every
 * failure is wrapped in SimulationEngineException so the controller layer can
 * return a clear error response instead of a 500/crash (docs/06_BACKEND.md §13).
 */
@Service
public class SimulationClient {

    private final RestClient restClient;

    public SimulationClient(
            @Value("${simulation.engine.url:http://localhost:8001}") String baseUrl,
            @Value("${simulation.engine.connect-timeout-ms:2000}") int connectTimeoutMs,
            @Value("${simulation.engine.read-timeout-ms:5000}") int readTimeoutMs
    ) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(connectTimeoutMs);
        factory.setReadTimeout(readTimeoutMs);
        this.restClient = RestClient.builder()
                .baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }

    /** POST Python /control/start with the given parameters, no task assignments. */
    public void start(String scenarioId, String mode, long seed, String speed) {
        start(scenarioId, mode, seed, speed, List.of());
    }

    /**
     * POST Python /control/start with the given parameters, plus the current
     * real Task/TaskAssignment data for whichever robots have one (from
     * TaskAllocationService.currentAssignmentsForSimulation()). Backward
     * compatible: an empty list produces the same body shape Python already
     * defaults to (task_assignments=None → every scenario robot uses its own
     * hardcoded start/goal, exactly as before this integration).
     */
    public void start(String scenarioId, String mode, long seed, String speed, List<RobotTaskAssignmentDto> assignments) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("scenarioId", scenarioId);
        body.put("mode", mode);
        body.put("seed", seed);
        body.put("speed", speed);
        body.put("taskAssignments", (assignments == null ? List.<RobotTaskAssignmentDto>of() : assignments).stream()
                .map(this::toPythonAssignment)
                .toList());
        try {
            restClient.post()
                    .uri("/control/start")
                    .body(body)
                    .retrieve()
                    .toBodilessEntity();
        } catch (RestClientException e) {
            throw wrap("start", e);
        }
    }

    private Map<String, Object> toPythonAssignment(RobotTaskAssignmentDto a) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("robotId", a.robotId);
        m.put("taskId", a.taskId);
        m.put("pickupPosition", a.pickupPosition == null ? null : Map.of("x", a.pickupPosition.x, "y", a.pickupPosition.y));
        m.put("dropPosition", a.dropPosition == null ? null : Map.of("x", a.dropPosition.x, "y", a.dropPosition.y));
        m.put("priority", a.priority);
        return m;
    }

    /** POST Python /control/stop. */
    public void stop() {
        try {
            restClient.post()
                    .uri("/control/stop")
                    .retrieve()
                    .toBodilessEntity();
        } catch (RestClientException e) {
            throw wrap("stop", e);
        }
    }

    // ── Product-mode calls (additive — none of the above are modified) ─────
    // Target the 4 new routes simulation/runner.py added in Phase 1
    // (inspected directly): /control/product/start, /control/product/stop,
    // /control/task, /control/inject. Reuses this same RestClient/wrap()
    // pattern, no new HTTP client, no new timeout config.

    /**
     * POST Python /control/product/start — starts a live Product-mode
     * session (simulation/product/session.py::ProductSession). Distinct
     * from a scenario start() above; shares the same single-run lock on
     * the Python side — a concurrent scenario run OR another product
     * session both surface as a rejected request here, exactly like
     * start() already does for a concurrent scenario run.
     *
     * seed: null lets Python pick a random one — always read the seed
     * actually used from the RETURNED map, never assume the caller's own
     * value was honored.
     * config: forwarded verbatim (e.g. {robotCount, maxTicks,
     * speedMultiplier}) — see ProductSession._run_inner for the keys it
     * reads; unrecognized/absent keys behave exactly as documented there.
     *
     * Returns Python's raw JSON response: {message, sessionId, seed}.
     */
    public Map<String, Object> startProduct(Long seed, String speed, Map<String, Object> config) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("seed", seed);
        body.put("speed", speed == null ? "BATCH" : speed);
        body.put("config", config == null ? Map.of() : config);
        try {
            return restClient.post()
                    .uri("/control/product/start")
                    .body(body)
                    .retrieve()
                    .body(new ParameterizedTypeReference<Map<String, Object>>() {
                    });
        } catch (RestClientException e) {
            throw wrap("product/start", e);
        }
    }

    /** POST Python /control/product/stop. */
    public void stopProduct() {
        try {
            restClient.post().uri("/control/product/stop").retrieve().toBodilessEntity();
        } catch (RestClientException e) {
            throw wrap("product/stop", e);
        }
    }

    /**
     * POST Python /control/task — pushes ONE real, current robot&lt;-&gt;task
     * assignment to a running product session. Same wire shape
     * toPythonAssignment(...) above already uses for the scenario
     * taskAssignments list ({robotId, taskId, pickupPosition, dropPosition,
     * priority}) — reused here, not reinvented — matching what
     * simulation/product/task_inbox.py::TaskInbox.submit_assignment
     * expects.
     */
    public void assignTask(String robotId, String taskId, PositionDto pickupPosition, PositionDto dropPosition, int priority) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("robotId", robotId);
        body.put("taskId", taskId);
        body.put("pickupPosition", pickupPosition == null ? null : Map.of("x", pickupPosition.x, "y", pickupPosition.y));
        body.put("dropPosition", dropPosition == null ? null : Map.of("x", dropPosition.x, "y", dropPosition.y));
        body.put("priority", priority);
        try {
            restClient.post().uri("/control/task").body(body).retrieve().toBodilessEntity();
        } catch (RestClientException e) {
            throw wrap("task", e);
        }
    }

    /**
     * POST Python /control/release — asks a running product session to
     * release ONE robot whose task Java has just abandoned as stalled
     * (see ProductSessionService.STALL_ABANDON_TICKS). Body {robotId,
     * taskId}; Python re-checks the robot is still on that task before
     * touching it, and reports the accept/ignore decision as a SYSTEM event —
     * a 200 here only means the request was queued.
     */
    public void releaseRobot(String robotId, String taskId) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("robotId", robotId);
        body.put("taskId", taskId);
        try {
            restClient.post().uri("/control/release").body(body).retrieve().toBodilessEntity();
        } catch (RestClientException e) {
            throw wrap("release", e);
        }
    }

    /**
     * POST Python /control/recover — asks a running product session to recover ONE broken-down (ROBOT_OFFLINE) robot
     * ("Mark as fixed"): clear its sensor fault and reset it to IDLE where it stopped. Body {robotId}. Python re-checks the
     * robot really is broken down and reports the accept/ignore decision as a SYSTEM event; a 200 here only means queued.
     */
    public void recoverRobot(String robotId) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("robotId", robotId);
        try {
            restClient.post().uri("/control/recover").body(body).retrieve().toBodilessEntity();
        } catch (RestClientException e) {
            throw wrap("recover", e);
        }
    }

    /**
     * POST Python /control/inject — a world-fault injection request for a
     * running product session. Returns Python's raw JSON response
     * ({"queued": true} on success) — the actual accept/reject decision
     * happens ASYNCHRONOUSLY inside Python's tick loop (cooldown, max
     * concurrent, real-planner feasibility guards) and is reported back as
     * a SYSTEM SimulationEvent on the normal event feed, NOT in this HTTP
     * response. Callers must not treat a 200 here as "the fault was
     * applied."
     */
    public Map<String, Object> injectProductFault(Map<String, Object> body) {
        try {
            return restClient.post()
                    .uri("/control/inject")
                    .body(body == null ? Map.of() : body)
                    .retrieve()
                    .body(new ParameterizedTypeReference<Map<String, Object>>() {
                    });
        } catch (RestClientException e) {
            throw wrap("inject", e);
        }
    }

    /** GET Python /control/status. */
    public SimulationStatusDto status() {
        try {
            return restClient.get()
                    .uri("/control/status")
                    .retrieve()
                    .body(SimulationStatusDto.class);
        } catch (RestClientException e) {
            throw wrap("status", e);
        }
    }

    private SimulationEngineException wrap(String action, RestClientException e) {
        if (e instanceof RestClientResponseException responseEx) {
            // Python WAS reachable and responded — just with an error status
            // (e.g. 400 "Simulation is already running.").
            String body = responseEx.getResponseBodyAsString();
            return new SimulationEngineException(
                    "Python simulation engine rejected " + action + " request ("
                            + responseEx.getStatusCode() + "): " + body,
                    true, e);
        }
        return new SimulationEngineException(
                "Python simulation engine is unreachable for " + action + " request: " + e.getMessage(),
                false, e);
    }
}
