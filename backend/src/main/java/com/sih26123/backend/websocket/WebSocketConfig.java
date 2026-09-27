package com.sih26123.backend.websocket;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

/**
 * WebSocketConfig — registers LiveUpdateWebSocketHandler at /ws/live.
 * Owner: Member 6
 *
 * setAllowedOrigins("*") — the dashboard dev server runs on a different port
 * (Vite, typically 5173) than the backend (8080); no auth is implemented
 * (explicitly out of MVP scope per docs/06_BACKEND.md §8.7), so this is a
 * deliberate, documented dev/demo choice rather than an oversight.
 */
@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

    private final LiveUpdateWebSocketHandler liveUpdateWebSocketHandler;

    public WebSocketConfig(LiveUpdateWebSocketHandler liveUpdateWebSocketHandler) {
        this.liveUpdateWebSocketHandler = liveUpdateWebSocketHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(liveUpdateWebSocketHandler, "/ws/live")
                .setAllowedOrigins("*");
    }
}
