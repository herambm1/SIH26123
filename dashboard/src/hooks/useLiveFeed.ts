// dashboard/src/hooks/useLiveFeed.ts
// Owner: Member 4
//
// Owns the /ws/live WebSocket connection lifecycle and the client-side tick
// buffer that makes playback possible at all — per the Phase 1 audit, there
// is NO backend mechanism to replay a completed run's history, so this
// buffer IS the only history that will ever exist, built strictly from
// frames actually received while connected.
//
// Playback contract (do not weaken):
//   - scrubTo() only accepts a tick already present in the buffer (backward
//     scrubbing through received data only).
//   - it is IMPOSSIBLE to move past the highest tick actually received —
//     there is nothing to jump forward into.
//   - positions are rendered exactly as received for the displayed tick;
//     no interpolation is computed anywhere in this hook or its consumers.
//
// A new run is detected two ways, deliberately redundant:
//   1. `resetKey` — the caller (App.tsx) increments this on every
//      successfully-acknowledged POST /api/simulation/control start. This
//      is the PRIMARY, reliable signal.
//   2. A fresh tick===1 frame arriving while the buffer already holds a
//      later tick — SimulationRunner.run()'s tick loop always starts at 1
//      (simulation/runner.py: `for tick in range(1, ...)`).
// #2 alone is NOT sufficient: a real backend limitation was found during
// Phase 4 integration testing — RobotCacheService.lastTick() is a single
// AtomicInteger that only ever increases and is never reset between runs,
// so TelemetryIngestController's broadcast `tick` field (Math.max(lastTick,
// state.timestamp)) can stay pinned at a PRIOR run's higher tick value for
// the entire duration of a shorter subsequent run — it may never actually
// report 1. Confirmed live: starting b_intersection (max_ticks=40) right
// after a_normal had already reached tick 40 caused every b_intersection
// frame's envelope `tick` to read 40 even as real positions changed
// underneath it. #1 (resetKey) is what actually makes reset reliable; #2 is
// kept only as a harmless secondary guard for the case resetKey isn't wired
// by a caller. See the Phase 4 report for the full trace — NOT fixed here
// (a backend change, out of this hook's scope without separate approval).
//
// SECOND backend limitation, found during Phase 5 integration testing:
// simulation/runner.py's tick loop pushes the ENTIRE accumulated
// self.events list to POST /api/events every tick (it is only ever reset at
// the start of run(), never after a push) — so EventIngestController
// re-saves and RE-BROADCASTS every event that has ever occurred in the run
// again on every subsequent tick, not once. Confirmed by source inspection
// (simulation/runner.py, step 5 of the tick loop: `if self.events:
// self._push_to_backend(...)` with no clearing afterward). Left UNCHANGED
// per instruction — not one of the two approved backend additions — but it
// means a naive per-tick event append here would show the same event
// duplicated dozens of times as a run progresses. Handled below by keying
// the event buffer on the real, unique SimulationEvent.eventId and only
// ever inserting each id once — a frontend-only dedupe, not a change to
// what the backend sends.

import { useCallback, useEffect, useRef, useState } from 'react';
import { connectLiveFeed } from '../api/client';
import type { RobotState, SimulationEvent } from '../types/contracts';

export type WsConnectionStatus = 'connecting' | 'open' | 'reconnecting' | 'disconnected';

const BACKOFF_START_MS = 1000;
const BACKOFF_MAX_MS = 8000;

/**
 * @param resetKey change this value (e.g. a counter incremented on every
 *   successful simulation start) to force the tick buffer to clear — the
 *   reliable new-run signal, see the header comment above.
 */
