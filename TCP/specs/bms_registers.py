"""
LUNA2000C ESS (BMS) register definitions — Huawei address map.

Source: Huawei LUNA2000C ESS Modbus Port Definitions (Issue 01, 2023-06-13)

Address map (Input Registers — read-only, FC04):
  30000-30065  Container status + env + SOC + energy + power + capacity (66 regs)
  30101-30108  BCU-1 basic (8 regs, dynamic — SOC/SOH/power)
  30118-30119  Container alarms (2 regs)
  39014-39017  Subsystem telealarm (4 regs)

No Holding Registers — BMS is a read-only device.

Simulator note:
  SOC-based alarms are placed on tele_alarm_1 (39014) bits 0-3:
    bit0 = SOC >= 100%, bit1 = 90-99%, bit2 = 1-10%, bit3 = SOC <= 0%
"""

from __future__ import annotations

import sys
import os
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tcp_servers"))
from register_codec import encode_block

# =========================================================================
# Block 1: Container status (30000-30002) — STATIC (IR)
# =========================================================================

CONTAINER_STATUS_POINTS = [
    {"name": "container_sts_1", "address": 30000, "quantity": 1, "dtype": "Bitfield16", "gain": 1, "unit": "-", "access": "RO"},
    {"name": "container_sts_2", "address": 30001, "quantity": 1, "dtype": "Bitfield16", "gain": 1, "unit": "-", "access": "RO"},
    {"name": "container_sts_3", "address": 30002, "quantity": 1, "dtype": "Bitfield16", "gain": 1, "unit": "-", "access": "RO"},
]

# =========================================================================
# Block 2: Environment (30014-30021) — STATIC (IR)
# =========================================================================

ENVIRONMENT_POINTS = [
    {"name": "batt_temp_1",  "address": 30014, "quantity": 1, "dtype": "I16", "gain": 10, "unit": "C", "access": "RO"},
    {"name": "batt_humid_1", "address": 30015, "quantity": 1, "dtype": "I16", "gain": 10, "unit": "%", "access": "RO"},
    {"name": "batt_temp_2",  "address": 30016, "quantity": 1, "dtype": "I16", "gain": 10, "unit": "C", "access": "RO"},
    {"name": "batt_humid_2", "address": 30017, "quantity": 1, "dtype": "I16", "gain": 10, "unit": "%", "access": "RO"},
    {"name": "batt_temp_3",  "address": 30018, "quantity": 1, "dtype": "I16", "gain": 10, "unit": "C", "access": "RO"},
    {"name": "batt_humid_3", "address": 30019, "quantity": 1, "dtype": "I16", "gain": 10, "unit": "%", "access": "RO"},
    {"name": "batt_temp_4",  "address": 30020, "quantity": 1, "dtype": "I16", "gain": 10, "unit": "C", "access": "RO"},
    {"name": "batt_humid_4", "address": 30021, "quantity": 1, "dtype": "I16", "gain": 10, "unit": "%", "access": "RO"},
]

# =========================================================================
# Block 3: Container SOC (30035) — DYNAMIC (IR)
# =========================================================================

SOC_POINT = [
    {"name": "container_soc", "address": 30035, "quantity": 1, "dtype": "U16", "gain": 1, "unit": "%", "access": "RO"},
]

# =========================================================================
# Block 4: Energy counters (30036-30055) — STATIC for simulator (IR)
# =========================================================================

ENERGY_POINTS = [
    {"name": "energy_chg_day", "address": 30036, "quantity": 2, "dtype": "U32", "gain": 10, "unit": "kWh", "access": "RO"},
    # 30038-30039: reserved
    {"name": "energy_dis_day", "address": 30040, "quantity": 2, "dtype": "U32", "gain": 10, "unit": "kWh", "access": "RO"},
    {"name": "energy_chg_mon", "address": 30042, "quantity": 2, "dtype": "U32", "gain": 10, "unit": "kWh", "access": "RO"},
    {"name": "energy_dis_mon", "address": 30044, "quantity": 2, "dtype": "U32", "gain": 10, "unit": "kWh", "access": "RO"},
    {"name": "energy_chg_yr",  "address": 30046, "quantity": 4, "dtype": "I64", "gain": 10, "unit": "kWh", "access": "RO"},
    {"name": "energy_dis_yr",  "address": 30050, "quantity": 4, "dtype": "I64", "gain": 10, "unit": "kWh", "access": "RO"},
    {"name": "aux_power_cons", "address": 30054, "quantity": 2, "dtype": "U32", "gain": 10, "unit": "kWh", "access": "RO"},
]

