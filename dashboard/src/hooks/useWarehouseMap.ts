// dashboard/src/hooks/useWarehouseMap.ts
// Owner: Member 4
//
// GET /api/warehouse, refetched whenever the active scenarioId changes.
// A scenario's map is static and identical across runs/seeds, so refetching
// on every status poll would be wasted work — refetching on scenarioId
// change is sufficient and still always reflects the real backend cache.
// A 503 (no run has pushed a map yet) is a genuine, real "not started"
// state, not an error — see fetchWarehouseMap in api/client.ts.

import { useEffect, useState } from 'react';
import { fetchWarehouseMap, ApiRequestError } from '../api/client';
import type { WarehouseMap } from '../types/contracts';

export function useWarehouseMap(scenarioId: string | null | undefined) {
  const [map, setMap] = useState<WarehouseMap | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchWarehouseMap()
      .then((m) => {
        if (cancelled) return;
        setMap(m);
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof ApiRequestError ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [scenarioId]);

  return { map, loading, error };
}
