package com.sih26123.backend.service;

import com.sih26123.backend.entity.TaskAssignmentEntity;
import com.sih26123.backend.entity.TaskEntity;
import com.sih26123.backend.model.PositionDto;
import com.sih26123.backend.model.RobotStateDto;
import com.sih26123.backend.model.TaskDto;
import com.sih26123.backend.model.WarehouseMapDto;
import com.sih26123.backend.repository.EventRepository;
import com.sih26123.backend.repository.TaskAssignmentRepository;
import com.sih26123.backend.repository.TaskRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.List;
import java.util.Optional;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Backlog-freeze fix: a task whose robot has not changed cell for
 * ProductSessionService.STALL_ABANDON_TICKS is abandoned (FAILED, its backlog
 * slot freed) and Python is asked to release the robot. Plain unit test —
 * every collaborator is a mock except RobotCacheService, whose tick/position
 * the test drives directly, exactly as real telemetry ingestion does.
 */
class ProductSessionServiceStallTest {

    private static final String TASK_ID = "task_s1_1"; // "task_" + sessionId + "_" + first seq

    private TaskRepository taskRepository;
    private TaskAssignmentRepository assignmentRepository;
    private SimulationClient simulationClient;
    private EventRepository eventRepository;
    private RobotCacheService robotCache;
    private ProductSessionService service;
    private TaskEntity task;

    @BeforeEach
    void setUp() {
        taskRepository = mock(TaskRepository.class);
        assignmentRepository = mock(TaskAssignmentRepository.class);
        simulationClient = mock(SimulationClient.class);
        WarehouseCacheService warehouse = mock(WarehouseCacheService.class);
        eventRepository = mock(EventRepository.class);
        robotCache = new RobotCacheService();

        WarehouseMapDto map = new WarehouseMapDto();
        map.pickupPoints = List.of(pos(1, 1));
        map.dropPoints = List.of(pos(9, 9));
        when(warehouse.get()).thenReturn(map);

        service = new ProductSessionService(taskRepository, assignmentRepository, robotCache, warehouse,
                mock(TaskAllocationService.class), eventRepository, mock(LiveUpdateBroadcaster.class),
                simulationClient);
        // Drive pollOnce() directly instead of starting the 200 ms executor.
        ReflectionTestUtils.setField(service, "running", true);
        ReflectionTestUtils.setField(service, "sessionId", "s1");
        ReflectionTestUtils.setField(service, "seed", 1L);
        ReflectionTestUtils.setField(service, "taskRng", new java.util.Random(1L));
        ReflectionTestUtils.setField(service, "liveRobotIds", Set.of("PR1"));

        TaskDto dto = new TaskDto();
        dto.taskId = TASK_ID;
        dto.pickupPosition = pos(1, 1);
        dto.dropPosition = pos(9, 9);
        dto.priority = 3;
        dto.status = "ASSIGNED"; // as if the existing allocator had already picked PR1
        task = TaskEntity.fromDto(dto);
        when(taskRepository.findById(TASK_ID)).thenReturn(Optional.of(task));

        TaskAssignmentEntity assignment = new TaskAssignmentEntity(TASK_ID, "PR1", 1, null);
        ReflectionTestUtils.setField(assignment, "id", 1L);
        when(assignmentRepository.findFirstByTaskIdOrderByAssignedAtTickDescIdDesc(TASK_ID))
                .thenReturn(Optional.of(assignment));
    }

    private static PositionDto pos(int x, int y) {
        PositionDto p = new PositionDto();
        p.x = x;
        p.y = y;
        return p;
    }

    private void report(String status, int x, int y, int tick) {
        RobotStateDto r = new RobotStateDto();
        r.robotId = "PR1";
        r.position = pos(x, y);
        r.status = status;
        r.timestamp = tick;
        robotCache.upsert(r);
    }

    private void poll() {
        ReflectionTestUtils.invokeMethod(service, "pollOnce");
    }

    /** First poll generates task_s1_1 and pushes it; second poll starts the stall clock. */
    private void pushAndStartClock(int tick) {
        report("MOVING", 3, 3, tick);
        poll(); // generates + pushes
        verify(simulationClient).assignTask(eq("PR1"), eq(TASK_ID), any(), any(), anyInt());
        poll(); // first observation of the robot's position for this task
    }

    @Test
    void robotThatNeverMoves_taskIsAbandonedAtTheThreshold_andRobotIsReleased() {
        pushAndStartClock(10);
        assertThat(ProductSessionService.STALL_ABANDON_TICKS).isEqualTo(30);

        report("WAITING", 3, 3, 10 + ProductSessionService.STALL_ABANDON_TICKS - 1);
        poll();
        assertThat(task.getStatus()).isEqualTo("IN_PROGRESS");
        verify(simulationClient, never()).releaseRobot(anyString(), anyString());

        report("WAITING", 3, 3, 10 + ProductSessionService.STALL_ABANDON_TICKS);
        poll();
        assertThat(task.getStatus()).isEqualTo("FAILED");
        verify(simulationClient).releaseRobot("PR1", TASK_ID);
        assertThat(service.status().tasksFailed).isEqualTo(1);
    }

