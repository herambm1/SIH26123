# simulation/scenarios package
# Owner: Member 3

from dataclasses import dataclass, field
from typing import Any
from shared.python.models import Position, WarehouseMap


@dataclass
class Scenario:
    scenario_id: str
    name: str
    description: str
    robots: list[dict]  # list of {"robotId": str, "start": Position, "goal": Position, "priority": int}
    warehouse_map: WarehouseMap
    max_ticks: int = 100
    events: list[dict] = field(default_factory=list)  # [{"tick": int, "type": str, "payload": dict}]
    fault_config: dict = field(default_factory=dict)





def list_scenarios() -> list[str]:
    """Return all 8 supported scenario IDs."""
    return [
        "a_normal",
        "b_intersection",
        "c_narrow_aisle",
        "d_deadlock",
        "e_blocked_aisle",
        "f_task_reassignment",
        "g_high_load",
        "h_negative_control",
    ]


def get_scenario(scenario_id: str, seed: int = 42, warehouse_map: WarehouseMap | None = None) -> Scenario:
    """Load a Scenario by scenario_id (e.g. 'a_normal' or 'a')."""
    sid = scenario_id.lower().strip()
    # Normalize short names like "a" or "b"
    id_map = {
        "a": "a_normal",
        "b": "b_intersection",
        "c": "c_narrow_aisle",
        "d": "d_deadlock",
        "e": "e_blocked_aisle",
        "f": "f_task_reassignment",
        "g": "g_high_load",
        "h": "h_negative_control",
    }
    normalized = id_map.get(sid, sid)

    if normalized == "a_normal":
        from simulation.scenarios.a_normal import get_scenario as load_a
        return load_a(seed, warehouse_map=warehouse_map)
    elif normalized == "b_intersection":
        from simulation.scenarios.b_intersection import get_scenario as load_b
        return load_b(seed, warehouse_map=warehouse_map)
    elif normalized == "c_narrow_aisle":
        from simulation.scenarios.c_narrow_aisle import get_scenario as load_c
        return load_c(seed, warehouse_map=warehouse_map)
    elif normalized == "d_deadlock":
        from simulation.scenarios.d_deadlock import get_scenario as load_d
        return load_d(seed, warehouse_map=warehouse_map)
    elif normalized == "e_blocked_aisle":
        from simulation.scenarios.e_blocked_aisle import get_scenario as load_e
        return load_e(seed, warehouse_map=warehouse_map)
    elif normalized == "f_task_reassignment":
        from simulation.scenarios.f_task_reassignment import get_scenario as load_f
        return load_f(seed, warehouse_map=warehouse_map)
    elif normalized == "g_high_load":
        from simulation.scenarios.g_high_load import get_scenario as load_g
        return load_g(seed, warehouse_map=warehouse_map)
    elif normalized == "h_negative_control":
        from simulation.scenarios.h_negative_control import get_scenario as load_h
        return load_h(seed, warehouse_map=warehouse_map)
    else:
        raise ValueError(f"Unknown scenario ID: {scenario_id}. Supported: {list_scenarios()}")
