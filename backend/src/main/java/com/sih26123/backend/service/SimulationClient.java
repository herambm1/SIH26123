package com.sih26123.backend.service;

/**
 * SimulationClient — thin HTTP client for the Python FastAPI control server.
 * Owner: Member 6
 *
 * Default target: http://localhost:8001 (configurable via simulation.engine.url)
 *
 * Implementation: Member 6's responsibility.
 */
public class SimulationClient {

    /**
     * POST to Python /control/start with the given parameters.
     * Implementation: Member 6's responsibility.
     */
    public void start(String scenarioId, String mode, long seed, String speed) {
        // POST Python /control/start
        throw new UnsupportedOperationException("Not implemented");
    }

    /**
     * POST to Python /control/stop.
     * Implementation: Member 6's responsibility.
     */
    public void stop() {
        // POST Python /control/stop
        throw new UnsupportedOperationException("Not implemented");
    }

    /**
     * GET Python /control/status.
     * Implementation: Member 6's responsibility.
     */
    public Object status() {
        // GET Python /control/status
        throw new UnsupportedOperationException("Not implemented");
    }
}
