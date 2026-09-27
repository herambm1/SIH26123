package com.sih26123.backend.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sih26123.backend.model.PositionDto;
import com.sih26123.backend.model.RobotStateDto;
import com.sih26123.backend.repository.RobotRepository;
import com.sih26123.backend.service.RobotCacheService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class TelemetryIngestControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private RobotCacheService robotCacheService;

    @Autowired
    private RobotRepository robotRepository;

    private RobotStateDto state(String robotId, String status, int timestamp) {
        RobotStateDto dto = new RobotStateDto();
        dto.robotId = robotId;
        dto.position = new PositionDto();
        dto.position.x = 1;
        dto.position.y = 2;
        dto.velocity = 1.0;
        dto.battery = 95.0;
        dto.status = status;
        dto.timestamp = timestamp;
        return dto;
    }

    @Test
    void ingestBatch_updatesCacheAndPersists() throws Exception {
        RobotStateDto s = state("TEL_R1", "MOVING", 3);

        mockMvc.perform(post("/api/telemetry/batch")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(List.of(s))))
                .andExpect(status().isOk());

        assertThat(robotCacheService.get("TEL_R1")).isPresent();
        assertThat(robotCacheService.get("TEL_R1").get().status).isEqualTo("MOVING");
        assertThat(robotRepository.findById("TEL_R1")).isPresent();
    }

    @Test
    void ingestBatch_missingRobotId_returns400_andDoesNotAffectSubsequentRequests() throws Exception {
        RobotStateDto bad = state(null, "MOVING", 1);

        mockMvc.perform(post("/api/telemetry/batch")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(List.of(bad))))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("BAD_REQUEST"));

        // A subsequent valid request must still succeed — one bad batch must not
        // take down the ingestion endpoint (docs/06_BACKEND.md §13).
        RobotStateDto good = state("TEL_R2", "IDLE", 1);
        mockMvc.perform(post("/api/telemetry/batch")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(List.of(good))))
                .andExpect(status().isOk());
        assertThat(robotCacheService.get("TEL_R2")).isPresent();
    }

    @Test
    void ingestBatch_malformedJson_returns400NotUncaughtException() throws Exception {
        mockMvc.perform(post("/api/telemetry/batch")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{ this is not valid json"))
                .andExpect(status().isBadRequest());
    }
}
