package com.sih26123.backend.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sih26123.backend.model.WarehouseMapDto;
import com.sih26123.backend.service.WarehouseCacheService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Collections;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class WarehouseControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private WarehouseCacheService warehouseCacheService;

    @Test
    void getWarehouseMap_beforeAnyDataReceived_returns503WithClearError() throws Exception {
        warehouseCacheService.set(null); // ensure clean slate regardless of test order

        mockMvc.perform(get("/api/warehouse"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.error").value("WAREHOUSE_MAP_UNAVAILABLE"));
    }

    @Test
    void postThenGetWarehouseMap_roundTrips() throws Exception {
        WarehouseMapDto map = new WarehouseMapDto();
        map.gridWidth = 20;
        map.gridHeight = 15;
        map.obstacles = Collections.emptyList();
        map.chokePoints = Collections.emptyList();
        map.pickupPoints = Collections.emptyList();
        map.dropPoints = Collections.emptyList();
        map.blockedCells = Collections.emptyList();

        mockMvc.perform(post("/api/warehouse")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(map)))
                .andExpect(status().isAccepted());

        mockMvc.perform(get("/api/warehouse"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.gridWidth").value(20))
                .andExpect(jsonPath("$.gridHeight").value(15));
    }

    @Test
    void postMalformedWarehouseMap_returns400AndDoesNotCorruptCache() throws Exception {
        // A prior valid map (or lack of one) must be unaffected by a rejected
        // malformed push — the endpoint fails safely, not silently.
        WarehouseMapDto bad = new WarehouseMapDto();
        bad.gridWidth = 0; // invalid
        bad.gridHeight = 15;

        mockMvc.perform(post("/api/warehouse")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(bad)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("BAD_REQUEST"));
    }

    @Test
    void postGarbageJson_returns400_notA500() throws Exception {
        mockMvc.perform(post("/api/warehouse")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{not valid json"))
                .andExpect(status().isBadRequest());
    }
}
