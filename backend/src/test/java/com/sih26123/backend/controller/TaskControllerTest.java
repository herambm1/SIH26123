package com.sih26123.backend.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sih26123.backend.model.PositionDto;
import com.sih26123.backend.model.TaskDto;
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
class TaskControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    private TaskDto validTaskBody() {
        TaskDto dto = new TaskDto();
        dto.pickupPosition = pos(1, 1);
        dto.dropPosition = pos(9, 9);
        dto.priority = 3;
        return dto;
    }

    private PositionDto pos(int x, int y) {
        PositionDto p = new PositionDto();
        p.x = x;
        p.y = y;
        return p;
    }

    @Test
    void createTask_valid_returns201WithPendingStatus() throws Exception {
        mockMvc.perform(post("/api/tasks")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(validTaskBody())))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.taskId").exists())
                // No idle robot is registered in this test's cache, so it stays PENDING.
                .andExpect(jsonPath("$.status").value("PENDING"));
    }

    @Test
    void createTask_missingPickup_returns400() throws Exception {
        TaskDto dto = new TaskDto();
        dto.dropPosition = pos(9, 9);
        dto.priority = 2;

        mockMvc.perform(post("/api/tasks")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(dto)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("BAD_REQUEST"));
    }

    @Test
    void getTasks_includesCreatedTask() throws Exception {
        String body = mockMvc.perform(post("/api/tasks")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(validTaskBody())))
                .andReturn().getResponse().getContentAsString();
        TaskDto created = objectMapper.readValue(body, TaskDto.class);

        mockMvc.perform(get("/api/tasks"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.taskId=='" + created.taskId + "')]").exists());
    }
}
