package com.sih26123.backend.service;

import com.sih26123.backend.entity.EventEntity;
import com.sih26123.backend.model.PositionDto;
import com.sih26123.backend.model.RobotStateDto;
import com.sih26123.backend.repository.EventRepository;
import com.sih26123.backend.repository.TaskAssignmentRepository;
import com.sih26123.backend.repository.TaskRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * The "broken down" overlay and "Mark as fixed" (ProductSessionService.latchBrokenDownRobots / fixRobot). Plain unit test: every
 * collaborator is a mock except RobotCacheService, whose status/tick the test drives directly like real telemetry ingestion.
 */
class ProductSessionServiceBrokenDownTest {

    private SimulationClient simulationClient;
    private EventRepository eventRepository;
    private LiveUpdateBroadcaster broadcaster;
    private RobotCacheService robotCache;
    private ProductSessionService service;

    @BeforeEach
    void setUp() {
        simulationClient = mock(SimulationClient.class);
        eventRepository = mock(EventRepository.class);
        broadcaster = mock(LiveUpdateBroadcaster.class);
        robotCache = new RobotCacheService();
        // No warehouse map -> no task generation; these tests are only about the overlay.
        service = new ProductSessionService(mock(TaskRepository.class), mock(TaskAssignmentRepository.class), robotCache,
                mock(WarehouseCacheService.class), mock(TaskAllocationService.class), eventRepository,
                broadcaster, simulationClient);
        ReflectionTestUtils.setField(service, "running", true);
        ReflectionTestUtils.setField(service, "sessionId", "s1");
        ReflectionTestUtils.setField(service, "liveRobotIds", Set.of("PR1", "PR2"));
    }

    private void report(String id, String status, int tick) {
        RobotStateDto r = new RobotStateDto();
        r.robotId = id;
        r.position = new PositionDto();
        r.position.x = 3;
        r.position.y = 3;
        r.status = status;
        r.timestamp = tick;
        robotCache.upsert(r);
    }

    private void poll() {
        ReflectionTestUtils.invokeMethod(service, "pollOnce");
    }

    private long eventsOfType(String type) {
        org.mockito.ArgumentCaptor<EventEntity> c = org.mockito.ArgumentCaptor.forClass(EventEntity.class);
        verify(eventRepository, org.mockito.Mockito.atLeast(0)).save(c.capture());
        return c.getAllValues().stream().filter(e -> type.equals(e.getType())).count();
    }

    @Test
    void anOfflineRobotIsLatchedOnce_andStaysLatchedWhenItsStatusFlickersToBlocked() {
        report("PR1", "OFFLINE", 10);
        poll();
        assertThat(service.status().brokenDownRobots).containsExactly("PR1");
        // Python's OFFLINE flickers: a dead robot's end-of-tick status can read BLOCKED.
        report("PR1", "BLOCKED", 11);
        poll();
        report("PR1", "OFFLINE", 12);
        poll();
        assertThat(service.status().brokenDownRobots).containsExactly("PR1");
        assertThat(eventsOfType("ROBOT_BROKEN_DOWN")).isEqualTo(1);
    }

    @Test
    void aRobotThatIsNotOfflineOrNotThisSessionsIsNeverLatched() {
        report("PR2", "BLOCKED", 10);
        report("R7", "OFFLINE", 10); // a stale scenario robot in the global cache, not a live robot of this session
        poll();
        assertThat(service.status().brokenDownRobots).isEmpty();
    }

    @Test
    void fixRobot_asksPythonToRecover_clearsTheLabel_andIgnoresStaleOfflineReportsForAShortWindow() {
        report("PR1", "OFFLINE", 10);
        poll();
        service.fixRobot("PR1");
        verify(simulationClient).recoverRobot("PR1");
        assertThat(service.status().brokenDownRobots).isEmpty();
        assertThat(eventsOfType("ROBOT_FIXED")).isEqualTo(1);

        // A telemetry batch produced before Python applied the recovery still says OFFLINE: must not re-latch.
        report("PR1", "OFFLINE", 10 + ProductSessionService.RELATCH_IGNORE_TICKS);
        poll();
        assertThat(service.status().brokenDownRobots).isEmpty();

        // Python applied it: IDLE. Stays clear.
        report("PR1", "IDLE", 10 + ProductSessionService.RELATCH_IGNORE_TICKS + 1);
        poll();
        assertThat(service.status().brokenDownRobots).isEmpty();
    }

