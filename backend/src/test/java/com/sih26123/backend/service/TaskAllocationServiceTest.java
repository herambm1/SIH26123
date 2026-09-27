package com.sih26123.backend.service;

import com.sih26123.backend.entity.TaskEntity;
import com.sih26123.backend.model.PositionDto;
import com.sih26123.backend.model.RobotStateDto;
import com.sih26123.backend.model.TaskDto;
import com.sih26123.backend.repository.EventRepository;
import com.sih26123.backend.repository.TaskAssignmentRepository;
import com.sih26123.backend.repository.TaskRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * TaskAllocationService integration test — verifies the MVP requirement
 * from docs/06_BACKEND.md §15: "robot goes OFFLINE mid-task → task reassigned
 * to another idle robot", plus the basic greedy nearest-idle-robot heuristic.
 */
@SpringBootTest
@ActiveProfiles("test")
class TaskAllocationServiceTest {

    @Autowired
    private TaskAllocationService taskAllocationService;

    @Autowired
    private TaskRepository taskRepository;

    @Autowired
    private TaskAssignmentRepository taskAssignmentRepository;

    @Autowired
    private EventRepository eventRepository;

    @Autowired
    private RobotCacheService robotCacheService;

    private RobotStateDto idleRobot(String id, int x, int y) {
        RobotStateDto dto = new RobotStateDto();
        dto.robotId = id;
        dto.position = pos(x, y);
        dto.status = "IDLE";
        dto.battery = 100.0;
        dto.timestamp = 1;
        return dto;
    }

    private PositionDto pos(int x, int y) {
        PositionDto p = new PositionDto();
        p.x = x;
        p.y = y;
        return p;
    }

    @Test
    void allocatePendingTasks_assignsToNearestIdleRobot() {
        robotCacheService.upsert(idleRobot("TA_NEAR", 1, 1));
        robotCacheService.upsert(idleRobot("TA_FAR", 20, 20));

        TaskDto taskDto = new TaskDto();
        taskDto.taskId = "task_nearest_test";
        taskDto.pickupPosition = pos(2, 2); // much closer to TA_NEAR
        taskDto.dropPosition = pos(9, 9);
        taskDto.priority = 2;
        taskDto.status = "PENDING";
        taskDto.createdAtTick = 1;
        taskRepository.save(com.sih26123.backend.entity.TaskEntity.fromDto(taskDto));

        taskAllocationService.allocatePendingTasks();

        TaskEntity updated = taskRepository.findById("task_nearest_test").orElseThrow();
        assertThat(updated.getStatus()).isEqualTo("ASSIGNED");
        assertThat(taskAssignmentRepository.findFirstByTaskIdOrderByAssignedAtTickDescIdDesc("task_nearest_test"))
                .isPresent()
                .get()
                .extracting("robotId")
                .isEqualTo("TA_NEAR");
    }

    @Test
    void robotGoesOffline_taskReassignedToIdlePeer_andEventEmitted() {
        robotCacheService.upsert(idleRobot("TA_R1", 0, 0));
        robotCacheService.upsert(idleRobot("TA_R2", 5, 5));

        TaskDto taskDto = new TaskDto();
        taskDto.taskId = "task_reassign_test";
        taskDto.pickupPosition = pos(0, 1); // nearest to TA_R1
        taskDto.dropPosition = pos(9, 9);
        taskDto.priority = 3;
        taskDto.status = "PENDING";
        taskDto.createdAtTick = 1;
        taskRepository.save(com.sih26123.backend.entity.TaskEntity.fromDto(taskDto));

        taskAllocationService.allocatePendingTasks();
        assertThat(taskAssignmentRepository.findFirstByTaskIdOrderByAssignedAtTickDescIdDesc("task_reassign_test"))
                .get().extracting("robotId").isEqualTo("TA_R1");

        // TA_R1 now goes OFFLINE while holding the task.
        RobotStateDto offline = idleRobot("TA_R1", 0, 0);
        offline.status = "OFFLINE";
        robotCacheService.upsert(offline);

        taskAllocationService.handleRobotOffline("TA_R1");

        TaskEntity afterReassign = taskRepository.findById("task_reassign_test").orElseThrow();
        assertThat(afterReassign.getStatus()).isEqualTo("ASSIGNED");
        assertThat(taskAssignmentRepository.findFirstByTaskIdOrderByAssignedAtTickDescIdDesc("task_reassign_test"))
                .get().extracting("robotId").isEqualTo("TA_R2");

        assertThat(eventRepository.findAll())
                .anySatisfy(e -> assertThat(e.getType()).isEqualTo("TASK_REASSIGNED"));
    }

    @Test
    void handleRobotOffline_robotWithNoActiveTask_isNoOp() {
        // Must not throw for a robot that never held a task.
        taskAllocationService.handleRobotOffline("TA_NEVER_ASSIGNED");
    }
}
