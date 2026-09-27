package com.sih26123.backend.controller;

import com.sih26123.backend.entity.EventEntity;
import com.sih26123.backend.model.SimulationEventDto;
import com.sih26123.backend.repository.EventRepository;
import com.sih26123.backend.service.LiveUpdateBroadcaster;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.UUID;

/**
 * EventIngestController — receives SimulationEvent lists pushed by the
 * Python runner, and serves already-persisted events to the dashboard.
 * Owner: Member 6
 *
 * POST /api/events  body: SimulationEvent[]  — once per tick, may be empty.
 *   On receipt: persists each event and broadcasts a SIMULATION_EVENT frame
 *   per event to the dashboard alerts feed, in the same request. Semantics
 *   UNCHANGED by the addition below — this ingestion path was not touched.
 *
 * GET  /api/events?type=&limit=  → approved read-only addition "b-1"
 *   (Phase 5, frontend catch-up/history for the event timeline). Exposes
 *   already-persisted EventEntity rows, ordered by tick ascending, capped at
 *   `limit` (default 500, max 2000). NOTE — EventEntity carries no
 *   scenarioId/runId (confirmed during the Phase 1 frontend audit: no event
 *   ingested anywhere is tagged with which run produced it), so this cannot
 *   be scoped to "the current run" — it returns everything ever persisted,
 *   optionally filtered by type. The frontend treats this accordingly (a
 *   supplementary full log, not a per-run history) rather than presenting
 *   it as scoped to one run.
 */
@RestController
@RequestMapping("/api/events")
public class EventIngestController {

    private final EventRepository eventRepository;
    private final LiveUpdateBroadcaster broadcaster;

    public EventIngestController(EventRepository eventRepository, LiveUpdateBroadcaster broadcaster) {
        this.eventRepository = eventRepository;
        this.broadcaster = broadcaster;
    }

    @PostMapping
    public ResponseEntity<Void> ingestEvents(@RequestBody List<SimulationEventDto> events) {
        if (events == null) {
            throw new IllegalArgumentException("Events body must be a JSON array of SimulationEvent (may be empty).");
        }
        for (SimulationEventDto event : events) {
            if (event == null) {
                throw new IllegalArgumentException("Events array contains a null entry.");
            }
            if (event.type == null || event.type.isBlank()) {
                throw new IllegalArgumentException("SimulationEvent.type is required.");
            }
            if (event.eventId == null || event.eventId.isBlank()) {
                event.eventId = "evt_" + UUID.randomUUID();
            }
            eventRepository.save(EventEntity.fromDto(event));
            broadcaster.broadcastEvent(event.tick, event);
        }
        return ResponseEntity.ok().build();
    }

    @GetMapping
    public ResponseEntity<List<SimulationEventDto>> getEvents(
            @RequestParam(required = false) String type,
            @RequestParam(required = false, defaultValue = "500") int limit) {
        Pageable page = PageRequest.of(0, Math.max(1, Math.min(limit, 2000)), Sort.by("tick").ascending());
        Page<EventEntity> result = (type == null || type.isBlank())
                ? eventRepository.findAll(page)
                : eventRepository.findByType(type, page);
        return ResponseEntity.ok(result.getContent().stream().map(EventEntity::toDto).toList());
    }
}
