package com.sih26123.backend.repository;

import com.sih26123.backend.entity.TaskAssignmentEntity;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

/** Owner: Member 6 */
public interface TaskAssignmentRepository extends JpaRepository<TaskAssignmentEntity, Long> {

    // Tiebreak on id (insertion order) — assignedAtTick alone is not unique:
    // an initial allocation and an immediate reassignment can land on the same
    // simulation tick, and "ORDER BY assignedAtTick DESC" alone does not
    // guarantee returning the most recently inserted row in that case.
    List<TaskAssignmentEntity> findByTaskIdOrderByAssignedAtTickDescIdDesc(String taskId);

    Optional<TaskAssignmentEntity> findFirstByTaskIdOrderByAssignedAtTickDescIdDesc(String taskId);

    List<TaskAssignmentEntity> findByRobotId(String robotId);
}
