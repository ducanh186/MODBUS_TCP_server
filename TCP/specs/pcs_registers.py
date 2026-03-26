"""
PCS2000HA register definitions — Full Huawei address map.

Source: Huawei PCS2000HA Smart PCS Modbus Port Definitions (Issue 03, 2025-04-03)

Address map (Input Registers — read-only, FC04):
  30000-30088  Identity + Rating           (89 regs, static, populated at init)
  32000-32013  Running status + Alarms     (14 regs, dynamic)
  32064-32090  Power readings              (27 regs, dynamic, controller updates)
  32463-32468  Battery cluster on PCS      (6 regs, dynamic)

Address map (Holding Registers — read/write, FC03/FC06):
  40039        Active power % scheduling   (1 reg, writable)
  40043-40044  Fixed active power setpoint (2 regs, I32, writable — used by PMS)

Legacy compatibility:
  HR  0-9      Legacy 0-based (HR0 = setpoint mirror)
  IR  0-9      Legacy 0-based (IR0 = active_power mirror)
"""

from __future__ import annotations

import sys
import os
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tcp_servers"))
from register_codec import encode_block

# =========================================================================
# Block 1: Identity (30000-30070, 71 regs) — STATIC (IR)
# =========================================================================

IDENTITY_POINTS = [
    {"name": "model",        "address": 30000, "quantity": 15, "dtype": "STR",  "gain": 1, "unit": "-",  "access": "RO"},
    {"name": "sn",           "address": 30015, "quantity": 10, "dtype": "STR",  "gain": 1, "unit": "-",  "access": "RO"},
    {"name": "pn",           "address": 30025, "quantity": 10, "dtype": "STR",  "gain": 1, "unit": "-",  "access": "RO"},
    {"name": "firmware_ver", "address": 30035, "quantity": 15, "dtype": "STR",  "gain": 1, "unit": "-",  "access": "RO"},
    {"name": "software_ver", "address": 30050, "quantity": 15, "dtype": "STR",  "gain": 1, "unit": "-",  "access": "RO"},
    {"name": "mac_address",  "address": 30065, "quantity": 3,  "dtype": "MAC",  "gain": 1, "unit": "-",  "access": "RO"},
    {"name": "protocol_ver", "address": 30068, "quantity": 2,  "dtype": "U32",  "gain": 1, "unit": "-",  "access": "RO"},
    {"name": "model_id",     "address": 30070, "quantity": 1,  "dtype": "U16",  "gain": 1, "unit": "-",  "access": "RO"},
]

# =========================================================================
# Block 2: Rating + Max reactive (30073-30088, 16 regs) — STATIC (IR)
# =========================================================================

RATING_POINTS = [
    {"name": "rated_power_pn",  "address": 30073, "quantity": 2, "dtype": "U32", "gain": 1000, "unit": "kW",   "access": "RO"},
    {"name": "max_active_pmax", "address": 30075, "quantity": 2, "dtype": "U32", "gain": 1000, "unit": "kW",   "access": "RO"},
    {"name": "max_apparent_s",  "address": 30077, "quantity": 2, "dtype": "U32", "gain": 1000, "unit": "kVA",  "access": "RO"},
    {"name": "qmax_fed_grid",   "address": 30079, "quantity": 2, "dtype": "I32", "gain": 1000, "unit": "kVar", "access": "RO"},
    {"name": "qmax_from_grid",  "address": 30081, "quantity": 2, "dtype": "I32", "gain": 1000, "unit": "kVar", "access": "RO"},
    {"name": "pmax_real",       "address": 30083, "quantity": 2, "dtype": "U32", "gain": 1000, "unit": "kW",   "access": "RO"},
    {"name": "smax_real",       "address": 30085, "quantity": 2, "dtype": "U32", "gain": 1000, "unit": "kVA",  "access": "RO"},
    {"name": "charge_power",    "address": 30087, "quantity": 2, "dtype": "U32", "gain": 1000, "unit": "kW",   "access": "RO"},
]

ALL_STATIC_POINTS = IDENTITY_POINTS + RATING_POINTS

# Merged range: 30000-30088 = 89 registers (gap at 30071-30072 = 0)
STATIC_RANGE_START = 30000
STATIC_RANGE_SIZE = 89  # 30000..30088 inclusive

# =========================================================================
# Block 3: Running status + Alarms (32000-32013, 14 regs) — DYNAMIC (IR)
# =========================================================================