# =========================================================================
# Block 5: Power + Capacity (30056-30065) — DYNAMIC/STATIC mix (IR)
# =========================================================================

POWER_CAPACITY_POINTS = [
    {"name": "chg_dis_power",  "address": 30056, "quantity": 2, "dtype": "I32", "gain": 10,  "unit": "kW",  "access": "RO"},
    {"name": "rated_capacity", "address": 30058, "quantity": 2, "dtype": "U32", "gain": 10,  "unit": "kWh", "access": "RO"},
    {"name": "rated_power",    "address": 30060, "quantity": 2, "dtype": "U32", "gain": 10,  "unit": "kW",  "access": "RO"},
    {"name": "chargeable_cap", "address": 30062, "quantity": 2, "dtype": "U32", "gain": 10,  "unit": "kWh", "access": "RO"},
    {"name": "discharg_cap",   "address": 30064, "quantity": 2, "dtype": "U32", "gain": 10,  "unit": "kWh", "access": "RO"},
]

# Merged range: 30000-30065 = 66 registers (gaps in between read as 0)
CONTAINER_RANGE_START = 30000
CONTAINER_RANGE_SIZE = 66  # 30000..30065 inclusive

# =========================================================================
# Block 6: BCU-1 basic (30101-30108, 8 regs) — DYNAMIC (IR)
# =========================================================================

BCU1_BASIC_POINTS = [
    {"name": "bcu1_wrk_packs",  "address": 30101, "quantity": 1, "dtype": "U16", "gain": 1,    "unit": "-",  "access": "RO"},
    {"name": "bcu1_dev_status", "address": 30102, "quantity": 1, "dtype": "U16", "gain": 1,    "unit": "-",  "access": "RO"},
    {"name": "bcu1_rack_volt",  "address": 30103, "quantity": 1, "dtype": "I16", "gain": 10,   "unit": "V",  "access": "RO"},
    {"name": "bcu1_rack_curr",  "address": 30104, "quantity": 1, "dtype": "I16", "gain": 10,   "unit": "A",  "access": "RO"},
    {"name": "bcu1_soc",        "address": 30105, "quantity": 1, "dtype": "U16", "gain": 1,    "unit": "%",  "access": "RO"},
    {"name": "bcu1_soh",        "address": 30106, "quantity": 1, "dtype": "U16", "gain": 1,    "unit": "%",  "access": "RO"},
    {"name": "bcu1_chg_dis_p",  "address": 30107, "quantity": 2, "dtype": "I32", "gain": 1000, "unit": "kW", "access": "RO"},
]

BCU1_RANGE_START = 30101
BCU1_RANGE_SIZE = 8  # 30101..30108

# =========================================================================
# Block 7: Container alarms (30118-30119, 2 regs) — DYNAMIC (IR)
# =========================================================================

CONTAINER_ALARM_POINTS = [
    {"name": "alarm_1", "address": 30118, "quantity": 1, "dtype": "U16", "gain": 1, "unit": "-", "access": "RO"},
    {"name": "alarm_2", "address": 30119, "quantity": 1, "dtype": "U16", "gain": 1, "unit": "-", "access": "RO"},
]

CONTAINER_ALARM_RANGE_START = 30118
CONTAINER_ALARM_RANGE_SIZE = 2  # 30118..30119

# =========================================================================
# Block 8: Subsystem telealarm (39014-39017, 4 regs) — DYNAMIC (IR)
# =========================================================================

