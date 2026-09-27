package com.sih26123.backend.model;

import java.time.Instant;

/**
 * ApiErrorDto — uniform JSON error body for every non-2xx response this
 * backend returns (validation failures, unreachable Python engine, unknown
 * robot IDs, uncaught exceptions). Owner: Member 6
 */
public class ApiErrorDto {
    public String error;
    public String message;
    public Instant timestamp = Instant.now();

    public ApiErrorDto() {
    }

    public ApiErrorDto(String error, String message) {
        this.error = error;
        this.message = message;
    }
}