STATUS_ALARM_POINTS = [
    {"name": "running_status", "address": 32000, "quantity": 1, "dtype": "Bitfield16", "gain": 1, "unit": "-", "access": "RO"},
    # 32001-32007: reserved gap (returns 0)
    {"name": "alarm_1",        "address": 32008, "quantity": 1, "dtype": "Bitfield16", "gain": 1, "unit": "-", "access": "RO"},
    {"name": "alarm_2",        "address": 32009, "quantity": 1, "dtype": "Bitfield16", "gain": 1, "unit": "-", "access": "RO"},
    {"name": "alarm_3",        "address": 32010, "quantity": 1, "dtype": "Bitfield16", "gain": 1, "unit": "-", "access": "RO"},
    {"name": "alarm_4",        "address": 32011, "quantity": 1, "dtype": "Bitfield16", "gain": 1, "unit": "-", "access": "RO"},
    {"name": "alarm_5",        "address": 32012, "quantity": 1, "dtype": "Bitfield16", "gain": 1, "unit": "-", "access": "RO"},
    {"name": "alarm_6",        "address": 32013, "quantity": 1, "dtype": "Bitfield16", "gain": 1, "unit": "-", "access": "RO"},
]

STATUS_RANGE_START = 32000
STATUS_RANGE_SIZE = 14  # 32000..32013

# =========================================================================
# Block 4: Power readings (32064-32090, 27 regs) — DYNAMIC (IR)
# =========================================================================

POWER_POINTS = [
    {"name": "dc_power",        "address": 32064, "quantity": 2, "dtype": "I32", "gain": 1000, "unit": "kW",   "access": "RO"},
    {"name": "line_volt_ab",    "address": 32066, "quantity": 1, "dtype": "U16", "gain": 10,   "unit": "V",    "access": "RO"},
    {"name": "line_volt_bc",    "address": 32067, "quantity": 1, "dtype": "U16", "gain": 10,   "unit": "V",    "access": "RO"},
    {"name": "line_volt_ca",    "address": 32068, "quantity": 1, "dtype": "U16", "gain": 10,   "unit": "V",    "access": "RO"},
    {"name": "phase_volt_a",    "address": 32069, "quantity": 1, "dtype": "U16", "gain": 10,   "unit": "V",    "access": "RO"},
    {"name": "phase_volt_b",    "address": 32070, "quantity": 1, "dtype": "U16", "gain": 10,   "unit": "V",    "access": "RO"},
    {"name": "phase_volt_c",    "address": 32071, "quantity": 1, "dtype": "U16", "gain": 10,   "unit": "V",    "access": "RO"},
    {"name": "phase_curr_a",    "address": 32072, "quantity": 2, "dtype": "I32", "gain": 1000, "unit": "A",    "access": "RO"},
    {"name": "phase_curr_b",    "address": 32074, "quantity": 2, "dtype": "I32", "gain": 1000, "unit": "A",    "access": "RO"},
    {"name": "phase_curr_c",    "address": 32076, "quantity": 2, "dtype": "I32", "gain": 1000, "unit": "A",    "access": "RO"},
    {"name": "peak_active_p",   "address": 32078, "quantity": 2, "dtype": "I32", "gain": 1000, "unit": "kW",   "access": "RO"},
    {"name": "active_power",    "address": 32080, "quantity": 2, "dtype": "I32", "gain": 1000, "unit": "kW",   "access": "RO"},
    {"name": "reactive_power",  "address": 32082, "quantity": 2, "dtype": "I32", "gain": 1000, "unit": "kVar", "access": "RO"},
    {"name": "power_factor",    "address": 32084, "quantity": 1, "dtype": "I16", "gain": 1000, "unit": "-",    "access": "RO"},
    {"name": "grid_frequency",  "address": 32085, "quantity": 1, "dtype": "U16", "gain": 10,   "unit": "Hz",   "access": "RO"},
    {"name": "efficiency",      "address": 32086, "quantity": 1, "dtype": "U16", "gain": 100,  "unit": "%",    "access": "RO"},
    {"name": "internal_temp",   "address": 32087, "quantity": 1, "dtype": "I16", "gain": 10,   "unit": "C",    "access": "RO"},
    {"name": "insulation_res",  "address": 32088, "quantity": 1, "dtype": "U16", "gain": 1000, "unit": "MOhm", "access": "RO"},
    {"name": "device_status",   "address": 32089, "quantity": 1, "dtype": "U16", "gain": 1,    "unit": "-",    "access": "RO"},
    {"name": "error_code",      "address": 32090, "quantity": 1, "dtype": "U16", "gain": 1,    "unit": "-",    "access": "RO"},
]

