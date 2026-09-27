package com.sih26123.backend.service;

import com.sih26123.backend.entity.EventEntity;
import com.sih26123.backend.entity.TaskAssignmentEntity;
import com.sih26123.backend.entity.TaskEntity;
import com.sih26123.backend.model.PositionDto;
import com.sih26123.backend.model.RobotStateDto;
import com.sih26123.backend.model.RobotTaskAssignmentDto;
import com.sih26123.backend.model.SimulationEventDto;
import com.sih26123.backend.repository.EventRepository;
import com.sih26123.backend.repository.TaskAssignmentRepository;
import com.sih26123.backend.repository.TaskRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

/**
 * TaskAllocationService — greedy/nearest-idle-robot task assignment.
 * Owner: Member 6
 *
 * MVP policy only (docs/06_BACKEND.md §8.3): no Hungarian algorithm, no
 * optimization framework. "Idle"/"busy" is tracked entirely in this
 * backend's own database (TaskAssignmentEntity rows), independent of
 * RobotState.currentTaskId — see the final report's compatibility note on
 * why Task/TaskAssignment cannot currently be pushed into the Python engine.
 */
@Service
public class TaskAllocationService {

    private static final Logger log = LoggerFactory.getLogger(TaskAllocationService.class);
    private static final Set<String> ACTIVE_TASK_STATUSES = Set.of("ASSIGNED", "IN_PROGRESS");

    private final TaskRepository taskRepository;
    private final TaskAssignmentRepository taskAssignmentRepository;
    private final EventRepository eventRepository;
    private final RobotCacheService robotCacheService;
    private final LiveUpdateBroadcaster broadcaster;

    public TaskAllocationService(TaskRepository taskRepository,
                                  TaskAssignmentRepository taskAssignmentRepository,
                                  EventRepository eventRepository,
                                  RobotCacheService robotCacheService,
                                  LiveUpdateBroadcaster broadcaster) {
        this.taskRepository = taskRepository;
        this.taskAssignmentRepository = taskAssignmentRepository;
        this.eventRepository = eventRepository;
        this.robotCacheService = robotCacheService;
        this.broadcaster = broadcaster;
    }

    /** Attempt to assign any PENDING tasks to currently IDLE, unassigned robots. */
    public synchronized void allocatePendingTasks() {
        List<TaskEntity> pending = taskRepository.findByStatus("PENDING");
        if (pending.isEmpty()) {
            return;
        }
        Set<String> busy = new HashSet<>(currentlyBusyRobotIds());
        int tick = robotCacheService.lastTick();

        for (TaskEntity task : pending) {
            Optional<RobotStateDto> candidate = nearestIdleRobot(busy, task.getPickupPosition() == null
                    ? null : task.getPickupPosition().toDto());
            if (candidate.isEmpty()) {
                continue; // no idle robot available right now — stays PENDING
            }
            RobotStateDto robot = candidate.get();
            taskAssignmentRepository.save(new TaskAssignmentEntity(task.getTaskId(), robot.robotId, tick, null));
            task.setStatus("ASSIGNED");
            taskRepository.save(task);
            busy.add(robot.robotId);
            log.info("Task {} assigned to robot {} (greedy nearest-idle)", task.getTaskId(), robot.robotId);
        }
    }

    /**
     * Handle a robot going OFFLINE while holding an active task: reassign to
     * the next nearest idle robot and emit a TASK_REASSIGNED event. Idempotent
     * — a robot with no active task is a normal no-op, not an error.
     */
    public synchronized void handleRobotOffline(String offlineRobotId) {
        Optional<TaskEntity> activeTask = findActiveTaskForRobot(offlineRobotId);
        if (activeTask.isEmpty()) {
            return;
        }
        TaskEntity task = activeTask.get();
        int tick = robotCacheService.lastTick();

        Set<String> busy = new HashSet<>(currentlyBusyRobotIds());
        busy.add(offlineRobotId); // never reassign back to the robot that just went offline
        Optional<RobotStateDto> candidate = nearestIdleRobot(busy, task.getPickupPosition() == null
                ? null : task.getPickupPosition().toDto());

        if (candidate.isEmpty()) {
            // Nobody available right now — release it back to the pool rather
            // than leaving it permanently stuck on an offline robot.
            task.setStatus("PENDING");
            taskRepository.save(task);
            log.warn("Robot {} went OFFLINE holding task {}, but no idle robot is available for reassignment. "
                    + "Task released back to PENDING.", offlineRobotId, task.getTaskId());
            return;
        }

        RobotStateDto newRobot = candidate.get();
        taskAssignmentRepository.save(new TaskAssignmentEntity(task.getTaskId(), newRobot.robotId, tick, null));
        task.setStatus("ASSIGNED");
        taskRepository.save(task);

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("taskId", task.getTaskId());
        payload.put("fromRobotId", offlineRobotId);
        payload.put("toRobotId", newRobot.robotId);

        SimulationEventDto eventDto = new SimulationEventDto();
        eventDto.eventId = "evt_reassign_" + UUID.randomUUID();
        eventDto.type = "TASK_REASSIGNED";
        eventDto.tick = tick;
        eventDto.payload = payload;

        eventRepository.save(EventEntity.fromDto(eventDto));
        broadcaster.broadcastEvent(tick, eventDto);
        log.info("Task {} reassigned from OFFLINE robot {} to robot {}", task.getTaskId(), offlineRobotId, newRobot.robotId);
    }

