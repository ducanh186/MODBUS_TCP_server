"""
SmartLogger (PMS) register definitions — Huawei address map.

Source: Huawei SmartLogger ModBus Interface Definitions (Issue 35, 2020-02-20)

Address map (Holding Registers only — FC03 read, FC06/FC10 write):
  40420-40429  Control block (active/reactive adjustment, power factor)
  40521-40577  Telemetry block (input power, CO2, active power, voltages, currents)
  40713-40722  Identity block (ESN string)
  50000-50001  Alarm block (SmartLogger alarm bitfields)

No Input Registers — SmartLogger uses HR for everything.

Simulator note:
  HR 40424-40425 repurposed as "direction" register (simulator extension):
    0 = discharge (+kW), 1 = charge (-kW).
  In real SmartLogger, 40424 is "Active adjustment (alternative)" U32 kW gain=10.
  Client must write both HR 40420 (magnitude) and HR 40424 (direction) to set demand.
"""

from __future__ import annotations

import sys
import os
from typing import Any, Dict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tcp_servers"))
from register_codec import encode_block

# =========================================================================
# Block 1: Control (40420-40429, 10 regs) — RW (HR)
# =========================================================================

CONTROL_POINTS = [
    {"name": "active_adj",       "address": 40420, "quantity": 2, "dtype": "U32", "gain": 10,   "unit": "kW",   "access": "RW"},
    {"name": "reactive_adj",     "address": 40422, "quantity": 2, "dtype": "I32", "gain": 10,   "unit": "kVar", "access": "RW"},
    # Simulator extension: direction flag (0=discharge, 1=charge)
    # In real spec this is "Active adjustment (alternative)" U32 kW gain=10
    {"name": "demand_direction", "address": 40424, "quantity": 1, "dtype": "U16", "gain": 1,    "unit": "-",    "access": "RW"},
    # 40425 reserved (was part of U32 40424-40425 in real spec)
    {"name": "reactive_adj_alt", "address": 40426, "quantity": 2, "dtype": "I32", "gain": 10,   "unit": "kVar", "access": "RW"},
    {"name": "active_pct",       "address": 40428, "quantity": 1, "dtype": "U16", "gain": 10,   "unit": "%",    "access": "RW"},
    {"name": "power_factor",     "address": 40429, "quantity": 1, "dtype": "I16", "gain": 1000, "unit": "-",    "access": "RW"},
]

CONTROL_RANGE_START = 40420
CONTROL_RANGE_SIZE = 10  # 40420..40429

# =========================================================================
# Block 2: Telemetry (40521-40577, 57 regs) — RO (HR)
# =========================================================================

TELEMETRY_POINTS = [
    {"name": "input_power",    "address": 40521, "quantity": 2, "dtype": "U32", "gain": 1000, "unit": "kW",  "access": "RO"},
    {"name": "co2_reduction",  "address": 40523, "quantity": 2, "dtype": "U32", "gain": 10,   "unit": "kg",  "access": "RO"},
    {"name": "active_power",   "address": 40525, "quantity": 2, "dtype": "I32", "gain": 1000, "unit": "kW",  "access": "RO"},
    # 40527-40531: gap (reserved)
    {"name": "power_factor",   "address": 40532, "quantity": 1, "dtype": "I16", "gain": 1000, "unit": "-",   "access": "RO"},
    # 40533-40543: gap
    {"name": "reactive_power", "address": 40544, "quantity": 2, "dtype": "I32", "gain": 1000, "unit": "kVar", "access": "RO"},
    # 40546-40559: gap
    {"name": "e_total",        "address": 40560, "quantity": 2, "dtype": "U32", "gain": 10,   "unit": "kWh", "access": "RO"},
    {"name": "e_daily",        "address": 40562, "quantity": 2, "dtype": "U32", "gain": 10,   "unit": "kWh", "access": "RO"},
    # 40564-40571: gap
    {"name": "phase_curr_a",   "address": 40572, "quantity": 1, "dtype": "I16", "gain": 1,    "unit": "A",   "access": "RO"},
    {"name": "phase_curr_b",   "address": 40573, "quantity": 1, "dtype": "I16", "gain": 1,    "unit": "A",   "access": "RO"},
    {"name": "phase_curr_c",   "address": 40574, "quantity": 1, "dtype": "I16", "gain": 1,    "unit": "A",   "access": "RO"},
    {"name": "volt_uab",       "address": 40575, "quantity": 1, "dtype": "U16", "gain": 10,   "unit": "V",   "access": "RO"},
    {"name": "volt_ubc",       "address": 40576, "quantity": 1, "dtype": "U16", "gain": 10,   "unit": "V",   "access": "RO"},
    {"name": "volt_uca",       "address": 40577, "quantity": 1, "dtype": "U16", "gain": 10,   "unit": "V",   "access": "RO"},
]

