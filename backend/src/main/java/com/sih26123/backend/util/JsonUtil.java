package com.sih26123.backend.util;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * JsonUtil — small static JSON helper for persistence-layer serialization
 * (e.g. storing currentPath / event payload as a TEXT column).
 * Owner: Member 6
 *
 * Kept as a static utility (not a Spring bean) so JPA entities can use it
 * without depending on dependency injection.
 */
public final class JsonUtil {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private JsonUtil() {
    }

    public static String toJson(Object value) {
        if (value == null) {
            return null;
        }
        try {
            return MAPPER.writeValueAsString(value);
        } catch (Exception e) {
            return null;
        }
    }

    public static <T> List<T> toListOrEmpty(String json, TypeReference<List<T>> typeRef) {
        if (json == null || json.isBlank()) {
            return Collections.emptyList();
        }
        try {
            return MAPPER.readValue(json, typeRef);
        } catch (Exception e) {
            return Collections.emptyList();
        }
    }

    public static Map<String, Object> toMapOrEmpty(String json) {
        if (json == null || json.isBlank()) {
            return Collections.emptyMap();
        }
        try {
            return MAPPER.readValue(json, new TypeReference<Map<String, Object>>() {
            });
        } catch (Exception e) {
            return Collections.emptyMap();
        }
    }
}
