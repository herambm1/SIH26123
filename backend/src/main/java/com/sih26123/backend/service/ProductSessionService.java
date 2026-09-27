package com.sih26123.backend.service;

import com.sih26123.backend.entity.EventEntity;
import com.sih26123.backend.entity.TaskAssignmentEntity;
import com.sih26123.backend.entity.TaskEntity;
import com.sih26123.backend.model.PositionDto;
import com.sih26123.backend.model.ProductSessionStatusDto;
import com.sih26123.backend.model.RobotStateDto;
import com.sih26123.backend.model.SimulationEventDto;
import com.sih26123.backend.model.TaskDto;
import com.sih26123.backend.model.WarehouseMapDto;
import com.sih26123.backend.repository.EventRepository;
import com.sih26123.backend.repository.TaskAssignmentRepository;
import com.sih26123.backend.repository.TaskRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.Random;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * ProductSessionService — Java-side task-lifecycle orchestration for a live
 * "Product" session. Owner: Member 6 (Phase 2, product-mode).
 *
 * ISOLATION (see Phase 2 design discussion — every point re-verified against
 * the actual current file contents, not assumed):
 *   - Does NOT add any method to TaskAllocationService. It injects the
 *     existing, unmodified TaskAllocationService and calls only its
 *     existing public allocatePendingTasks() — the exact same call
 *     TaskController.createTask() already makes after creating a task.
 *   - Does NOT touch TelemetryIngestController, TaskController, or
 *     SimulationControlController. It runs its own ScheduledExecutorService
 *     poll loop rather than hooking into telemetry ingestion — deliberately,
 *     so BackendApplication does not need @EnableScheduling either, and the
 *     scenario/benchmark request path is unaffected in every possible way,
 *     not just in the common case.
 *   - Only ever writes TaskEntity.status = "IN_PROGRESS" or "COMPLETED" —
 *     two values nothing else in this codebase currently writes (confirmed
 *     by grep). "PENDING" and "ASSIGNED" continue to be written ONLY by the
 *     existing TaskController/TaskAllocationService code, unchanged.
 *
 * ROBOT-ID / TASK-ID NAMESPACING: every robot in a product session is named
 * "PR1".."PRn" by simulation/product/session.py (not "R1".."Rn", which every
 * scenario file uses) and every task this service creates is prefixed
 * "task_&lt;sessionId&gt;_" — both deliberately, to keep a product session's
 * data structurally distinguishable from a scenario run's, given that
 * RobotCacheService is a single global, never-cleared, session-unaware
 * cache (confirmed by reading it directly). See isCurrentSessionRobot()
 * below for the resulting safety-net check this still requires.
 */
@Service
public class ProductSessionService {

    private static final Logger log = LoggerFactory.getLogger(ProductSessionService.class);

