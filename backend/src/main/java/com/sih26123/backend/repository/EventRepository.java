package com.sih26123.backend.repository;

import com.sih26123.backend.entity.EventEntity;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

/**
 * Owner: Member 6
 *
 * findByType added for GET /api/events (approved addition "b-1", Phase 5) —
 * a read-only exposure of already-persisted rows, ordered by the Pageable's
 * Sort (tick ascending, applied by the controller). No new write path, no
 * change to what ingestEvents() stores.
 */
public interface EventRepository extends JpaRepository<EventEntity, String> {
    Page<EventEntity> findByType(String type, Pageable pageable);
}
