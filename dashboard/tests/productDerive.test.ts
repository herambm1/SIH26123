// Unit tests for the Product tab's pure derivations. Run: `node --test tests/` from dashboard/ (Node 22.18+/24 strips the types itself;
// no test framework is installed in this project). Kept outside src/ so `tsc` (which has no @types/node) does not see it.
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  buildFeed,
  deriveKpis,
  deriveRoster,
  describeEvent,
  feedCounts,
  isCollisionEvent,
  latestVerdictByRobot,
  robotsForMap,
} from '../src/components/product/productDerive.ts';
import type { RobotState, SimulationEvent } from '../src/types/contracts.ts';
import type { ProductSessionStatus } from '../src/types/product.ts';

const robot = (id: string, status: RobotState['status'], extra: Partial<RobotState> = {}): RobotState => ({
  robotId: id,
  position: { x: 1, y: 2 },
  velocity: 0,
  battery: 100,
  currentTaskId: null,
  destination: null,
  currentPath: [],
  status,
  timestamp: 5,
  ...extra,
});

const ev = (eventId: string, type: string, tick: number, payload: Record<string, unknown> = {}): SimulationEvent => ({ eventId, type, tick, payload });

const status = (over: Partial<ProductSessionStatus> = {}): ProductSessionStatus => ({
  running: true,
  sessionId: 's1',
  seed: 7,
  currentTick: 10,
  tasksCreated: 10,
  tasksInProgress: 8,
  tasksCompleted: 4,
  tasksReassigned: 0,
  tasksPendingOrAssigned: 1,
  tasksFailed: 2,
  brokenDownRobots: [],
  ...over,
});

describe('deriveKpis', () => {
  it('splits open tasks into active and pending, never negative', () => {
    const k = deriveKpis(status(), [], []);
    assert.equal(k.completed, 4);
    assert.equal(k.abandoned, 2);
    assert.equal(k.pending, 1);
    assert.equal(k.active, 10 - 4 - 2 - 1); // created - completed - abandoned - pending
    assert.equal(deriveKpis(status({ tasksCreated: 0, tasksCompleted: 3, tasksPendingOrAssigned: 5 }), [], []).active, 0);
  });

  it('is all zeros with no session', () => {
    const k = deriveKpis(null, [], []);
    assert.deepEqual(k, { completed: 0, active: 0, pending: 0, abandoned: 0, activeConflicts: 0, collisions: 0, brokenDown: 0 });
  });

  it('counts referee collisions only from CONFLICT_DETECTED with collision=true, once each', () => {
    const events = [
      ev('a', 'CONFLICT_DETECTED', 3, { collision: true, robotIds: ['PR1', 'PR2'] }),
      ev('b', 'CONFLICT_DETECTED', 4, { collision: false }),
      ev('c', 'CONFLICT_DETECTED', 5, { collision: true, robotIds: ['PR3', 'PR4'] }),
      ev('d', 'NEGOTIATION', 5, { robotId: 'PR1', resolutionAction: 'WAIT' }),
    ];
    assert.equal(deriveKpis(status(), events, []).collisions, 2);
    assert.equal(isCollisionEvent(events[1]), false);
  });

  it('counts an active conflict only for a robot that is waiting/blocked AND whose latest verdict is not CONTINUE', () => {
    const events = [
      ev('1', 'NEGOTIATION', 2, { robotId: 'PR1', resolutionAction: 'WAIT' }),
      ev('2', 'NEGOTIATION', 3, { robotId: 'PR2', resolutionAction: 'WAIT' }),
      ev('3', 'NEGOTIATION', 6, { robotId: 'PR2', resolutionAction: 'CONTINUE' }), // PR2 was cleared
      ev('4', 'NEGOTIATION', 4, { robotId: 'PR3', resolutionAction: 'YIELD' }),
    ];
    const robots = [robot('PR1', 'WAITING'), robot('PR2', 'WAITING'), robot('PR3', 'MOVING'), robot('PR4', 'WAITING')];
    // PR1 yes; PR2 latest verdict CONTINUE -> no; PR3 not waiting -> no; PR4 waiting but no verdict -> no
    assert.equal(deriveKpis(status(), events, robots).activeConflicts, 1);
  });

  it('never counts a broken-down robot as an active conflict, and reports the broken-down count', () => {
    const events = [ev('1', 'NEGOTIATION', 2, { robotId: 'PR1', resolutionAction: 'REASSIGN_TASK' })];
    const k = deriveKpis(status({ brokenDownRobots: ['PR1'] }), events, [robot('PR1', 'BLOCKED')]);
    assert.equal(k.activeConflicts, 0);
    assert.equal(k.brokenDown, 1);
  });
});

describe('latestVerdictByRobot', () => {
  it('the later tick wins per robot', () => {
    const m = latestVerdictByRobot([
      ev('1', 'NEGOTIATION', 9, { robotId: 'PR1', resolutionAction: 'YIELD' }),
      ev('2', 'NEGOTIATION', 4, { robotId: 'PR1', resolutionAction: 'WAIT' }),
    ]);
    assert.equal(m.get('PR1'), 'YIELD');
  });
});