POWER_RANGE_START = 32064
POWER_RANGE_SIZE = 27  # 32064..32090

# =========================================================================
# Block 5: Battery cluster on PCS (32463-32468, 6 regs) — DYNAMIC (IR)
# =========================================================================

BATTERY_CLUSTER_POINTS = [
    {"name": "batt_soc",    "address": 32463, "quantity": 1, "dtype": "U16", "gain": 10,   "unit": "%",   "access": "RO"},
    {"name": "batt_soh",    "address": 32464, "quantity": 1, "dtype": "U16", "gain": 10,   "unit": "%",   "access": "RO"},
    {"name": "rated_ah",    "address": 32465, "quantity": 2, "dtype": "U32", "gain": 1000, "unit": "Ah",  "access": "RO"},
    {"name": "rated_kwh",   "address": 32467, "quantity": 2, "dtype": "U32", "gain": 1000, "unit": "kWh", "access": "RO"},
]

BATTERY_RANGE_START = 32463
BATTERY_RANGE_SIZE = 6  # 32463..32468

ALL_DYNAMIC_IR_POINTS = STATUS_ALARM_POINTS + POWER_POINTS + BATTERY_CLUSTER_POINTS

# =========================================================================
# Block 6: Control commands (HR, writable) — 40039 and 40043-40044
# =========================================================================

CONTROL_POINTS = [
    {"name": "active_pwr_pct",  "address": 40039, "quantity": 1, "dtype": "I16", "gain": 100,  "unit": "%",  "access": "RW"},
    # 40040-40042: gap
    {"name": "fixed_active_p",  "address": 40043, "quantity": 2, "dtype": "I32", "gain": 1000, "unit": "kW", "access": "RW"},
]

CONTROL_RANGE_START = 40039
CONTROL_RANGE_SIZE = 6  # 40039..40044

# =========================================================================
# Key addresses used by controller (for readable code)
# =========================================================================

ADDR_RUNNING_STATUS = 32000
ADDR_ACTIVE_POWER   = 32080   # I32, gain=1000, unit=kW
ADDR_DC_POWER       = 32064   # I32, gain=1000, unit=kW
ADDR_GRID_FREQ      = 32085   # U16, gain=10, unit=Hz
ADDR_INTERNAL_TEMP  = 32087   # I16, gain=10, unit=C
ADDR_DEVICE_STATUS  = 32089   # U16
ADDR_BATT_SOC       = 32463   # U16, gain=10, unit=%
ADDR_BATT_SOH       = 32464   # U16, gain=10, unit=%
ADDR_FIXED_ACTIVE_P = 40043   # I32, gain=1000, unit=kW — setpoint from PMS

# =========================================================================
# Default static values (used when no plant.yaml override)
# =========================================================================

PCS_DEFAULTS = {
    # Identity
    "model":        "LUNA2000-213KTL-H0",
    "sn":           "SIM00000001",
    "pn":           "02312ABC0001",
    "firmware_ver": "V200R024C10SPC",
    "software_ver": "V200R024C10",
    "mac_address":  "00:00:00:00:00:01",
    "protocol_ver": 1,
    "model_id":     586,
    # Rating
    "rated_power_pn":  2000.0,   # kW
    "max_active_pmax": 2200.0,   # kW (110% overload)
    "max_apparent_s":  2200.0,   # kVA
    "qmax_fed_grid":   -1500.0,  # kVar (negative = to grid)
    "qmax_from_grid":  1500.0,   # kVar
    "pmax_real":       2000.0,   # kW
    "smax_real":       2000.0,   # kVA
    "charge_power":    2000.0,   # kW
}


def build_static_init(
    overrides: Dict[str, Any] | None = None,
) -> Dict[int, int]:
    """Build {address: uint16_value} init dict for the static HR range.

    Uses PCS_DEFAULTS, optionally patched by overrides (e.g. different SN per device).
    Returns init_values suitable for MultiRangeDataBlock range tuple.
    """
    values = dict(PCS_DEFAULTS)
    if overrides:
        values.update(overrides)

    points_with_values: List[Tuple[Dict, Any]] = []
    for pt in ALL_STATIC_POINTS:
        val = values.get(pt["name"])
        if val is not None:
            points_with_values.append((pt, val))

    flat_regs = encode_block(STATIC_RANGE_START, STATIC_RANGE_SIZE, points_with_values)

    # Convert flat list → {address: value} for only non-zero positions
    init: Dict[int, int] = {}
    for offset, reg_val in enumerate(flat_regs):
        if reg_val != 0:
            init[STATIC_RANGE_START + offset] = reg_val
    return init
