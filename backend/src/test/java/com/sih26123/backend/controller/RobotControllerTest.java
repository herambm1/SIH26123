package com.sih26123.backend.controller;

import com.sih26123.backend.model.PositionDto;
import com.sih26123.backend.model.RobotStateDto;
import com.sih26123.backend.service.RobotCacheService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class RobotControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private RobotCacheService robotCacheService;

    private RobotStateDto sampleState(String robotId) {
        RobotStateDto dto = new RobotStateDto();
        dto.robotId = robotId;
        dto.position = new PositionDto();
        dto.position.x = 3;
        dto.position.y = 4;
        dto.velocity = 1.0;
        dto.battery = 80.0;
        dto.status = "MOVING";
        dto.timestamp = 7;
        return dto;
    }

    @Test
    void getRobots_returnsCachedStates() throws Exception {
        robotCacheService.upsert(sampleState("RC_TEST_1"));

        mockMvc.perform(get("/api/robots"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.robotId=='RC_TEST_1')]").exists());
    }

    @Test
    void getRobotById_knownRobot_returnsState() throws Exception {
        robotCacheService.upsert(sampleState("RC_TEST_2"));

        mockMvc.perform(get("/api/robots/RC_TEST_2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.robotId").value("RC_TEST_2"))
                .andExpect(jsonPath("$.status").value("MOVING"))
                .andExpect(jsonPath("$.position.x").value(3));
    }

    @Test
    void getRobotById_unknownRobot_returns404WithClearBody() throws Exception {
        mockMvc.perform(get("/api/robots/DOES_NOT_EXIST"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").value("ROBOT_NOT_FOUND"))
                .andExpect(jsonPath("$.message").exists());
    }
}