TELEMETRY_RANGE_START = 40521
TELEMETRY_RANGE_SIZE = 57  # 40521..40577

# =========================================================================
# Block 3: Identity (40713-40722, 10 regs) — RO (HR)
# =========================================================================

IDENTITY_POINTS = [
    {"name": "esn", "address": 40713, "quantity": 10, "dtype": "STR", "gain": 1, "unit": "-", "access": "RO"},
]

IDENTITY_RANGE_START = 40713
IDENTITY_RANGE_SIZE = 10  # 40713..40722

# =========================================================================
# Block 4: Alarm (50000-50001, 2 regs) — RO (HR)
# =========================================================================

ALARM_POINTS = [
    {"name": "alarm_info_1", "address": 50000, "quantity": 1, "dtype": "U16", "gain": 1, "unit": "-", "access": "RO"},
    {"name": "alarm_info_2", "address": 50001, "quantity": 1, "dtype": "U16", "gain": 1, "unit": "-", "access": "RO"},
]

ALARM_RANGE_START = 50000
ALARM_RANGE_SIZE = 2  # 50000..50001

# =========================================================================
# Key addresses used by controller
# =========================================================================

# Control (writable by client)
ADDR_ACTIVE_ADJ        = 40420  # U32, gain=10, kW — demand magnitude
ADDR_DEMAND_DIRECTION  = 40424  # U16, 0=discharge, 1=charge (simulator extension)

# Telemetry (written by controller)
ADDR_ACTIVE_POWER      = 40525  # I32, gain=1000, kW — total active power aggregate

# Alarm (written by controller)
ADDR_ALARM_1           = 50000  # U16, BMS alarm forwarding (bits 0-3 = BMS1, bits 8-11 = BMS2)
ADDR_ALARM_2           = 50001  # U16, reserved

# =========================================================================
# Default static values
# =========================================================================

PMS_DEFAULTS = {
    "active_adj": 0.0,          # kW — no demand at startup
    "demand_direction": 0,      # discharge
    "power_factor": 1.0,        # unity PF
    "esn": "SIMLOGGER001",      # ESN string
}


def build_static_init(
    overrides: Dict[str, Any] | None = None,
) -> Dict[int, int]:
    """Build {address: uint16_value} init dict for all HR ranges.

    Returns init_values suitable for MultiRangeDataBlock range tuples.
    """
    values = dict(PMS_DEFAULTS)
    if overrides:
        values.update(overrides)

    init: Dict[int, int] = {}

    # Control range (40420-40429)
    control_pvs = [(pt, values[pt["name"]]) for pt in CONTROL_POINTS if pt["name"] in values]
    control_regs = encode_block(CONTROL_RANGE_START, CONTROL_RANGE_SIZE, control_pvs)
    for i, v in enumerate(control_regs):
        if v != 0:
            init[CONTROL_RANGE_START + i] = v

    # Identity range (40713-40722) — ESN string
    id_pvs = [(pt, values[pt["name"]]) for pt in IDENTITY_POINTS if pt["name"] in values]
    id_regs = encode_block(IDENTITY_RANGE_START, IDENTITY_RANGE_SIZE, id_pvs)
    for i, v in enumerate(id_regs):
        if v != 0:
            init[IDENTITY_RANGE_START + i] = v

    return init
