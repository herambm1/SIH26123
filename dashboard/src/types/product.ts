// dashboard/src/types/product.ts
//
// Product-mode (live, seeded, exploratory session) response shapes. NOT shared/python/models.py contracts and NOT part of
// contracts.ts: they mirror backend/.../model/ProductSessionStatusDto and ProductController's ack bodies, inspected directly.
// A Java-side "broken down" overlay (brokenDownRobots) deliberately is NOT a RobotState.status value.

/** GET /api/product/session */
export interface ProductSessionStatus {
  running: boolean;
  sessionId: string | null;
  seed: number | null;
  currentTick: number;
  /** LIFETIME counters (never decremented). */
  tasksCreated: number;
  tasksInProgress: number;
  tasksCompleted: number;
  tasksReassigned: number;
  /** Live snapshot: open tasks not yet pushed to a robot (still PENDING / assigned-but-not-pushed). */
  tasksPendingOrAssigned: number;
  /** Abandoned tasks (stalled robot, or repeatedly assigned to a non-live robot). */
  tasksFailed: number;
  /** Robots latched as broken down (ROBOT_OFFLINE) until "Mark as fixed". Sorted. */
  brokenDownRobots: string[];
}

/** POST /api/product/session/start */
export interface ProductStartAck {
  message: string;
  sessionId: string;
  seed: number;
  robotCount: number;
  speed: string;
}

export type ProductSpeedMultiplier = 1 | 2 | 4;