SUBSYSTEM_ALARM_POINTS = [
    {"name": "tele_alarm_1", "address": 39014, "quantity": 1, "dtype": "U16", "gain": 1, "unit": "-", "access": "RO"},
    {"name": "tele_alarm_2", "address": 39015, "quantity": 1, "dtype": "U16", "gain": 1, "unit": "-", "access": "RO"},
    {"name": "tele_alarm_3", "address": 39016, "quantity": 1, "dtype": "U16", "gain": 1, "unit": "-", "access": "RO"},
    {"name": "tele_alarm_4", "address": 39017, "quantity": 1, "dtype": "U16", "gain": 1, "unit": "-", "access": "RO"},
]

SUBSYSTEM_ALARM_RANGE_START = 39014
SUBSYSTEM_ALARM_RANGE_SIZE = 4  # 39014..39017

# =========================================================================
# Key addresses used by controller
# =========================================================================

ADDR_CONTAINER_SOC  = 30035   # U16, gain=1, unit=%
ADDR_CHG_DIS_POWER  = 30056   # I32, gain=10, unit=kW
ADDR_RATED_CAPACITY = 30058   # U32, gain=10, unit=kWh

ADDR_BCU1_SOC       = 30105   # U16, gain=1, unit=%
ADDR_BCU1_SOH       = 30106   # U16, gain=1, unit=%
ADDR_BCU1_CHG_DIS_P = 30107   # I32, gain=1000, unit=kW

ADDR_CONTAINER_ALARM = 30118  # U16, temperature/humidity alarms
ADDR_TELE_ALARM_1    = 39014  # U16, simulator SOC alarms (bits 0-3)

# =========================================================================
# Default static values
# =========================================================================

BMS_DEFAULTS = {
    # Environment (25°C, 45% humidity for all 4 cabins)
    "batt_temp_1": 25.0, "batt_humid_1": 45.0,
    "batt_temp_2": 25.0, "batt_humid_2": 45.0,
    "batt_temp_3": 25.0, "batt_humid_3": 45.0,
    "batt_temp_4": 25.0, "batt_humid_4": 45.0,
    # Container SOC
    "container_soc": 50,
    # Power + capacity
    "rated_capacity": 100.0,    # kWh
    "rated_power": 100.0,       # kW
    "chargeable_cap": 50.0,     # kWh
    "discharg_cap": 50.0,       # kWh
    # BCU-1
    "bcu1_wrk_packs": 16,
    "bcu1_dev_status": 0x0200,  # Running
    "bcu1_rack_volt": 768.0,    # V
    "bcu1_soc": 50,             # %
    "bcu1_soh": 100,            # %
}


def build_static_init(
    overrides: Dict[str, Any] | None = None,
) -> Dict[int, int]:
    """Build {address: uint16_value} init dict for all IR ranges.

    Uses BMS_DEFAULTS, optionally patched by overrides.
    Returns init_values suitable for MultiRangeDataBlock range tuples.
    """
    values = dict(BMS_DEFAULTS)
    if overrides:
        values.update(overrides)

    init: Dict[int, int] = {}

    # Container range (30000-30065)
    container_points = (
        CONTAINER_STATUS_POINTS + ENVIRONMENT_POINTS + SOC_POINT +
        ENERGY_POINTS + POWER_CAPACITY_POINTS
    )
    container_pvs = [(pt, values[pt["name"]]) for pt in container_points if pt["name"] in values]
    container_regs = encode_block(CONTAINER_RANGE_START, CONTAINER_RANGE_SIZE, container_pvs)
    for i, v in enumerate(container_regs):
        if v != 0:
            init[CONTAINER_RANGE_START + i] = v

    # BCU-1 range (30101-30108)
    bcu1_pvs = [(pt, values[pt["name"]]) for pt in BCU1_BASIC_POINTS if pt["name"] in values]
    bcu1_regs = encode_block(BCU1_RANGE_START, BCU1_RANGE_SIZE, bcu1_pvs)
    for i, v in enumerate(bcu1_regs):
        if v != 0:
            init[BCU1_RANGE_START + i] = v

    return init
