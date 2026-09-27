// dashboard/src/hooks/useProductSession.ts
//
// Owns the Product tab's session lifecycle against the Java backend only: a 1 s status poll of GET /api/product/session (task
// counters + the broken-down overlay), RANDOMIZE & START, STOP, and "Mark as fixed". Robot positions and events do NOT come from
// here — they come over /ws/live via the existing useLiveFeed (see ProductView), reset with `generation`.

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiRequestError } from '../api/client';
import { fetchProductSession, fixProductRobot, startProductSession, stopProductSession } from '../api/productApi';
import type { ProductSessionStatus, ProductSpeedMultiplier } from '../types/product';

const POLL_MS = 1000;
const START_RETRIES = 10; // Python may still be finishing the previous session's last tick when we stop-then-start
const START_RETRY_MS = 500;

export type ProductBackend = 'unknown' | 'reachable' | 'unreachable';

function message(e: unknown): string {
  return e instanceof ApiRequestError || e instanceof Error ? e.message : String(e);
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function useProductSession() {
  const [status, setStatus] = useState<ProductSessionStatus | null>(null);
  const [backend, setBackend] = useState<ProductBackend>('unknown');
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [fixing, setFixing] = useState<Set<string>>(new Set());
  const [fixError, setFixError] = useState<string | null>(null);
  // Incremented when a new session is started: the reliable "new session" signal useLiveFeed resets its buffers on.
  const [generation, setGeneration] = useState(0);
  const unmounted = useRef(false);

  const poll = useCallback(async () => {
    try {
      const s = await fetchProductSession();
      if (unmounted.current) return;
      setStatus(s);
      setBackend('reachable');
    } catch (e) {
      if (unmounted.current) return;
      setBackend(e instanceof ApiRequestError && e.status > 0 ? 'reachable' : 'unreachable');
    }
  }, []);

  useEffect(() => {
    unmounted.current = false;
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => {
      unmounted.current = true;
      clearInterval(id);
    };
  }, [poll]);

  /** RANDOMIZE & START: a fresh random seed, replacing any session that is already running. */
  const randomizeAndStart = useCallback(
    async (speedMultiplier: ProductSpeedMultiplier) => {
      setError(null);
      setFixError(null);
      setStarting(true);
      try {
        if (status?.running) {
          await stopProductSession();
        }
        setGeneration((g) => g + 1); // clear the previous session's map frames and events straight away
        const seed = Math.floor(Math.random() * 2_147_483_646) + 1;
        let lastErr: unknown = null;
        for (let attempt = 0; attempt < START_RETRIES; attempt++) {
          try {
            const ack = await startProductSession(seed, speedMultiplier);
            setGeneration((g) => g + 1);
            await poll();
            return ack;
          } catch (e) {
            lastErr = e;
            const msg = message(e).toLowerCase();
            if (!msg.includes('already running')) break;
            await sleep(START_RETRY_MS);
          }
        }
        throw lastErr;
      } catch (e) {
        setError(message(e));
        return null;
      } finally {
        setStarting(false);
      }
    },
    [status?.running, poll],
  );

  const stop = useCallback(async () => {
    setError(null);
    setStopping(true);
    try {
      await stopProductSession();
      await poll();
    } catch (e) {
      setError(message(e));
    } finally {
      setStopping(false);
    }
  }, [poll]);

  /** "Mark as fixed" for a broken-down robot. */
  const fixRobot = useCallback(
    async (robotId: string) => {
      setFixError(null);
      setFixing((prev) => new Set(prev).add(robotId));
      try {
        await fixProductRobot(robotId);
        await poll();
      } catch (e) {
        setFixError(`${robotId}: ${message(e)}`);
      } finally {
        setFixing((prev) => {
          const next = new Set(prev);
          next.delete(robotId);
          return next;
        });
      }
    },
    [poll],
  );

  return { status, backend, error, starting, stopping, fixing, fixError, generation, randomizeAndStart, stop, fixRobot };
}

export type ProductSession = ReturnType<typeof useProductSession>;
