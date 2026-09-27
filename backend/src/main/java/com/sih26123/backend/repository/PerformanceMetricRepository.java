package com.sih26123.backend.repository;

import com.sih26123.backend.entity.PerformanceMetricEntity;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/** Owner: Member 6 */
public interface PerformanceMetricRepository extends JpaRepository<PerformanceMetricEntity, String> {

    List<PerformanceMetricEntity> findByScenarioId(String scenarioId);
}
