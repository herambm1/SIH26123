package com.sih26123.backend.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sih26123.backend.model.SimulationEventDto;
import com.sih26123.backend.repository.EventRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Collections;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class EventIngestControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private EventRepository eventRepository;

    @Test
    void ingestEvents_emptyArray_isValidAndAccepted() throws Exception {
        mockMvc.perform(post("/api/events")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("[]"))
                .andExpect(status().isOk());
    }

    @Test
    void ingestEvents_validEvent_isPersisted() throws Exception {
        SimulationEventDto event = new SimulationEventDto();
        event.eventId = "evt_test_1";
        event.type = "AISLE_BLOCKED";
        event.tick = 12;
        event.payload = Map.of("cell", "x=5,y=5");

        mockMvc.perform(post("/api/events")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(List.of(event))))
                .andExpect(status().isOk());

        assertThat(eventRepository.findById("evt_test_1")).isPresent();
        assertThat(eventRepository.findById("evt_test_1").get().getType()).isEqualTo("AISLE_BLOCKED");
    }

    @Test
    void ingestEvents_missingType_returns400() throws Exception {
        SimulationEventDto event = new SimulationEventDto();
        event.eventId = "evt_bad";
        event.tick = 1;
        event.payload = Collections.emptyMap();

        mockMvc.perform(post("/api/events")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(List.of(event))))
                .andExpect(status().isBadRequest());
    }
}