    /**
     * The real, current robot&lt;-&gt;task assignments (ASSIGNED/IN_PROGRESS
     * only), shaped for Python's POST /control/start taskAssignments field —
     * this is what makes this service's centralized allocation actually
     * reach the decentralized simulation instead of staying backend-only
     * bookkeeping (see CLAUDE.md Known Integration Gaps #3, closed this
     * session). Called by SimulationControlController at run-start.
     */
    public synchronized List<RobotTaskAssignmentDto> currentAssignmentsForSimulation() {
        List<RobotTaskAssignmentDto> result = new ArrayList<>();
        List<TaskEntity> active = new ArrayList<>();
        active.addAll(taskRepository.findByStatus("ASSIGNED"));
        active.addAll(taskRepository.findByStatus("IN_PROGRESS"));
        for (TaskEntity task : active) {
            taskAssignmentRepository.findFirstByTaskIdOrderByAssignedAtTickDescIdDesc(task.getTaskId())
                    .ifPresent(assignment -> {
                        RobotTaskAssignmentDto dto = new RobotTaskAssignmentDto();
                        dto.robotId = assignment.getRobotId();
                        dto.taskId = task.getTaskId();
                        dto.pickupPosition = task.getPickupPosition() == null ? null : task.getPickupPosition().toDto();
                        dto.dropPosition = task.getDropPosition() == null ? null : task.getDropPosition().toDto();
                        dto.priority = task.getPriority();
                        result.add(dto);
                    });
        }
        return result;
    }

    private Optional<TaskEntity> findActiveTaskForRobot(String robotId) {
        List<TaskAssignmentEntity> assignmentsForRobot = taskAssignmentRepository.findByRobotId(robotId);
        for (TaskAssignmentEntity assignment : assignmentsForRobot) {
            // Only the CURRENT holder counts — a robot may appear in old,
            // superseded assignment rows for a task it no longer holds.
            boolean isCurrentHolder = taskAssignmentRepository
                    .findFirstByTaskIdOrderByAssignedAtTickDescIdDesc(assignment.getTaskId())
                    .map(latest -> latest.getRobotId().equals(robotId))
                    .orElse(false);
            if (!isCurrentHolder) {
                continue;
            }
            Optional<TaskEntity> task = taskRepository.findById(assignment.getTaskId());
            if (task.isPresent() && ACTIVE_TASK_STATUSES.contains(task.get().getStatus())) {
                return task;
            }
        }
        return Optional.empty();
    }

    private Set<String> currentlyBusyRobotIds() {
        Set<String> busy = new HashSet<>();
        List<TaskEntity> active = new ArrayList<>();
        active.addAll(taskRepository.findByStatus("ASSIGNED"));
        active.addAll(taskRepository.findByStatus("IN_PROGRESS"));
        for (TaskEntity task : active) {
            taskAssignmentRepository.findFirstByTaskIdOrderByAssignedAtTickDescIdDesc(task.getTaskId())
                    .ifPresent(a -> busy.add(a.getRobotId()));
        }
        return busy;
    }

    private Optional<RobotStateDto> nearestIdleRobot(Set<String> excludeRobotIds, PositionDto target) {
        RobotStateDto best = null;
        int bestDistance = Integer.MAX_VALUE;
        for (RobotStateDto robot : robotCacheService.values()) {
            if (!"IDLE".equals(robot.status) || excludeRobotIds.contains(robot.robotId)) {
                continue;
            }
            int distance = manhattan(robot.position, target);
            if (distance < bestDistance) {
                bestDistance = distance;
                best = robot;
            }
        }
        return Optional.ofNullable(best);
    }

    private int manhattan(PositionDto a, PositionDto b) {
        if (a == null || b == null) {
            return Integer.MAX_VALUE / 2; // unknown position — deprioritize but don't crash
        }
        return Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
    }
}
