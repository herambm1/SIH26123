package com.sih26123.backend.controller;

import com.sih26123.backend.service.ProductSessionService;
import com.sih26123.backend.service.SimulationClient;
import com.sih26123.backend.service.SimulationEngineException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** POST /api/product/robot/{robotId}/fix — HTTP contract only (the overlay logic itself is ProductSessionServiceBrokenDownTest). */
class ProductControllerFixTest {

    private ProductSessionService service;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        service = mock(ProductSessionService.class);
        mockMvc = MockMvcBuilders.standaloneSetup(new ProductController(service, mock(SimulationClient.class)))
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();
    }

    @Test
    void fix_success_returns200AndCallsTheService() throws Exception {
        mockMvc.perform(post("/api/product/robot/PR3/fix"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.robotId").value("PR3"));
        verify(service).fixRobot("PR3");
    }

    @Test
    void fix_notBrokenDownOrNoSession_returns400() throws Exception {
        doThrow(new IllegalArgumentException("Robot 'PR3' is not broken down.")).when(service).fixRobot("PR3");
        mockMvc.perform(post("/api/product/robot/PR3/fix"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value("Robot 'PR3' is not broken down."));
    }

    @Test
    void fix_pythonUnreachable_returns503() throws Exception {
        doThrow(new SimulationEngineException("engine down", false, null)).when(service).fixRobot("PR3");
        mockMvc.perform(post("/api/product/robot/PR3/fix")).andExpect(status().isServiceUnavailable());
    }
}