export function useLiveFeed(resetKey?: number | string) {
  const [connectionStatus, setConnectionStatus] = useState<WsConnectionStatus>('connecting');
  const [robotBuffer, setRobotBuffer] = useState<Map<number, RobotState[]>>(new Map());
  // Keyed by the real, unique SimulationEvent.eventId — see the header
  // comment on why a naive tick-keyed append would duplicate every event
  // many times over (the backend re-broadcasts the whole event list every
  // tick). Each real event is stored exactly once, first-seen wins.
  const [eventsById, setEventsById] = useState<Map<string, SimulationEvent>>(new Map());
  const [scrubTick, setScrubTick] = useState<number | null>(null); // null = following live

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const backoffRef = useRef(BACKOFF_START_MS);
  const unmountedRef = useRef(false);

  const connect = useCallback(() => {
    if (unmountedRef.current) return;
    setConnectionStatus((prev) => (prev === 'open' ? prev : 'connecting'));

    const ws = connectLiveFeed(
      (msg) => {
        if (msg.type === 'ROBOT_STATE_BATCH') {
          setRobotBuffer((prev) => {
            const isNewRun = msg.tick === 1 && prev.size > 0 && Math.max(...prev.keys()) > 1;
            const next = isNewRun ? new Map<number, RobotState[]>() : new Map(prev);
            next.set(msg.tick, msg.payload);
            return next;
          });
          if (msg.tick === 1) {
            // A fresh run started — always resume following live, discard
            // any stale scrub position from the previous run.
            setScrubTick(null);
            setEventsById(new Map());
          }
        } else if (msg.type === 'SIMULATION_EVENT') {
          setEventsById((prev) => {
            if (prev.has(msg.payload.eventId)) return prev; // already recorded — the backend re-broadcasts it every tick
            const next = new Map(prev);
            next.set(msg.payload.eventId, msg.payload);
            return next;
          });
        }
        // METRIC_UPDATE is consumed by the Benchmark view (Phase 6), not here.
      },
      () => {
        backoffRef.current = BACKOFF_START_MS;
        setConnectionStatus('open');
      },
      () => {
        if (unmountedRef.current) return;
        setConnectionStatus('reconnecting');
        scheduleReconnect();
      },
      () => {
        // onerror — the subsequent onclose drives the actual reconnect.
      },
    );
    wsRef.current = ws;
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    reconnectTimerRef.current = setTimeout(() => {
      backoffRef.current = Math.min(backoffRef.current * 2, BACKOFF_MAX_MS);
      connect();
    }, backoffRef.current);
  }, [connect]);

  useEffect(() => {
    unmountedRef.current = false;
    connect();
    return () => {
      unmountedRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
      setConnectionStatus('disconnected');
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Primary new-run reset signal — see the header comment for why the
  // tick===1 heuristic alone is not reliable given a real backend limitation.
  const isFirstResetRef = useRef(true);
  useEffect(() => {
    if (isFirstResetRef.current) {
      isFirstResetRef.current = false;
      return;
    }
    setRobotBuffer(new Map());
    setEventsById(new Map());
    setScrubTick(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetKey]);

  const bufferedTicks = Array.from(robotBuffer.keys()).sort((a, b) => a - b);
  const minBufferedTick = bufferedTicks.length ? bufferedTicks[0] : null;
  const maxBufferedTick = bufferedTicks.length ? bufferedTicks[bufferedTicks.length - 1] : null;
  const isLive = scrubTick === null;
  const displayTick = isLive ? maxBufferedTick : scrubTick;
  const robotsAtDisplayTick = displayTick !== null ? (robotBuffer.get(displayTick) ?? []) : [];
  // Full tick-by-tick history buffered this run (ticks actually received
  // only, per the playback contract) — used by the d_deadlock narrative to
  // reconstruct real status transitions (approach -> WAITING -> resume)
  // across the whole run, not just the currently displayed tick.
  const robotHistory = bufferedTicks.map((tick) => ({ tick, robots: robotBuffer.get(tick) ?? [] }));

  // All real events received this run, deduplicated, sorted by tick — the
  // event timeline's primary source. eventsUpToDisplayTick additionally
  // scopes to "what has happened so far" for the currently displayed tick,
  // which is what a scrubbed/paused view should show (not future events
  // this connection happens to have already buffered).
  const allEvents = Array.from(eventsById.values()).sort((a, b) => a.tick - b.tick);
  const eventsUpToDisplayTick = displayTick !== null ? allEvents.filter((e) => e.tick <= displayTick) : [];
  const eventsAtDisplayTick = displayTick !== null ? allEvents.filter((e) => e.tick === displayTick) : [];

  const scrubTo = useCallback(
    (tick: number) => {
      if (minBufferedTick === null || maxBufferedTick === null) return;
      const clamped = Math.max(minBufferedTick, Math.min(tick, maxBufferedTick));
      setScrubTick(clamped === maxBufferedTick ? null : clamped);
    },
    [minBufferedTick, maxBufferedTick],
  );

  const stepBack = useCallback(() => {
    if (displayTick === null || minBufferedTick === null) return;
    const idx = bufferedTicks.indexOf(displayTick);
    if (idx > 0) setScrubTick(bufferedTicks[idx - 1]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [displayTick, bufferedTicks, minBufferedTick]);

  const stepForward = useCallback(() => {
    // Cannot exceed the highest tick actually received — there is nothing
    // to jump forward into, per the Phase 1 finding. Stepping forward past
    // the second-to-last buffered tick simply resumes following live.
    if (displayTick === null) return;
    const idx = bufferedTicks.indexOf(displayTick);
    if (idx === -1) return;
    if (idx >= bufferedTicks.length - 2) {
      setScrubTick(null); // resume live — already at (or one before) the latest
    } else {
      setScrubTick(bufferedTicks[idx + 1]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [displayTick, bufferedTicks]);

  const resumeLive = useCallback(() => setScrubTick(null), []);

  const pauseAtCurrent = useCallback(() => {
    if (maxBufferedTick !== null) setScrubTick(maxBufferedTick);
  }, [maxBufferedTick]);

  return {
    connectionStatus,
    minBufferedTick,
    maxBufferedTick,
    displayTick,
    isLive,
    robotsAtDisplayTick,
    robotHistory,
    allEvents,
    eventsUpToDisplayTick,
    eventsAtDisplayTick,
    bufferedTicks,
    scrubTo,
    stepBack,
    stepForward,
    resumeLive,
    pauseAtCurrent,
  };
}

export type LiveFeed = ReturnType<typeof useLiveFeed>;
