package com.sih26123.backend.controller;

import com.sih26123.backend.model.ApiErrorDto;
import com.sih26123.backend.service.SimulationEngineException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * GlobalExceptionHandler — uniform error responses across every controller.
 * Owner: Member 6
 *
 * Guarantees per docs/06_BACKEND.md §13:
 *   - malformed ingestion input → HTTP 400, never an uncaught 500
 *   - Python unreachable → a clear error response, backend stays alive
 *   - one bad request never affects subsequent requests (each is handled
 *     independently by Spring MVC's per-request exception dispatch)
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiErrorDto> handleBadRequest(IllegalArgumentException e) {
        return ResponseEntity.badRequest().body(new ApiErrorDto("BAD_REQUEST", e.getMessage()));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiErrorDto> handleMalformedJson(HttpMessageNotReadableException e) {
        return ResponseEntity.badRequest()
                .body(new ApiErrorDto("MALFORMED_REQUEST_BODY", "Request body could not be parsed as valid JSON."));
    }

    @ExceptionHandler(SimulationEngineException.class)
    public ResponseEntity<ApiErrorDto> handleSimulationEngineError(SimulationEngineException e) {
        HttpStatus status = e.isEngineReachable() ? HttpStatus.BAD_GATEWAY : HttpStatus.SERVICE_UNAVAILABLE;
        return ResponseEntity.status(status)
                .body(new ApiErrorDto("SIMULATION_ENGINE_ERROR", e.getMessage()));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiErrorDto> handleUnexpected(Exception e) {
        log.error("Unhandled exception in request", e);
        return ResponseEntity.internalServerError()
                .body(new ApiErrorDto("INTERNAL_ERROR", "An unexpected error occurred."));
    }
}
