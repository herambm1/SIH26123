package com.sih26123.backend.service;

import com.sih26123.backend.entity.TaskEntity;
import com.sih26123.backend.model.PositionDto;
import com.sih26123.backend.model.RobotStateDto;
import com.sih26123.backend.model.TaskDto;
import com.sih26123.backend.repository.EventRepository;
import com.sih26123.backend.repository.TaskAssignmentRepository;
import com.sih26123.backend.repository.TaskRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * prepareNewSession(): what must be cleaned up before a second product session starts in the same backend process (the
 * Product tab's RANDOMIZE &amp; START starts sessions back to back).
 */
class ProductSessionServicePrepareTest {

    private TaskRepository taskRepository;
    private RobotCacheService robotCache;
    private ProductSessionService service;

    @BeforeEach
    void setUp() {
        taskRepository = mock(TaskRepository.class);
        robotCache = new RobotCacheService();
        service = new ProductSessionService(taskRepository, mock(TaskAssignmentRepository.class), robotCache,
                mock(WarehouseCacheService.class), mock(TaskAllocationService.class), mock(EventRepository.class),
                mock(LiveUpdateBroadcaster.class), mock(SimulationClient.class));
    }

    private static TaskEntity task(String id, String status) {
        TaskDto dto = new TaskDto();
        dto.taskId = id;
        dto.pickupPosition = new PositionDto();
        dto.dropPosition = new PositionDto();
        dto.priority = 1;
        dto.status = status;
        return TaskEntity.fromDto(dto);
    }

    @Test
    void resetsTheRobotCacheAndItsTickCounter() {
        RobotStateDto r = new RobotStateDto();
        r.robotId = "PR1";
        r.status = "IDLE";
        r.timestamp = 768;
        robotCache.upsert(r);
        assertThat(robotCache.lastTick()).isEqualTo(768);

        service.prepareNewSession();

        assertThat(robotCache.lastTick()).isZero();
        assertThat(robotCache.getAll()).isEmpty();
    }

    @Test
    void marksLeftoverProductTasksFailed_butNeverOtherTasks() {
        TaskEntity leftoverAssigned = task("task_product_1790_a1_3", "ASSIGNED");
        TaskEntity leftoverInProgress = task("task_product_1790_a1_4", "IN_PROGRESS");
        TaskEntity leftoverPending = task("task_product_1790_a1_5", "PENDING");
        TaskEntity manualTask = task("task_manual_9", "ASSIGNED"); // created through POST /api/tasks, not a product task
        when(taskRepository.findByStatus("ASSIGNED")).thenReturn(List.of(leftoverAssigned, manualTask));
        when(taskRepository.findByStatus("IN_PROGRESS")).thenReturn(List.of(leftoverInProgress));
        when(taskRepository.findByStatus("PENDING")).thenReturn(List.of(leftoverPending));

        service.prepareNewSession();

        assertThat(leftoverAssigned.getStatus()).isEqualTo("FAILED");
        assertThat(leftoverInProgress.getStatus()).isEqualTo("FAILED");
        assertThat(leftoverPending.getStatus()).isEqualTo("FAILED");
        assertThat(manualTask.getStatus()).isEqualTo("ASSIGNED");
        verify(taskRepository, never()).save(manualTask);
        verify(taskRepository).save(leftoverAssigned);
    }

    @Test
    void withNothingLeftOverItOnlyResetsTheCache() {
        when(taskRepository.findByStatus(any())).thenReturn(List.of());
        service.prepareNewSession();
        verify(taskRepository, never()).save(any());
    }
}