    /** Never more than this many of OUR OWN not-yet-completed tasks in flight at once. */
    private static final int MAX_BACKLOG = 3;
    /** Poll cadence — a mechanical detail only; every actual decision below is keyed off the
     * TICK read from real telemetry (robotCacheService.lastTick()), never off wall-clock time. */
    private static final long POLL_DELAY_MS = 200;
    /** Task order generation is tick-driven with seeded jitter — a new task is considered
     * roughly every 8-15 ticks, subject to the MAX_BACKLOG cap above. */
    private static final int TASK_MIN_INTERVAL_TICKS = 8;
    private static final int TASK_INTERVAL_JITTER_TICKS = 8;
    /** Re-check-later interval when a task generation attempt was skipped (backlog full or
     * warehouse map not yet cached) — avoids busy-looping every 200ms with no effect. */
    private static final int TASK_RETRY_TICKS = 5;
    /** Bounded retry cap for the stale-robot isolation safety net below — without this, a
     * stale non-PR* robot that keeps winning TaskAllocationService.nearestIdleRobot()'s
     * selection (e.g. because it is the only one ever reported IDLE, and nothing else in the
     * global RobotCacheService ever changes) would revert-and-reassign indefinitely, once per
     * poll cycle, forever. After this many reverts the task is abandoned (marked FAILED, a
     * status value TaskDto's own docstring already documents as valid but that nothing else in
     * this codebase currently writes) rather than looped forever. */
    private static final int MAX_STALE_ROBOT_REVERTS = 5;
    /** Backlog-freeze fix. A task whose robot has made no progress (same cell in the cache) for
     * this many ticks is abandoned (FAILED) so it stops holding one of the MAX_BACKLOG slots, and
     * the robot is released so it can take new work. Without this, a robot that strands (its
     * agent-side avoid-cell list never expires, so it eventually has no route) keeps its task
     * IN_PROGRESS forever; three such robots froze task generation for the rest of the session
     * (roughly 90 s of a LIVE session at 1x). 30 ticks matches simulation/product/session.py's own
     * _STALL_TICKS; measured in a Java-faithful soak, a stall that long resolves by itself in
     * about 2-4% of cases (docs/PRODUCT_MODE_INVESTIGATION_STATUS.md, "Backlog freeze"). */
    static final int STALL_ABANDON_TICKS = 30;
    /** After a fix, OFFLINE observations of that robot are ignored for this many ticks so a telemetry batch produced before
     * Python applied the recovery cannot re-latch it as broken down. If Python ignored the fix (the robot was not really
     * dead) the robot simply re-latches once the window has passed. */
    static final int RELATCH_IGNORE_TICKS = 10;

    private final TaskRepository taskRepository;
    private final TaskAssignmentRepository taskAssignmentRepository;
    private final RobotCacheService robotCacheService;
    private final WarehouseCacheService warehouseCacheService;
    private final TaskAllocationService taskAllocationService;
    private final EventRepository eventRepository;
    private final LiveUpdateBroadcaster broadcaster;
    private final SimulationClient simulationClient;

    public ProductSessionService(TaskRepository taskRepository,
                                  TaskAssignmentRepository taskAssignmentRepository,
                                  RobotCacheService robotCacheService,
                                  WarehouseCacheService warehouseCacheService,
                                  TaskAllocationService taskAllocationService,
                                  EventRepository eventRepository,
                                  LiveUpdateBroadcaster broadcaster,
                                  SimulationClient simulationClient) {
        this.taskRepository = taskRepository;
        this.taskAssignmentRepository = taskAssignmentRepository;
        this.robotCacheService = robotCacheService;
        this.warehouseCacheService = warehouseCacheService;
        this.taskAllocationService = taskAllocationService;
        this.eventRepository = eventRepository;
        this.broadcaster = broadcaster;
        this.simulationClient = simulationClient;
    }

    // ── Per-task tracking (this service's own state, not persisted) ────────

    private static final class TrackedTask {
        final String taskId;
        final PositionDto pickupPosition;
        final PositionDto dropPosition;
        final int priority;
        Long lastPushedAssignmentId; // null until we've pushed at least once
        boolean completed;
        int staleRobotReverts; // see MAX_STALE_ROBOT_REVERTS below
        PositionDto lastObservedPosition; // null until first observed after a push
        int lastMoveTick;

        TrackedTask(String taskId, PositionDto pickupPosition, PositionDto dropPosition, int priority) {
            this.taskId = taskId;
            this.pickupPosition = pickupPosition;
            this.dropPosition = dropPosition;
            this.priority = priority;
        }
    }

    private volatile boolean running = false;
    private volatile String sessionId;
    private volatile Long seed;
    private volatile Set<String> liveRobotIds = Set.of();
    private final Map<String, TrackedTask> tracked = new ConcurrentHashMap<>();
    private final AtomicInteger taskSeq = new AtomicInteger(0);
    private Random taskRng;
    private int nextTaskGenerationTick;
    private ScheduledExecutorService executor;