    @Test
    void ifPythonIgnoredTheFix_theRobotReLatchesOnceTheWindowHasPassed() {
        report("PR1", "OFFLINE", 10);
        poll();
        service.fixRobot("PR1");
        report("PR1", "OFFLINE", 10 + ProductSessionService.RELATCH_IGNORE_TICKS + 1);
        poll();
        assertThat(service.status().brokenDownRobots).containsExactly("PR1");
    }

    @Test
    void fixRobot_rejectsUnknownNotBrokenAndNoSession_withoutCallingPython() {
        report("PR1", "MOVING", 10);
        poll();
        assertThatThrownBy(() -> service.fixRobot("PR1")).isInstanceOf(IllegalArgumentException.class).hasMessageContaining("not broken down");
        assertThatThrownBy(() -> service.fixRobot("PR9")).isInstanceOf(IllegalArgumentException.class).hasMessageContaining("Unknown robot");
        assertThatThrownBy(() -> service.fixRobot(null)).isInstanceOf(IllegalArgumentException.class);
        ReflectionTestUtils.setField(service, "running", false);
        assertThatThrownBy(() -> service.fixRobot("PR1")).isInstanceOf(IllegalArgumentException.class).hasMessageContaining("No product session");
        verify(simulationClient, never()).recoverRobot(any());
    }

    @Test
    void ifPythonCannotBeReached_theLabelStays_andNoIgnoreWindowIsOpened() {
        report("PR1", "OFFLINE", 10);
        poll();
        doThrow(new SimulationEngineException("engine down", false, null)).when(simulationClient).recoverRobot("PR1");
        assertThatThrownBy(() -> service.fixRobot("PR1")).isInstanceOf(SimulationEngineException.class);
        assertThat(service.status().brokenDownRobots).containsExactly("PR1");
    }

    @Test
    void aFailedEventWriteNeverBreaksLatchingOrFixing() {
        when(eventRepository.save(any())).thenThrow(new RuntimeException("[SQLITE_BUSY] database is locked"));
        report("PR1", "OFFLINE", 10);
        poll(); // must not throw
        assertThat(service.status().brokenDownRobots).containsExactly("PR1");
        service.fixRobot("PR1"); // must not throw
        assertThat(service.status().brokenDownRobots).isEmpty();
        verify(simulationClient).recoverRobot("PR1");
    }

    @Test
    void aLockedDatabaseDoesNotStopTheEventReachingTheLiveFeed() {
        when(eventRepository.save(any())).thenThrow(new RuntimeException("[SQLITE_BUSY] database is locked"));
        report("PR1", "OFFLINE", 10);
        poll();
        // the history write failed, but the WebSocket broadcast (what the Product tab's event feed is built from) still went out
        org.mockito.ArgumentCaptor<com.sih26123.backend.model.SimulationEventDto> sent =
                org.mockito.ArgumentCaptor.forClass(com.sih26123.backend.model.SimulationEventDto.class);
        verify(broadcaster).broadcastEvent(org.mockito.ArgumentMatchers.anyInt(), sent.capture());
        assertThat(sent.getValue().type).isEqualTo("ROBOT_BROKEN_DOWN");
    }

    @Test
    void startingANewSessionClearsTheOverlay() {
        report("PR1", "OFFLINE", 10);
        poll();
        assertThat(service.status().brokenDownRobots).isNotEmpty();
        ReflectionTestUtils.setField(service, "running", false);
        service.start("s2", 1L, 4);
        try {
            assertThat(service.status().brokenDownRobots).isEmpty();
        } finally {
            service.stop();
        }
    }
}