    @Test
    void abandonedTask_freesItsBacklogSlot_soGenerationCanContinue() {
        // Fill the backlog to MAX_BACKLOG with stuck tasks is not needed to prove the mechanism:
        // the abandoned task must simply no longer count as in flight.
        pushAndStartClock(10);
        report("WAITING", 3, 3, 10 + ProductSessionService.STALL_ABANDON_TICKS);
        poll();
        Object tracked = ReflectionTestUtils.getField(service, "tracked");
        long inFlight = ((java.util.Map<?, ?>) tracked).values().stream()
                .filter(t -> !(boolean) ReflectionTestUtils.getField(t, "completed")).count();
        // Only tasks generated AFTER the abandonment (if any) may still be open; TASK_ID must not be.
        Object abandoned = ((java.util.Map<?, ?>) tracked).get(TASK_ID);
        assertThat((boolean) ReflectionTestUtils.getField(abandoned, "completed")).isTrue();
        assertThat(inFlight).isLessThan(3);
    }

    @Test
    void robotThatKeepsMoving_isNeverAbandoned() {
        pushAndStartClock(10);
        // Moves every 20 ticks — never 30 in the same cell.
        for (int i = 1; i <= 6; i++) {
            report("MOVING", 3 + i, 3, 10 + i * 20);
            poll();
        }
        assertThat(task.getStatus()).isEqualTo("IN_PROGRESS");
        verify(simulationClient, never()).releaseRobot(anyString(), anyString());
        assertThat(service.status().tasksFailed).isZero();
    }

    @Test
    void offlineRobot_isNotAbandonedByThisPath() {
        pushAndStartClock(10);
        report("OFFLINE", 3, 3, 10 + 3 * ProductSessionService.STALL_ABANDON_TICKS);
        poll();
        assertThat(task.getStatus()).isEqualTo("IN_PROGRESS");
        verify(simulationClient, never()).releaseRobot(anyString(), anyString());
    }

    @Test
    void failedReleaseRequest_doesNotBreakThePoll_andTheTaskStaysAbandoned() {
        doThrow(new SimulationEngineException("engine down", false, null))
                .when(simulationClient).releaseRobot(anyString(), anyString());
        pushAndStartClock(10);
        report("WAITING", 3, 3, 10 + ProductSessionService.STALL_ABANDON_TICKS);
        poll(); // must not throw
        assertThat(task.getStatus()).isEqualTo("FAILED");
        assertThat(service.status().tasksFailed).isEqualTo(1);
    }

    @Test
    void lockedDatabaseWhileRecordingTheEvent_stillReleasesTheRobot_andKeepsTheTaskAbandoned() {
        // Real full-stack finding: SQLite is routinely "database is locked" under telemetry load. The release
        // request must not depend on any DB write succeeding, and a lost feed event must not undo the abandonment.
        pushAndStartClock(10);
        when(eventRepository.save(any())).thenAnswer(inv -> {
            com.sih26123.backend.entity.EventEntity e = inv.getArgument(0);
            if ("TASK_STATUS_CHANGED".equals(e.getType())) {
                throw new RuntimeException("[SQLITE_BUSY] database is locked");
            }
            return e;
        });
        report("WAITING", 3, 3, 10 + ProductSessionService.STALL_ABANDON_TICKS);
        poll(); // must not throw
        verify(simulationClient).releaseRobot("PR1", TASK_ID);
        assertThat(task.getStatus()).isEqualTo("FAILED");
        assertThat(service.status().tasksFailed).isEqualTo(1);
    }

    @Test
    void lockedDatabaseWhileSavingTheTask_retriesOnTheNextPoll() {
        pushAndStartClock(10);
        report("WAITING", 3, 3, 10 + ProductSessionService.STALL_ABANDON_TICKS);
        when(taskRepository.save(any())).thenThrow(new RuntimeException("[SQLITE_BUSY] database is locked"))
                .thenAnswer(inv -> inv.getArgument(0));
        try {
            poll();
        } catch (RuntimeException expected) {
            // safePoll() swallows this in production; the point is what the NEXT poll does.
        }
        assertThat(service.status().tasksFailed).isZero(); // not marked abandoned yet
        poll();
        assertThat(task.getStatus()).isEqualTo("FAILED");
        assertThat(service.status().tasksFailed).isEqualTo(1);
        verify(simulationClient, org.mockito.Mockito.atLeast(1)).releaseRobot("PR1", TASK_ID);
    }

    @Test
    void completedTask_isNeverTreatedAsStalled() {
        pushAndStartClock(10);
        report("IDLE", 9, 9, 20); // arrived at the drop cell
        poll();
        assertThat(task.getStatus()).isEqualTo("COMPLETED");
        report("IDLE", 9, 9, 200);
        poll();
        verify(simulationClient, never()).releaseRobot(anyString(), anyString());
        assertThat(service.status().tasksFailed).isZero();
        assertThat(service.status().tasksCompleted).isEqualTo(1);
    }
}
