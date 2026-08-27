# 02 — Robot Communication — Implementation Specification
**Member 2 · Synced with `SIH_26123_Project_Overview.md` v2 · Canonical contracts: `docs/00_SHARED_CONTRACTS.md` / `shared/python/models.py`**

---

## 1. Module Purpose

You build the peer-to-peer message layer that lets robot agents share intent and negotiate conflicts without a central per-tick arbiter. This is what makes the "decentralized" architecture claim real, testable, and demonstrable — including by killing the Java backend mid-demo and showing robots still avoid each other.

## 2. System Context

```text
React Dashboard ──REST/WS──▶ Java Backend ──REST(control)──▶ Python Sim Engine
                                    ▲                                │
                                    └────────REST(data push)─────────┘

Inside the Python Sim Engine, per tick, per robot:
  Edge → RobotAgent.tick() → Planner → [ YOU: broadcast/receive ] → Coordination
```
Default transport is an **in-process publish/subscribe bus**, not real network sockets. A live SIH demo on unfamiliar venue Wi-Fi is a real failure risk; the bus is deterministic and reliable while still enforcing the decentralization property — agents only ever see each other through explicit messages, never shared memory/global state.

## 3. Your Place in the Architecture

```text
RobotState (per robot, this tick)
      ↓
build_intent_message() (you)
      ↓
InProcessBus.broadcast() (you)
      ↓
InProcessBus.receive() (you, called by every other robot's agent)
      ↓
ConflictDetector.detect() (Member 3, reads what you deliver)
```

## 4. What You Own

```text
robot_agent/communication/transport.py   — Transport ABC, InProcessBus, MessageFaultConfig
robot_agent/communication/messages.py    — build_intent_message()
robot_agent/tests/test_communication.py
```

## 5. Reads / Consumes

`RobotState` (from the calling robot agent, to build an outgoing intent message).

## 6. Produces

Intent messages on the bus (dicts, not a formally separate contract type — derived from `RobotState`); delivered/received message lists, consumed directly inside Member 3's `tick()`.

## 7. Must Not Modify

`robot_agent/agent.py` (Member 3), `collision_engine/` (Member 3), `planner/` (Member 1), `edge/` (Member 5), `backend/`, `dashboard/`.

## 8. Complete Responsibilities & Implementation Requirements

**8.1 Transport interface and default implementation.** Define an abstract `Transport` so a real network implementation (UDP/WebSocket) can be swapped in later for the optional hardware bonus demo without touching any caller's code. Default: `InProcessBus`, a simple per-robot queue (dict of `robotId -> list[dict]`), thread-safe if the simulation ever runs agents concurrently (it may not for the MVP — single-threaded tick loop is fine and simpler; document this assumption clearly rather than silently assuming concurrency).

**8.2 Intent message format.** Not a new named contract — a JSON-serializable subset of `RobotState`: `robotId, position, destination, plannedPath, currentTask, priority, battery, status, timestamp`. `plannedPath` is `RobotPath.waypoints` (space-time), which is what lets receivers do windowed-replanning-style conflict prediction.

**8.3 Robot discovery.** Trivial in the in-process bus — all registered robot IDs are known at simulation start (from the scenario definition). No dynamic discovery protocol needed for the MVP.

**8.4 Fault injection.** `MessageFaultConfig(drop_rate: float, delay_ticks: int)`. Dropped messages simply never appear in the recipient's `receive()` result for that tick; delayed messages are queued and released after `delay_ticks` have passed. This directly powers the deadlock-recovery and resilience demo scenarios — treat it as a real feature, not decoration.

**8.5 Optional/stretch: real transport.** `UDPTransport` or `WebSocketTransport` behind the same `Transport` interface, for the isolated hardware bonus segment only. Never required by the core demo.

## 9. Exact Interfaces

