"""
PCS2000HA register definitions — Phase A (identity + rating blocks, read-only static).

Source: Huawei PCS2000HA Smart PCS Modbus Port Definitions (Issue 03, 2025-04-03)

Address map:
  30000-30070  Identity + Firmware/Protocol  (71 regs, contiguous, RO)
  30071-30072  Reserved gap (returns 0)
  30073-30088  Rating + Max reactive         (16 regs, contiguous, RO)
  ─────────── merged into one range: (30000, 89) for mega-read ───────────

Phase B will add:
  32000-32090  Running status + Power readings  (dynamic, controller updates)
  40039-40201  Control commands                 (writable by PMS)
"""

from __future__ import annotations

import sys
import os
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tcp_servers"))
from register_codec import encode_block

# =========================================================================
# Block 1: Identity (30000-30070, 71 regs)
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
# Block 2: Rating + Max reactive (30073-30088, 16 regs)
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
