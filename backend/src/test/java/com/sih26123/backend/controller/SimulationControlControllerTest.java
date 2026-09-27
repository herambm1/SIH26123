package com.sih26123.backend.controller;

import com.sih26123.backend.entity.TaskAssignmentEntity;
import com.sih26123.backend.entity.TaskEntity;
import com.sih26123.backend.model.PositionDto;
import com.sih26123.backend.model.RobotTaskAssignmentDto;
import com.sih26123.backend.model.SimulationStatusDto;
import com.sih26123.backend.model.TaskDto;
import com.sih26123.backend.repository.TaskAssignmentRepository;
import com.sih26123.backend.repository.TaskRepository;
import com.sih26123.backend.service.SimulationClient;
import com.sih26123.backend.service.SimulationEngineException;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * Exercises /api/simulation/control and /api/simulation/status with a mocked
 * SimulationClient — SimulationClient's own HTTP behavior is covered by
 * SimulationClientTest against a real local mock server.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class SimulationControlControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private TaskRepository taskRepository;

    @Autowired
    private TaskAssignmentRepository taskAssignmentRepository;

    @MockBean
    private SimulationClient simulationClient;

    private PositionDto pos(int x, int y) {
        PositionDto p = new PositionDto();
        p.x = x;
        p.y = y;
        return p;
    }

    @Test
    void controlStart_valid_delegatesToSimulationClient() throws Exception {
        // No ASSIGNED/IN_PROGRESS task anywhere → the assignments list the
        // controller now always passes through must be empty. Explicitly
        // cleared rather than assumed, since other test classes in this
        // shared Spring context create tasks of their own.
        taskAssignmentRepository.deleteAll();
        taskRepository.deleteAll();

        mockMvc.perform(post("/api/simulation/control")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"action\":\"start\",\"scenarioId\":\"a_normal\",\"mode\":\"DECENTRALIZED_PROPOSED\",\"seed\":42,\"speed\":\"BATCH\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.runId").exists());

        verify(simulationClient).start("a_normal", "DECENTRALIZED_PROPOSED", 42L, "BATCH", List.of());
    }

    @Test
    void controlStart_withActiveTaskAssignment_passesRealAssignmentToSimulationClient() throws Exception {
        taskAssignmentRepository.deleteAll();
        taskRepository.deleteAll();

        String taskId = "scc_task_" + UUID.randomUUID();
        TaskDto taskDto = new TaskDto();
        taskDto.taskId = taskId;
        taskDto.pickupPosition = pos(1, 1);
        taskDto.dropPosition = pos(9, 9);
        taskDto.priority = 4;
        taskDto.status = "ASSIGNED";
        taskDto.createdAtTick = 0;
        taskRepository.save(TaskEntity.fromDto(taskDto));
        taskAssignmentRepository.save(new TaskAssignmentEntity(taskId, "R1", 0, null));

        mockMvc.perform(post("/api/simulation/control")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"action\":\"start\",\"scenarioId\":\"a_normal\",\"mode\":\"DECENTRALIZED_PROPOSED\",\"seed\":42,\"speed\":\"BATCH\"}"))
                .andExpect(status().isOk());

        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<RobotTaskAssignmentDto>> captor = ArgumentCaptor.forClass(List.class);
        verify(simulationClient).start(eq("a_normal"), eq("DECENTRALIZED_PROPOSED"), eq(42L), eq("BATCH"), captor.capture());

        List<RobotTaskAssignmentDto> sent = captor.getValue();
        assertThat(sent).hasSize(1);
        assertThat(sent.get(0).robotId).isEqualTo("R1");
        assertThat(sent.get(0).taskId).isEqualTo(taskId);
        assertThat(sent.get(0).dropPosition.x).isEqualTo(9);
        assertThat(sent.get(0).dropPosition.y).isEqualTo(9);
        assertThat(sent.get(0).priority).isEqualTo(4);
    }

    @Test
    void controlStop_delegatesToSimulationClient() throws Exception {
        mockMvc.perform(post("/api/simulation/control")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"action\":\"stop\"}"))
                .andExpect(status().isOk());

        verify(simulationClient).stop();
    }

    @Test
    void control_unknownAction_returns400() throws Exception {
        mockMvc.perform(post("/api/simulation/control")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"action\":\"pause\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void controlStart_pythonUnreachable_returns503AndBackendStaysAlive() throws Exception {
        doThrow(new SimulationEngineException("connection refused", false, new RuntimeException()))
                .when(simulationClient).start(anyString(), anyString(), anyLong(), anyString(), anyList());

        mockMvc.perform(post("/api/simulation/control")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"action\":\"start\",\"scenarioId\":\"a_normal\"}"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.error").value("SIMULATION_ENGINE_ERROR"));

        // Backend itself must still be alive and serving other endpoints.
        mockMvc.perform(get("/api/robots")).andExpect(status().isOk());
    }

    @Test
    void controlStart_pythonRejects_returns502() throws Exception {
        doThrow(new SimulationEngineException("already running", true, new RuntimeException()))
                .when(simulationClient).start(anyString(), anyString(), anyLong(), anyString(), anyList());

        mockMvc.perform(post("/api/simulation/control")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"action\":\"start\",\"scenarioId\":\"a_normal\"}"))
                .andExpect(status().isBadGateway());
    }

    @Test
    void status_delegatesToSimulationClient() throws Exception {
        when(simulationClient.status()).thenReturn(new SimulationStatusDto(true, 17, "a_normal", "DECENTRALIZED_PROPOSED"));

        mockMvc.perform(get("/api/simulation/status"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.running").value(true))
                .andExpect(jsonPath("$.currentTick").value(17));
    }
}