```python
# robot_agent/communication/transport.py
from abc import ABC, abstractmethod

class Transport(ABC):
    @abstractmethod
    def send(self, to: str, msg: dict) -> None: ...
    @abstractmethod
    def broadcast(self, msg: dict) -> None: ...
    @abstractmethod
    def receive(self, robot_id: str) -> list[dict]: ...

class MessageFaultConfig:
    def __init__(self, drop_rate: float = 0.0, delay_ticks: int = 0): ...

class InProcessBus(Transport):
    def __init__(self, robot_ids: list[str], fault_config: MessageFaultConfig | None = None): ...
    def advance_tick(self) -> None:
        """Call once per simulation tick to release delayed messages."""

# robot_agent/communication/messages.py
def build_intent_message(state: RobotState) -> dict:
    """Extracts robotId, position, destination, plannedPath, currentTask,
    priority, battery, status, timestamp from a RobotState."""
```

## 10. How My Module Affects Other Modules

```text
Robot Communication
    ↓
delivered intent messages → Coordination (Member 3): input to ConflictDetector.detect()
    ↓
delivered intent messages → Planner (Member 1): input to windowed replanning (avoid_intervals)
    ↓
message drop/delay behavior → demo scenarios (Member 3): what makes the deadlock/resilience
    scenarios interesting to run in the first place
```

## 11. How Other Modules Affect My Module

```text
RobotState (Robot Agent, Member 3)
    → the data you serialize into every outgoing intent message
Scenario fault-injection config (Member 3's scenario definitions)
    → which MessageFaultConfig profile to apply for a given demo scenario
```

## 12. Integration Points

| My Module | Other Module | Data/Interface | Direction | Purpose |
|---|---|---|---|---|
| Communication | Coordination | intent messages (dicts) | Communication → Coordination | Conflict detection input |
| Communication | Planner | intent messages (dicts) | Communication → Planner | Windowed replanning input |
| Robot Agent | Communication | `RobotState` | Robot Agent → Communication | Build outgoing intent |
| Scenarios | Communication | `MessageFaultConfig` | Scenarios → Communication | Fault injection setup |

## 13. Failure / Missing-Dependency Behavior

- **No `RobotState` yet** (Member 3's agent not built): build and test with a fabricated `RobotState` — you don't need the real one.
- **`receive()` returns empty** (no peers broadcast this tick, or all dropped by fault injection): this is a normal, expected state, not an error — callers (Planner, Coordination) already treat "no peer intents" as valid input.
- **A robot ID isn't registered on the bus**: raise a clear `UnknownRobotError` at `send()`/`broadcast()` time rather than silently dropping.

## 14. Mock-First Development

| Real dependency | Mock while developing | Integration replacement |
|---|---|---|
| Real `RobotState` from Robot Agent | 2–3 hardcoded fake agent objects, each holding a static `RobotState` | Swap the fake agents for real `RobotAgent` instances; `Transport` interface unchanged |
| Real fault-injection scenario config | Manually construct a `MessageFaultConfig` in a test | Same constructor, different config source |

You need nothing from anyone else to build and fully test this module.

## 15. Testing Strategy

- Unit test: `InProcessBus` delivers a broadcast message to all registered robots except the sender.
- Fault injection test: with `drop_rate=1.0`, confirm zero messages delivered; with `delay_ticks=3`, confirm a message appears only after 3 calls to `advance_tick()`.
- Run standalone: 2–3 fabricated agent objects exchanging hardcoded messages, printed to console — no other module needed.

## 16. AI Coding Boundary

> You own `robot_agent/communication/`. Do not modify `robot_agent/agent.py`, `collision_engine/`, `planner/`, `edge/`, `backend/`, or `dashboard/` — if something in `agent.py` looks wrong when integrating, flag it to Member 3 rather than fixing it. Keep the `Transport` interface (`send`, `broadcast`, `receive`) stable — other modules call it directly and shouldn't need to change if the implementation changes. Import contracts from `shared/python/models.py`. Inspect existing code before modifying. Show diffs. Write tests, including for the fault-injection modes. Don't restructure the repository.

## 17. Definition of Done

- `InProcessBus` reliably delivers messages between multiple fabricated agents, unit-tested.
- `MessageFaultConfig` (drop rate, delay) is configurable and behaviorally verified by tests.
- `build_intent_message()` produces a schema-correct subset of `RobotState`.
- `Transport` interface is clean enough that a real UDP/WebSocket implementation could be substituted without any caller changing.
