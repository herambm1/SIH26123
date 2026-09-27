package com.sih26123.backend.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sih26123.backend.model.PerformanceMetricDto;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class MetricsControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    private PerformanceMetricDto metric(String runId, String scenarioId, String mode) {
        PerformanceMetricDto dto = new PerformanceMetricDto();
        dto.runId = runId;
        dto.scenarioId = scenarioId;
        dto.mode = mode;
        dto.totalCompletionTicks = 50;
        dto.avgCompletionTicks = 42.5;
        dto.collisionCount = 0;
        dto.deadlockCount = 1;
        dto.rerouteCount = 2;
        dto.idleTicksTotal = 5;
        dto.messageCount = 100;
        dto.seed = 42;
        return dto;
    }

    @Test
    void ingestMetric_thenFilterByScenarioId_returnsIt() throws Exception {
        mockMvc.perform(post("/api/metrics")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(metric("run_M1", "scn_metrics_test", "DECENTRALIZED_PROPOSED"))))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/metrics").param("scenarioId", "scn_metrics_test"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].runId").value("run_M1"))
                .andExpect(jsonPath("$[0].collisionCount").value(0));
    }

    @Test
    void ingestMetric_missingRunId_returns400() throws Exception {
        PerformanceMetricDto dto = metric(null, "scn_x", "STOP_AND_WAIT");
        mockMvc.perform(post("/api/metrics")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(dto)))
                .andExpect(status().isBadRequest());
    }
}