    /** "Broken down" overlay - see ProductSessionStatusDto.brokenDownRobots. */
    private final Set<String> brokenDown = ConcurrentHashMap.newKeySet();
    private final Map<String, Integer> ignoreOfflineUntilTick = new ConcurrentHashMap<>();

    private final AtomicInteger createdCount = new AtomicInteger(0);
    private final AtomicInteger inProgressCount = new AtomicInteger(0);
    private final AtomicInteger completedCount = new AtomicInteger(0);
    private final AtomicInteger reassignedCount = new AtomicInteger(0);
    private final AtomicInteger failedCount = new AtomicInteger(0);

    // ── Lifecycle ────────────────────────────────────────────────────────

    /**
     * Start local orchestration for a session Python has ALREADY started
     * (sessionId/seed come from Python's own POST /control/product/start
     * response — see ProductController — never generated independently
     * here, so Java-side events tag the exact same sessionId Python's own
     * events carry).
     */
    public synchronized void start(String sessionId, long seed, int robotCount) {
        if (running) {
            throw new IllegalStateException("A product session is already running locally.");
        }
        this.sessionId = sessionId;
        this.seed = seed;
        this.taskRng = new Random(seed);
        this.nextTaskGenerationTick = 0;
        this.tracked.clear();
        this.brokenDown.clear();
        this.ignoreOfflineUntilTick.clear();
        this.taskSeq.set(0);
        this.createdCount.set(0);
        this.inProgressCount.set(0);
        this.completedCount.set(0);
        this.reassignedCount.set(0);
        this.failedCount.set(0);

        Set<String> ids = new HashSet<>();
        for (int i = 1; i <= robotCount; i++) {
            ids.add("PR" + i);
        }
        this.liveRobotIds = Set.copyOf(ids);

        this.running = true;
        this.executor = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "product-session-poll");
            t.setDaemon(true);
            return t;
        });
        this.executor.scheduleWithFixedDelay(this::safePoll, POLL_DELAY_MS, POLL_DELAY_MS, TimeUnit.MILLISECONDS);
        log.info("Product session {} local orchestration started (seed={}, robots={})", sessionId, seed, liveRobotIds);
    }

    /**
     * Called by ProductController BEFORE it asks Python to start a new session. Fixes two things that made a second session
     * in the same backend process misbehave (found while building the Product tab's RANDOMIZE &amp; START, which starts
     * sessions back to back):
     *   1. RobotCacheService.lastTick() never decreases, so the new session's tick-driven logic ran on the previous
     *      session's stale, higher tick (no task generated until the new ticks caught up; envelope tick pinned): the
     *      cache is reset.
     *   2. Product tasks left PENDING/ASSIGNED/IN_PROGRESS by the previous session kept their robots "busy" for
     *      TaskAllocationService (robot ids PR1..PRn repeat every session): they are marked FAILED. Only tasks with the
     *      product prefix "task_product_" are touched.
     */
    public void prepareNewSession() {
        robotCacheService.reset();
        int closed = 0;
        for (String status : List.of("PENDING", "ASSIGNED", "IN_PROGRESS")) {
            for (TaskEntity task : taskRepository.findByStatus(status)) {
                if (task.getTaskId() != null && task.getTaskId().startsWith("task_product_")) {
                    task.setStatus("FAILED");
                    taskRepository.save(task);
                    closed++;
                }
            }
        }
        if (closed > 0) {
            log.info("Product session: closed {} task(s) left open by a previous session before starting a new one", closed);
        }
    }

    public synchronized void stop() {
        running = false;
        if (executor != null) {
            executor.shutdown();
            try {
                executor.awaitTermination(1, TimeUnit.SECONDS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            executor = null;
        }
        log.info("Product session {} local orchestration stopped ({} created, {} completed, {} reassigned)",
                sessionId, createdCount.get(), completedCount.get(), reassignedCount.get());
    }

    public boolean isRunning() {
        return running;
    }

    public ProductSessionStatusDto status() {
        ProductSessionStatusDto dto = new ProductSessionStatusDto();
        dto.running = running;
        dto.sessionId = sessionId;
        dto.seed = seed;
        dto.currentTick = robotCacheService.lastTick();
        // created/inProgress/completed/reassigned are LIFETIME counters
        // (never decremented) — inProgress counts every ASSIGNED->
        // IN_PROGRESS transition that has ever happened, not "currently in
        // progress right now" (a task that later completes still counts).
        dto.tasksCreated = createdCount.get();
        dto.tasksInProgress = inProgressCount.get();
        dto.tasksCompleted = completedCount.get();
        dto.tasksReassigned = reassignedCount.get();
        dto.tasksFailed = failedCount.get();
        dto.brokenDownRobots = new ArrayList<>(new java.util.TreeSet<>(brokenDown));
        // tasksPendingOrAssigned, by contrast, IS a live snapshot: of our
        // still-open (not-yet-completed) tracked tasks, how many have not
        // yet had an assignment pushed to Python (lastPushedAssignmentId ==
        // null) — i.e. still PENDING or ASSIGNED-but-not-yet-pushed.
        long notCompleted = tracked.values().stream().filter(t -> !t.completed).count();
        long currentlyPushed = tracked.values().stream()
                .filter(t -> !t.completed && t.lastPushedAssignmentId != null).count();
        dto.tasksPendingOrAssigned = (int) (notCompleted - currentlyPushed);
        return dto;
    }

    // ── Poll loop ────────────────────────────────────────────────────────

    private void safePoll() {
        try {
            pollOnce();
        } catch (Exception e) {
            // A poll-cycle failure must never kill the scheduled executor —
            // the next cycle should still run (same "never let a background
            // failure silently stop everything" principle GlobalExceptionHandler
            // applies to requests).
            log.warn("Product session {} poll cycle failed: {}", sessionId, e.getMessage(), e);
        }
    }

    private synchronized void pollOnce() {
        if (!running) {
            return;
        }
        int tick = robotCacheService.lastTick();

        latchBrokenDownRobots(tick);
        maybeGenerateTask(tick);

        for (TrackedTask t : tracked.values()) {
            if (t.completed) {
                continue;
            }
            Optional<TaskEntity> taskOpt = taskRepository.findById(t.taskId);
            if (taskOpt.isEmpty()) {
                continue;
            }
            TaskEntity task = taskOpt.get();
            String status = task.getStatus();
            if ("PENDING".equals(status)) {
                continue; // not yet picked up by the existing allocator
            }

            Optional<TaskAssignmentEntity> latest =
                    taskAssignmentRepository.findFirstByTaskIdOrderByAssignedAtTickDescIdDesc(t.taskId);
            if (latest.isEmpty()) {
                continue;
            }
            TaskAssignmentEntity assignment = latest.get();
            String robotId = assignment.getRobotId();

            if (!isCurrentSessionRobot(robotId)) {
                // Safety net (see class javadoc): the existing, unmodified
                // TaskAllocationService.nearestIdleRobot() scans the global
                // RobotCacheService with no session awareness at all. A
                // stale robot left IDLE in the cache by a PREVIOUS scenario
                // run could otherwise be selected for one of OUR tasks.
                // Never push a stale/foreign robot to Python.
                t.staleRobotReverts++;
                if (t.staleRobotReverts > MAX_STALE_ROBOT_REVERTS) {
                    // Bounded — see MAX_STALE_ROBOT_REVERTS. Reverting to
                    // PENDING has already been tried this many times and
                    // the SAME kind of foreign robot keeps winning
                    // allocation; looping forever would never surface the
                    // problem to anyone. Abandon this one task rather than
                    // spin — the session itself keeps running.
                    log.error("Product session {}: task {} was reassigned to a non-live robot more than {} "
                                    + "times in a row (most recently '{}', live robots are {}) — abandoning this "
                                    + "task as FAILED rather than retrying indefinitely. This points at a "
                                    + "persistently stale entry in the global RobotCacheService; it does not "
                                    + "affect any other task or the session as a whole.",
                            sessionId, t.taskId, MAX_STALE_ROBOT_REVERTS, robotId, liveRobotIds);
                    task.setStatus("FAILED");
                    taskRepository.save(task);
                    t.completed = true; // stop tracking/polling this task
                    failedCount.incrementAndGet();
                    emitEvent("TASK_STATUS_CHANGED", tick, orderedMap(
                            "taskId", t.taskId, "toStatus", "FAILED",
                            "reason", "repeatedly assigned to a non-live robot (" + robotId + "); abandoned after "
                                    + MAX_STALE_ROBOT_REVERTS + " reallocation attempts"));
                    continue;
                }
                // Release the task back to PENDING so the existing
                // allocator gets another chance (it is re-invoked on every
                // telemetry batch regardless, via TelemetryIngestController,
                // unchanged).
                log.warn("Product session {}: task {} was assigned to '{}', which is not a live robot of this "
                                + "session ({}) — reverting to PENDING for reallocation (attempt {}/{}). This "
                                + "indicates a stale robot entry in the global RobotCacheService (see "
                                + "ProductSessionService javadoc).",
                        sessionId, t.taskId, robotId, liveRobotIds, t.staleRobotReverts, MAX_STALE_ROBOT_REVERTS);
                task.setStatus("PENDING");
                taskRepository.save(task);
                continue;
            }

            if (!assignment.getId().equals(t.lastPushedAssignmentId)) {
                boolean isReassignment = t.lastPushedAssignmentId != null;
                simulationClient.assignTask(robotId, t.taskId, t.pickupPosition, t.dropPosition, t.priority);
                t.lastPushedAssignmentId = assignment.getId();
                if (!"IN_PROGRESS".equals(status)) {
                    task.setStatus("IN_PROGRESS");
                    taskRepository.save(task);
                    inProgressCount.incrementAndGet();
                }
                if (isReassignment) {
                    reassignedCount.incrementAndGet();
                }
                t.lastObservedPosition = null; // stall clock restarts for the (new) robot
                emitEvent("TASK_PUSHED_TO_ENGINE", tick, orderedMap(
                        "taskId", t.taskId, "robotId", robotId, "reassignment", isReassignment));
                continue; // this task's completion is checked on a later poll, not the same cycle
            }

            // Completion: exact-cell position match + status back to IDLE —
            // both fields already ingested by the existing, unmodified
            // TelemetryIngestController into RobotCacheService. No fuzzy
            // radius: the grid is discrete, and robot_agent/agent.py's own
            // arrival check (_advance_one_cell_if_clear) only ever sets
            // status="IDLE" on an EXACT position==destination match, so an
            // exact match here is the only value that check can produce.
            Optional<RobotStateDto> robotOpt = robotCacheService.get(robotId);
            if (robotOpt.isPresent()) {
                RobotStateDto robot = robotOpt.get();
                if ("IDLE".equals(robot.status) && positionEquals(robot.position, t.dropPosition)) {
                    task.setStatus("COMPLETED");
                    taskRepository.save(task);
                    t.completed = true;
                    completedCount.incrementAndGet();
                    emitEvent("TASK_STATUS_CHANGED", tick, orderedMap(
                            "taskId", t.taskId, "robotId", robotId, "toStatus", "COMPLETED"));
                } else if (!"OFFLINE".equals(robot.status)) {
                    // (OFFLINE robots are handled by TaskAllocationService.handleRobotOffline,
                    // via TelemetryIngestController — a different, existing path.)
                    abandonIfStalled(t, task, robot, tick);
                }
            }
        }
    }

    /**
     * Backlog-freeze fix (see STALL_ABANDON_TICKS): tracks whether the robot holding this task
     * has moved, using only what real telemetry already put in RobotCacheService (position + the
     * tick). If it has not changed cell for STALL_ABANDON_TICKS, the task is abandoned as FAILED
     * (freeing its backlog slot — a fresh task is generated by the normal path) and Python is
     * asked to release the robot.
     *
     * Ordering matters, found in a real full-stack run: the backend's SQLite file is routinely
     * "database is locked" under telemetry load (about 2-3% of poll cycles fail on a DB write).
     * The release request is therefore sent FIRST and needs no DB access; a save that then fails
     * aborts the poll before the task is marked abandoned, so the next poll simply retries
     * (Python re-validates every release — a repeat for a robot that is already IDLE, or is on a
     * different task, is ignored). The first version marked the task abandoned and THEN wrote the
     * event, so a locked-DB failure on that event (the full-stack logs showed exactly that:
     * "poll cycle failed ... insert into events") left the task FAILED with no release ever sent.
     */
    private void abandonIfStalled(TrackedTask t, TaskEntity task, RobotStateDto robot, int tick) {
        if (t.lastObservedPosition == null || !positionEquals(t.lastObservedPosition, robot.position)) {
            PositionDto copy = new PositionDto();
            copy.x = robot.position == null ? 0 : robot.position.x;
            copy.y = robot.position == null ? 0 : robot.position.y;
            t.lastObservedPosition = robot.position == null ? null : copy;
            t.lastMoveTick = tick;
            return;
        }
        int stalledTicks = tick - t.lastMoveTick;
        if (stalledTicks < STALL_ABANDON_TICKS) {
            return;
        }
        log.warn("Product session {}: task {} abandoned — robot {} has not moved for {} ticks (status {}); "
                        + "freeing its backlog slot and asking Python to release the robot.",
                sessionId, t.taskId, robot.robotId, stalledTicks, robot.status);
        try {
            simulationClient.releaseRobot(robot.robotId, t.taskId);
        } catch (RuntimeException e) {
            log.warn("Product session {}: release request for robot {} failed: {}", sessionId, robot.robotId, e.getMessage());
        }
        task.setStatus("FAILED");
        taskRepository.save(task);
        t.completed = true; // stop tracking/polling this task; its backlog slot is now free
        failedCount.incrementAndGet();
        try {
            emitEvent("TASK_STATUS_CHANGED", tick, orderedMap(
                    "taskId", t.taskId, "robotId", robot.robotId, "toStatus", "FAILED",
                    "reason", "no progress for " + stalledTicks + " ticks (robot status " + robot.status
                            + "); abandoned and the robot was asked to release"));
        } catch (RuntimeException e) {
            // The task is already FAILED and the robot released; only the feed event is lost.
            log.warn("Product session {}: could not record the FAILED event for task {}: {}", sessionId, t.taskId, e.getMessage());
        }
    }

    /**
     * Latch every live robot of this session that reports OFFLINE as "broken down". Reassigning its task is NOT done here:
     * TelemetryIngestController already calls TaskAllocationService.handleRobotOffline on every OFFLINE report (the Phase 2
     * mechanism) - this only adds the sticky label. The label is needed because Python's OFFLINE flickers: a dead robot's
     * end-of-tick status often reads BLOCKED, so the cache alone would show it "recovering" and "breaking" every few ticks.
     */
    private void latchBrokenDownRobots(int tick) {
        for (String robotId : liveRobotIds) {
            Optional<RobotStateDto> robot = robotCacheService.get(robotId);
            if (robot.isEmpty() || !"OFFLINE".equals(robot.get().status)) {
                continue;
            }
            Integer ignoreUntil = ignoreOfflineUntilTick.get(robotId);
            if (ignoreUntil != null && tick <= ignoreUntil) {
                continue;
            }
            if (brokenDown.add(robotId)) {
                log.warn("Product session {}: robot {} is broken down (reported OFFLINE)", sessionId, robotId);
                try {
                    emitEvent("ROBOT_BROKEN_DOWN", tick, orderedMap("robotId", robotId));
                } catch (RuntimeException e) {
                    log.warn("Product session {}: could not record ROBOT_BROKEN_DOWN for {}: {}", sessionId, robotId, e.getMessage());
                }
            }
        }
    }

    /**
     * "Mark as fixed": recover a broken-down robot. Asks Python to clear the robot's sensor fault and reset it to IDLE where
     * it stopped (POST /control/recover); on success removes the label and opens the re-latch ignore window. The robot then
     * becomes selectable by the existing allocator on its next IDLE telemetry - nothing is assigned here. Throws
     * IllegalArgumentException (HTTP 400) if there is no running session, the robot is not one of this session's, or it is
     * not currently broken down; a Python failure propagates as SimulationEngineException and leaves the label in place.
     */
    public void fixRobot(String robotId) {
        if (!running) {
            throw new IllegalArgumentException("No product session running.");
        }
        if (robotId == null || !liveRobotIds.contains(robotId)) {
            throw new IllegalArgumentException("Unknown robot '" + robotId + "' for this product session.");
        }
        if (!brokenDown.contains(robotId)) {
            throw new IllegalArgumentException("Robot '" + robotId + "' is not broken down.");
        }
        simulationClient.recoverRobot(robotId);
        int tick = robotCacheService.lastTick();
        ignoreOfflineUntilTick.put(robotId, tick + RELATCH_IGNORE_TICKS);
        brokenDown.remove(robotId);
        log.info("Product session {}: robot {} marked as fixed (recovery requested)", sessionId, robotId);
        try {
            emitEvent("ROBOT_FIXED", tick, orderedMap("robotId", robotId));
        } catch (RuntimeException e) {
            log.warn("Product session {}: could not record ROBOT_FIXED for {}: {}", sessionId, robotId, e.getMessage());
        }
    }

    private boolean isCurrentSessionRobot(String robotId) {
        return robotId != null && robotId.startsWith("PR") && liveRobotIds.contains(robotId);
    }

    private static boolean positionEquals(PositionDto a, PositionDto b) {
        return a != null && b != null && a.x == b.x && a.y == b.y;
    }

    // ── Seeded, tick-driven task order generation ───────────────────────

    private void maybeGenerateTask(int tick) {
        if (tick < nextTaskGenerationTick) {
            return;
        }
        long inFlight = tracked.values().stream().filter(t -> !t.completed).count();
        if (inFlight >= MAX_BACKLOG) {
            nextTaskGenerationTick = tick + TASK_RETRY_TICKS;
            return;
        }
        WarehouseMapDto map = warehouseCacheService.get();
        if (map == null || map.pickupPoints == null || map.pickupPoints.isEmpty()
                || map.dropPoints == null || map.dropPoints.isEmpty()) {
            // Real map not pushed yet (ProductSession pushes it at the very
            // start of its own run — see simulation/product/session.py) —
            // never fabricate placeholder pickup/drop geometry.
            nextTaskGenerationTick = tick + TASK_RETRY_TICKS;
            return;
        }

        PositionDto pickup = map.pickupPoints.get(taskRng.nextInt(map.pickupPoints.size()));
        List<PositionDto> candidateDrops = unoccupiedDropPoints(map.dropPoints);
        PositionDto drop = candidateDrops.get(taskRng.nextInt(candidateDrops.size()));
        int priority = 1 + taskRng.nextInt(5);
        String taskId = "task_" + sessionId + "_" + taskSeq.incrementAndGet();

        TaskDto dto = new TaskDto();
        dto.taskId = taskId;
        dto.pickupPosition = pickup;
        dto.dropPosition = drop;
        dto.priority = priority;
        dto.status = "PENDING";
        dto.createdAtTick = tick;
        taskRepository.save(TaskEntity.fromDto(dto));

        // Reuse the EXISTING, unmodified allocator — the same call
        // TaskController.createTask() already makes right after creating a
        // task. No new TaskAllocationService method; this only shortens the
        // latency until assignment (it would happen anyway on the next
        // telemetry batch via TelemetryIngestController, unchanged).
        taskAllocationService.allocatePendingTasks();

        tracked.put(taskId, new TrackedTask(taskId, pickup, drop, priority));
        createdCount.incrementAndGet();
        emitEvent("TASK_CREATED", tick, orderedMap(
                "taskId", taskId, "pickupPosition", posMap(pickup), "dropPosition", posMap(drop), "priority", priority));

        nextTaskGenerationTick = tick + TASK_MIN_INTERVAL_TICKS + taskRng.nextInt(TASK_INTERVAL_JITTER_TICKS + 1);
    }

    /**
     * Never send a robot to a drop cell that is already taken: a cell a robot of this session is
     * standing on, or the drop cell of a task that is still open. A robot that finished a task
     * stays parked on its drop cell, and a robot heading to an occupied destination can never
     * enter it (the agent's physical guard refuses to step onto a stationary peer), so the task
     * stalls until it is abandoned. In a 60-seed x 2000-tick model this alone took abandonment
     * from 57%/41% to 37%/22.5% (fault-free / faults on) and removed almost all dead stretches
     * (docs/PRODUCT_MODE_INVESTIGATION_STATUS.md, 10.6 and 10.7). If EVERY drop cell is taken the
     * full list is used, so generation never stalls on this rule.
     */
    private List<PositionDto> unoccupiedDropPoints(List<PositionDto> dropPoints) {
        Set<Long> taken = new HashSet<>();
        for (RobotStateDto robot : robotCacheService.values()) {
            if (isCurrentSessionRobot(robot.robotId) && robot.position != null) {
                taken.add(cellKey(robot.position));
            }
        }
        for (TrackedTask t : tracked.values()) {
            if (!t.completed && t.dropPosition != null) {
                taken.add(cellKey(t.dropPosition));
            }
        }
        List<PositionDto> free = new ArrayList<>();
        for (PositionDto d : dropPoints) {
            if (!taken.contains(cellKey(d))) {
                free.add(d);
            }
        }
        return free.isEmpty() ? dropPoints : free;
    }

    private static long cellKey(PositionDto p) {
        return ((long) p.x << 32) | (p.y & 0xffffffffL);
    }

    // ── Event emission (payload-only tagging — see Phase 0 finding: no
    // runId/sessionId column exists on EventEntity, and none is added here) ─

    private void emitEvent(String type, int tick, Map<String, Object> payload) {
        payload.put("sessionId", sessionId);
        payload.put("origin", "SYSTEM");
        SimulationEventDto dto = new SimulationEventDto();
        dto.eventId = "evt_" + sessionId + "_" + UUID.randomUUID();
        dto.type = type;
        dto.tick = tick;
        dto.payload = payload;
        try {
            eventRepository.save(EventEntity.fromDto(dto));
        } catch (RuntimeException e) {
            // The backend's SQLite file is routinely "database is locked" under telemetry load. The live feed must not lose the
            // event because the history write failed (the Product tab's feed is built from this broadcast), so log and still
            // broadcast; only the persisted copy is missing.
            log.warn("Product session {}: could not persist {} event ({}); broadcasting it anyway", sessionId, type, e.getMessage());
        }
        broadcaster.broadcastEvent(tick, dto);
    }

    private static Map<String, Object> posMap(PositionDto p) {
        return p == null ? null : Map.of("x", p.x, "y", p.y);
    }

    private static Map<String, Object> orderedMap(Object... kv) {
        Map<String, Object> m = new LinkedHashMap<>();
        for (int i = 0; i < kv.length; i += 2) {
            m.put((String) kv[i], kv[i + 1]);
        }
        return m;
    }
}
