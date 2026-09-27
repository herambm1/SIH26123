package com.sih26123.backend.controller;

import com.sih26123.backend.entity.TaskEntity;
import com.sih26123.backend.model.TaskDto;
import com.sih26123.backend.repository.TaskRepository;
import com.sih26123.backend.service.RobotCacheService;
import com.sih26123.backend.service.TaskAllocationService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.UUID;

/**
 * TaskController — task creation and retrieval.
 * Owner: Member 6
 *
 * GET  /api/tasks  → list of Task
 * POST /api/tasks  → create a Task, status=PENDING, then attempt immediate
 *                    greedy allocation to any currently idle robot.
 */
@RestController
@RequestMapping("/api/tasks")
public class TaskController {

    private final TaskRepository taskRepository;
    private final TaskAllocationService taskAllocationService;
    private final RobotCacheService robotCacheService;

    public TaskController(TaskRepository taskRepository,
                           TaskAllocationService taskAllocationService,
                           RobotCacheService robotCacheService) {
        this.taskRepository = taskRepository;
        this.taskAllocationService = taskAllocationService;
        this.robotCacheService = robotCacheService;
    }

    @GetMapping
    public ResponseEntity<List<TaskDto>> getTasks() {
        List<TaskDto> tasks = taskRepository.findAll().stream().map(TaskEntity::toDto).toList();
        return ResponseEntity.ok(tasks);
    }

    @PostMapping
    public ResponseEntity<TaskDto> createTask(@RequestBody TaskDto body) {
        if (body == null || body.pickupPosition == null || body.dropPosition == null) {
            throw new IllegalArgumentException("pickupPosition and dropPosition are required to create a task.");
        }
        if (body.priority < 1 || body.priority > 5) {
            throw new IllegalArgumentException("priority must be between 1 and 5.");
        }

        TaskDto dto = new TaskDto();
        dto.taskId = (body.taskId == null || body.taskId.isBlank()) ? "task_" + UUID.randomUUID() : body.taskId;
        dto.pickupPosition = body.pickupPosition;
        dto.dropPosition = body.dropPosition;
        dto.priority = body.priority;
        dto.status = "PENDING";
        dto.createdAtTick = robotCacheService.lastTick();

        taskRepository.save(TaskEntity.fromDto(dto));
        taskAllocationService.allocatePendingTasks();

        // Re-read so the response reflects any allocation that just happened.
        TaskDto result = taskRepository.findById(dto.taskId).map(TaskEntity::toDto).orElse(dto);
        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }
}
