package com.sih26123.backend.service;

/**
 * SimulationEngineException — thrown by SimulationClient when the Python
 * FastAPI control server is unreachable or returns an error response.
 * Owner: Member 6
 *
 * Caught at the controller layer and turned into a clear JSON error response
 * (never an uncaught 500 / crash) — see docs/06_BACKEND.md §13.
 */
public class SimulationEngineException extends RuntimeException {

    /** True if Python responded with an error status (e.g. "already running");
     *  false if Python could not be reached at all (connection refused/timeout). */
    private final boolean engineReachable;

    public SimulationEngineException(String message, boolean engineReachable, Throwable cause) {
        super(message, cause);
        this.engineReachable = engineReachable;
    }

    public boolean isEngineReachable() {
        return engineReachable;
    }
}
