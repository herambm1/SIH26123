package com.sih26123.backend.entity;

import com.sih26123.backend.model.SimulationEventDto;
import com.sih26123.backend.util.JsonUtil;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;

import java.time.Instant;

/**
 * EventEntity — mirrors shared/python/models.py SimulationEvent. Owner: Member 6
 */
@Entity
@Table(name = "events")
public class EventEntity {

    @Id
    @Column(name = "event_id")
    private String eventId;

    private String type;
    private int tick;

    @Lob
    @Column(name = "payload_json")
    private String payloadJson;

    @Column(name = "recorded_at")
    private Instant recordedAt;

    public EventEntity() {
    }

    public static EventEntity fromDto(SimulationEventDto dto) {
        EventEntity e = new EventEntity();
        e.eventId = dto.eventId;
        e.type = dto.type;
        e.tick = dto.tick;
        e.payloadJson = JsonUtil.toJson(dto.payload);
        e.recordedAt = Instant.now();
        return e;
    }

    public SimulationEventDto toDto() {
        SimulationEventDto dto = new SimulationEventDto();
        dto.eventId = this.eventId;
        dto.type = this.type;
        dto.tick = this.tick;
        dto.payload = JsonUtil.toMapOrEmpty(this.payloadJson);
        return dto;
    }

    public String getEventId() {
        return eventId;
    }

    public String getType() {
        return type;
    }

    public int getTick() {
        return tick;
    }
}
