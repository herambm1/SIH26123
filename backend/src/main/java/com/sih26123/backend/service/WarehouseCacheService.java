package com.sih26123.backend.service;

import com.sih26123.backend.model.WarehouseMapDto;
import org.springframework.stereotype.Service;

import java.util.concurrent.atomic.AtomicReference;

/**
 * WarehouseCacheService — holds the WarehouseMap fetched once at run start.
 * Owner: Member 6
 *
 * IMPORTANT — cross-module gap (see final report): docs/06_BACKEND.md §8.6/§14
 * says the map should be "fetched once from Python at run start, cached", but
 * simulation/runner.py (inspected directly) exposes only /control/start,
 * /control/stop, /control/status — there is no endpoint to fetch or push a
 * WarehouseMap. Per this task's explicit instruction not to invent an
 * undocumented Python endpoint, this cache starts empty and is only populated
 * if/when something calls set(...) (e.g. via the POST /api/warehouse endpoint
 * added as the natural extension of the existing push-ingestion pattern, for
 * whenever Python-side support exists) — GET /api/warehouse reports a clear
 * 503 rather than fabricating placeholder map data.
 */
@Service
public class WarehouseCacheService {

    private final AtomicReference<WarehouseMapDto> cached = new AtomicReference<>();

    public void set(WarehouseMapDto map) {
        cached.set(map);
    }

    public WarehouseMapDto get() {
        return cached.get();
    }
}
