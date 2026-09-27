package com.sih26123.backend.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * CorsConfig — allows the dashboard's dev server (a different origin/port,
 * e.g. Vite on :5173) to call this backend's REST API. Owner: Member 6
 *
 * No authentication is implemented (explicitly out of MVP scope per
 * docs/06_BACKEND.md §8.7), so a permissive dev/demo CORS policy is a
 * deliberate, documented choice rather than an oversight.
 */
@Configuration
public class CorsConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOriginPatterns("*")
                .allowedMethods("GET", "POST", "PUT", "DELETE", "OPTIONS")
                .allowedHeaders("*");
    }
}
