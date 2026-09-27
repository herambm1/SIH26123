// dashboard/src/hooks/useSimulationControl.ts
// Owner: Member 4
//
// Owns scenario/mode/seed/speed selection and the real start/stop calls
// against POST /api/simulation/control, plus a status poll against
// GET /api/simulation/status (there is no push channel for status itself —
// only ROBOT_STATE_BATCH/SIMULATION_EVENT/METRIC_UPDATE go over /ws/live).
// Owns nothing about tick-by-tick robot data — see useLiveFeed for that.

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiRequestError, fetchSimulationStatus, startSimulation, stopSimulation } from '../api/client';
import type { SimulationMode, SimulationSpeed, SimulationStatus } from '../types/contracts';
import { SCENARIO_CATALOG } from '../data/scenarioCatalog';

const STATUS_POLL_MS = 1000;

export type BackendReachability = 'unknown' | 'reachable' | 'unreachable';
/**
 * Separate from BackendReachability on purpose — a runtime finding from the
 * Phase 4 integration check: GET /api/simulation/status returns HTTP 503
 * SIMULATION_ENGINE_ERROR when the Java backend itself is perfectly healthy
 * but the Python simulation engine is unreachable (confirmed live: Java
 * stayed up and returned a clear error body, exactly per this project's
 * documented resilience design). Collapsing that into "backend unreachable"
 * would misrepresent which half of the system is actually down.
 */
export type EngineReachability = 'unknown' | 'reachable' | 'unreachable';

export function useSimulationControl() {
  const [scenarioId, setScenarioId] = useState<string>(SCENARIO_CATALOG[0].scenarioId);
  const [mode, setMode] = useState<SimulationMode>('DECENTRALIZED_PROPOSED');
  const [seed, setSeed] = useState<number>(42);
  const [speed, setSpeed] = useState<SimulationSpeed>('LIVE');

  const [status, setStatus] = useState<SimulationStatus | null>(null);
  const [reachability, setReachability] = useState<BackendReachability>('unknown');
  const [engineReachability, setEngineReachability] = useState<EngineReachability>('unknown');
  const [actionError, setActionError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [stopping, setStopping] = useState(false);
  // Incremented on every successfully-ACKed start — the reliable "new run
  // began" signal useLiveFeed uses to reset its tick buffer (see that
  // hook's header comment for why the WS envelope's own tick field can't
  // be trusted for this alone).
  const [runGeneration, setRunGeneration] = useState(0);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const pollOnce = useCallback(async () => {
    try {
      const s = await fetchSimulationStatus();
      setStatus(s);
      setReachability('reachable');
      setEngineReachability('reachable');
    } catch (e) {
      if (e instanceof ApiRequestError && e.status > 0) {
        // The Java backend answered (even with an error status) — it is up.
        // status===0 means the fetch itself failed (network/CORS/refused).
        setReachability('reachable');
        setEngineReachability('unreachable');
        setStatus(null);
      } else {
        setReachability('unreachable');
        setEngineReachability('unknown');
        setStatus(null);
      }
      // Status polling failures are connectivity noise, not user-facing
      // action errors — surfaced only via the two reachability badges.
    }
  }, []);

  useEffect(() => {
    pollOnce();
    pollRef.current = setInterval(pollOnce, STATUS_POLL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [pollOnce]);

  const start = useCallback(async () => {
    setActionError(null);
    setStarting(true);
    try {
      await startSimulation({ scenarioId, mode, seed, speed });
      setRunGeneration((g) => g + 1);
      await pollOnce();
    } catch (e) {
      setActionError(e instanceof ApiRequestError ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  }, [scenarioId, mode, seed, speed, pollOnce]);

  const stop = useCallback(async () => {
    setActionError(null);
    setStopping(true);
    try {
      await stopSimulation();
      await pollOnce();
    } catch (e) {
      setActionError(e instanceof ApiRequestError ? e.message : String(e));
    } finally {
      setStopping(false);
    }
  }, [pollOnce]);

  return {
    // selection state
    scenarioId,
    setScenarioId,
    mode,
    setMode,
    seed,
    setSeed,
    speed,
    setSpeed,
    // run state
    status,
    reachability,
    engineReachability,
    actionError,
    starting,
    stopping,
    start,
    stop,
    runGeneration,
  };
}

export type SimulationControl = ReturnType<typeof useSimulationControl>;