describe('deriveRoster / robotsForMap', () => {
  const robots = [robot('PR10', 'MOVING'), robot('PR2', 'BLOCKED', { currentTaskId: 'task_product_x_7', destination: { x: 9, y: 9 }, currentPath: [{ x: 2, y: 2 }] })];

  it('sorts numerically by robot id and carries task/destination/path info', () => {
    const rows = deriveRoster(robots, [], []);
    assert.deepEqual(rows.map((r) => r.robotId), ['PR2', 'PR10']);
    assert.equal(rows[0].taskId, 'task_product_x_7');
    assert.deepEqual(rows[0].destination, { x: 9, y: 9 });
    assert.equal(rows[0].pathRemaining, 1);
  });

  it('shows a latched broken-down robot as BROKEN_DOWN whatever its flickering reported status is', () => {
    const rows = deriveRoster(robots, ['PR2'], []);
    assert.equal(rows[0].status, 'BROKEN_DOWN');
    assert.equal(rows[0].reportedStatus, 'BLOCKED');
    assert.equal(rows[1].status, 'MOVING');
  });

  it('draws a broken-down robot with the OFFLINE marker and leaves the input untouched', () => {
    const drawn = robotsForMap(robots, ['PR2']);
    assert.equal(drawn.find((r) => r.robotId === 'PR2')?.status, 'OFFLINE');
    assert.equal(robots[1].status, 'BLOCKED');
    assert.equal(robotsForMap(robots, []), robots);
  });
});

describe('describeEvent / buildFeed', () => {
  it('hides per-tick COMM_FLOW and the duplicate task lines', () => {
    assert.equal(describeEvent(ev('1', 'COMM_FLOW', 1, { records: [] })), null);
    assert.equal(describeEvent(ev('2', 'TASK_PUSHED_TO_ENGINE', 1, { taskId: 't_1' })), null);
    assert.equal(describeEvent(ev('3', 'TASK_STATUS_CHANGED', 1, { toStatus: 'COMPLETED', taskId: 't_1' })), null);
  });

  it('describes negotiation, task, fault and collision events with the right category and color', () => {
    const neg = describeEvent(ev('n', 'NEGOTIATION', 5, { robotId: 'PR1', peerRobotId: 'PR2', resolutionAction: 'YIELD', conflictType: 'NARROW_AISLE_HEADON', contestedCell: { x: 3, y: 4 } }));
    assert.equal(neg?.category, 'NEGOTIATION');
    assert.equal(neg?.label, 'YIELD');
    assert.match(neg?.text ?? '', /PR1 re PR2 at \(3,4\) \[narrow aisle headon\]/);

    const done = describeEvent(ev('d', 'TASK_COMPLETED', 9, { robotId: 'PR3', taskId: 'task_product_abc_12' }));
    assert.equal(done?.category, 'TASK');
    assert.match(done?.text ?? '', /PR3 completed #12/);

    const off = describeEvent(ev('o', 'ROBOT_UNAVAILABLE', 9, { robotId: 'PR5' }));
    assert.equal(off?.category, 'FAULT');

    const abandoned = describeEvent(ev('a', 'TASK_STATUS_CHANGED', 9, { toStatus: 'FAILED', taskId: 't_4', robotId: 'PR1', reason: 'no progress for 30 ticks' }));
    assert.equal(abandoned?.label, 'ABANDONED');

    const col = describeEvent(ev('c', 'CONFLICT_DETECTED', 9, { collision: true, robotIds: ['PR1', 'PR2'], cumulativeCollisionCount: 3 }));
    assert.equal(col?.category, 'COLLISION');
    assert.equal(col?.color, 'var(--error)');
    assert.match(col?.text ?? '', /PR1 x PR2/);
  });

  it('reads an aisle-block cell whether it arrives as an {x,y} object or as a [x,y] array', () => {
    assert.match(describeEvent(ev('b1', 'AISLE_BLOCKED', 3, { cell: [4, 7], manual: false }))?.text ?? '', /cell \(4,7\)/);
    assert.match(describeEvent(ev('b2', 'AISLE_CLEARED', 9, { cell: { x: 4, y: 7 } }))?.text ?? '', /cell \(4,7\)/);
    assert.match(describeEvent(ev('b3', 'AISLE_BLOCKED', 3, {}))?.text ?? '', /cell \?/);
  });

  const events = [
    ev('1', 'NEGOTIATION', 1, { robotId: 'PR1', resolutionAction: 'WAIT', sessionId: 's1' }),
    ev('2', 'TASK_CREATED', 2, { taskId: 'task_product_s1_1', priority: 3, dropPosition: { x: 1, y: 1 }, sessionId: 's1' }),
    ev('3', 'COMM_FLOW', 3, { sessionId: 's1' }),
    ev('4', 'ROBOT_BROKEN_DOWN', 4, { robotId: 'PR2', sessionId: 's1' }),
    ev('5', 'NEGOTIATION', 5, { robotId: 'PR9', resolutionAction: 'WAIT', sessionId: 'OLD' }), // a previous session's late event
  ];

  it('newest first, filtered by category, and drops another session\'s events', () => {
    const all = buildFeed(events, 'ALL', 's1');
    assert.deepEqual(all.map((l) => l.eventId), ['4', '2', '1']);
    assert.deepEqual(buildFeed(events, 'NEGOTIATION', 's1').map((l) => l.eventId), ['1']);
    assert.deepEqual(buildFeed(events, 'FAULTS', 's1').map((l) => l.eventId), ['4']);
    assert.deepEqual(buildFeed(events, 'COLLISIONS', 's1'), []);
    assert.equal(buildFeed(events, 'ALL', null).length, 4); // no session known yet: nothing is dropped
  });

  it('caps the number of lines and counts per filter chip', () => {
    assert.equal(buildFeed(events, 'ALL', 's1', 2).length, 2);
    assert.deepEqual(feedCounts(events, 's1'), { ALL: 3, NEGOTIATION: 1, TASKS: 1, FAULTS: 1, COLLISIONS: 0 });
  });
});
