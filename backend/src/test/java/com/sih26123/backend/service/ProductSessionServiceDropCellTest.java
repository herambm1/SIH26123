package com.sih26123.backend.service;

import com.sih26123.backend.entity.TaskEntity;
import com.sih26123.backend.model.PositionDto;
import com.sih26123.backend.model.RobotStateDto;
import com.sih26123.backend.model.WarehouseMapDto;
import com.sih26123.backend.repository.EventRepository;
import com.sih26123.backend.repository.TaskAssignmentRepository;
import com.sih26123.backend.repository.TaskRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.atLeastOnce;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Task generation must never pick a drop cell that a robot of this session is standing on, or that is already
 * the drop cell of an open task (see ProductSessionService.unoccupiedDropPoints).
 */
class ProductSessionServiceDropCellTest {

    private TaskRepository taskRepository;
    private RobotCacheService robotCache;
    private ProductSessionService service;
    private WarehouseMapDto map;

    @BeforeEach
    void setUp() {
        taskRepository = mock(TaskRepository.class);
        WarehouseCacheService warehouse = mock(WarehouseCacheService.class);
        robotCache = new RobotCacheService();
        map = new WarehouseMapDto();
        map.pickupPoints = List.of(pos(1, 1));
        map.dropPoints = List.of(pos(9, 1), pos(9, 2), pos(9, 3), pos(9, 4));
        when(warehouse.get()).thenReturn(map);

        service = new ProductSessionService(taskRepository, mock(TaskAssignmentRepository.class), robotCache, warehouse,
                mock(TaskAllocationService.class), mock(EventRepository.class), mock(LiveUpdateBroadcaster.class),
                mock(SimulationClient.class));
        ReflectionTestUtils.setField(service, "running", true);
        ReflectionTestUtils.setField(service, "sessionId", "s1");
        ReflectionTestUtils.setField(service, "liveRobotIds", Set.of("PR1", "PR2"));
    }

    private static PositionDto pos(int x, int y) {
        PositionDto p = new PositionDto();
        p.x = x;
        p.y = y;
        return p;
    }

    private void robotAt(String id, int x, int y, int tick) {
        RobotStateDto r = new RobotStateDto();
        r.robotId = id;
        r.position = pos(x, y);
        r.status = "IDLE";
        r.timestamp = tick;
        robotCache.upsert(r);
    }

    /** Generate tasks until n exist, forcing the "next generation tick" open each time; returns the drop cells chosen. */
    private List<String> generate(int n, long rngSeed) {
        ReflectionTestUtils.setField(service, "taskRng", new java.util.Random(rngSeed));
        ReflectionTestUtils.setField(service, "nextTaskGenerationTick", 0);
        for (int i = 0; i < n; i++) {
            ReflectionTestUtils.setField(service, "nextTaskGenerationTick", 0);
            ReflectionTestUtils.invokeMethod(service, "pollOnce");
        }
        ArgumentCaptor<TaskEntity> saved = ArgumentCaptor.forClass(TaskEntity.class);
        verify(taskRepository, atLeastOnce()).save(saved.capture());
        return saved.getAllValues().stream()
                .map(t -> t.getDropPosition().toDto().x + "," + t.getDropPosition().toDto().y)
                .toList();
    }

    @Test
    void neverPicksACellARobotIsStandingOn() {
        robotAt("PR1", 9, 1, 5);
        robotAt("PR2", 9, 2, 5);
        for (long seed = 1; seed <= 30; seed++) {
            org.mockito.Mockito.clearInvocations(taskRepository);
            ReflectionTestUtils.setField(service, "tracked", new java.util.concurrent.ConcurrentHashMap<>());
            List<String> drops = generate(1, seed);
            assertThat(drops.get(0)).isIn("9,3", "9,4");
        }
    }

    @Test
    void neverPicksTheDropCellOfAnOpenTask_soOpenTasksGetDistinctDrops() {
        robotAt("PR1", 5, 5, 5); // parked away from every drop cell
        List<String> drops = generate(3, 7L); // MAX_BACKLOG = 3 open tasks at most
        assertThat(new HashSet<>(drops)).hasSize(3); // 4 drop cells, 3 open tasks: all distinct
    }

    @Test
    void foreignRobotsInTheGlobalCacheDoNotBlockADropCell() {
        robotAt("R1", 9, 1, 5); // a stale scenario robot, not one of this session's live robots
        boolean everPicked = false;
        for (long seed = 1; seed <= 60 && !everPicked; seed++) {
            org.mockito.Mockito.clearInvocations(taskRepository);
            ReflectionTestUtils.setField(service, "tracked", new java.util.concurrent.ConcurrentHashMap<>());
            everPicked = generate(1, seed).get(0).equals("9,1");
        }
        assertThat(everPicked).isTrue();
    }

    @Test
    void whenEveryDropCellIsTaken_generationStillProduceATask() {
        robotAt("PR1", 9, 1, 5);
        robotAt("PR2", 9, 2, 5);
        ReflectionTestUtils.setField(service, "liveRobotIds", Set.of("PR1", "PR2", "PR3", "PR4"));
        robotAt("PR3", 9, 3, 5);
        robotAt("PR4", 9, 4, 5);
        List<String> drops = generate(1, 3L);
        assertThat(drops).hasSize(1);
        assertThat(drops.get(0)).isIn("9,1", "9,2", "9,3", "9,4");
    }
}
