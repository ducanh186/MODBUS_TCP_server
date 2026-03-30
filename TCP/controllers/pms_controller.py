"""
PMS controller — runs inside the PMS server process (Huawei address map).

Every tick:
1. Read demand from own HR 40420-40421 (active_adj U32 gain=10, magnitude kW)
   + HR 40424 (demand_direction: 0=discharge, 1=charge) → signed demand_kw.
2. Read suppression percent from Suppression Logger HR0 (0-based).
3. Split (suppressed) demand equally across PCS devices.
4. Write each PCS HR 40043-40044 (fixed_active_p I32 gain=1000) via Modbus TCP.
5. Read each PCS IR 32080-32081 (active_power I32 gain=1000) via Modbus TCP.
6. Read each BMS Huawei registers via Modbus TCP:
   - IR 30105-30106 (bcu1_soc + bcu1_soh, U16, gain=1)
   - IR 39014 (tele_alarm_1, SOC-based alarm bits)
7. Write aggregates to own HR:
   - HR 40525-40526 (active_power I32 gain=1000)
   - HR 50000 (alarm: BMS1 bits[3:0] | BMS2 bits[11:8])
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Dict, Tuple

from pymodbus.client import ModbusTcpClient

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tcp_servers"))

from register_codec import encode_i32, decode_i32, encode_u32, decode_u32, decode_u16

from specs.pms_registers import (
    ADDR_ACTIVE_ADJ,
    ADDR_DEMAND_DIRECTION,
    ADDR_ACTIVE_POWER,
    ADDR_ALARM_1,
)

log = logging.getLogger("pms_controller")

# PMS own Huawei HR addresses
PMS_HR_DEMAND_MAG   = ADDR_ACTIVE_ADJ       # 40420, U32, gain=10, kW (magnitude)
PMS_HR_DEMAND_DIR   = ADDR_DEMAND_DIRECTION  # 40424, U16, 0=discharge, 1=charge
PMS_HR_ACTIVE_POWER = ADDR_ACTIVE_POWER      # 40525, I32, gain=1000, kW
PMS_HR_ALARM_1      = ADDR_ALARM_1           # 50000, U16, BMS alarm forwarding

PMS_DEMAND_GAIN     = 10     # active_adj U32 gain
PMS_POWER_GAIN      = 1000   # active_power I32 gain

# PCS Huawei addresses (written/read via Modbus TCP)
PCS_HR_FIXED_ACTIVE_P = 40043   # I32, gain=1000, kW — write setpoint
PCS_IR_ACTIVE_POWER   = 32080   # I32, gain=1000, kW — read output
PCS_GAIN_POWER        = 1000

# BMS Huawei addresses (read via Modbus TCP)
BMS_IR_BCU1_SOC      = 30105   # U16, gain=1, %
BMS_IR_BCU1_SOH      = 30106   # U16, gain=1, %
BMS_IR_TELE_ALARM_1  = 39014   # U16, SOC-based alarm bits


def _tick(
    stores: Dict[str, object],
    lock: threading.RLock,
    host: str,
    pcs_ports: Dict[str, int],
    bms_ports: Dict[str, int],
    pairing: Dict[str, str],
    suppression_host: str = "",
    suppression_port: int = 0,
) -> None:
    """One tick of the PMS controller."""

    num_pcs = len(pcs_ports)
    if num_pcs == 0:
        return

    # 1) Read demand from own HR 40420-40421 (U32 gain=10, magnitude)
    #    + HR 40424 (direction: 0=discharge, 1=charge)
    with lock:
        mag_regs = stores["hr"].getValues(PMS_HR_DEMAND_MAG, 2)
        dir_regs = stores["hr"].getValues(PMS_HR_DEMAND_DIR, 1)
    demand_mag_kw = decode_u32(list(mag_regs), gain=PMS_DEMAND_GAIN)
    direction = dir_regs[0]  # 0=discharge (+kW), 1=charge (-kW)
    demand_kw = -demand_mag_kw if direction == 1 else demand_mag_kw

    # 1b) Read suppression_percent from Suppression Logger HR0
    supp_pct = 100
    if suppression_host and suppression_port:
        try:
            supp_client = ModbusTcpClient(suppression_host, port=suppression_port)
            supp_client.connect()
            rr = supp_client.read_holding_registers(0, count=1, device_id=0)
            if not rr.isError():
                raw = rr.registers[0]
                supp_pct = max(0, min(100, raw))
            supp_client.close()
        except Exception:
            log.warning("PMS: cannot read suppression logger — using 100%")

    # Apply suppression to discharge only (+kW)
    if demand_kw > 0 and supp_pct < 100:
        original_kw = demand_kw
        demand_kw = demand_kw * supp_pct / 100.0
        log.info(f"Suppression {supp_pct}%: demand {original_kw:.1f} -> {demand_kw:.1f} kW")

    # 2) Split demand equally
    setpoint_kw = demand_kw / num_pcs

    total_active_kw = 0.0
    bms_alarms: Dict[str, int] = {}  # bms_name -> alarm bitfield

    for pcs_name, pcs_port in pcs_ports.items():
        # 3) Write PCS HR 40043-40044 (I32 gain=1000) via Modbus TCP
        try:
            pcs_client = ModbusTcpClient(host, port=pcs_port)
            pcs_client.connect()
            pcs_client.write_registers(
                PCS_HR_FIXED_ACTIVE_P,
                encode_i32(setpoint_kw, gain=PCS_GAIN_POWER),
                device_id=0,
            )

            # 4) Read PCS IR 32080-32081 (active_power I32 gain=1000)
            rr = pcs_client.read_input_registers(PCS_IR_ACTIVE_POWER, count=2, device_id=0)
            if not rr.isError():
                pcs_active_kw = decode_i32(list(rr.registers), gain=PCS_GAIN_POWER)
                total_active_kw += pcs_active_kw
            pcs_client.close()
        except Exception:
            log.exception(f"PMS: error communicating with {pcs_name} on port {pcs_port}")

        # 5) Read paired BMS alarm (Huawei addresses)
        bms_name = pairing.get(pcs_name)
        if bms_name and bms_name in bms_ports:
            bms_port = bms_ports[bms_name]
            try:
                bms_client = ModbusTcpClient(host, port=bms_port)
                bms_client.connect()
                # Read alarm (39014)
                rr_alarm = bms_client.read_input_registers(BMS_IR_TELE_ALARM_1, count=1, device_id=0)
                if not rr_alarm.isError():
                    bms_alarms[bms_name] = rr_alarm.registers[0]
                bms_client.close()
            except Exception:
                log.exception(f"PMS: error communicating with {bms_name} on port {bms_port}")

    # 6) Write aggregates into PMS HR (Huawei addresses)
    with lock:
        # HR 40525-40526: total active_power (I32 gain=1000)
        stores["hr"].setValues(PMS_HR_ACTIVE_POWER, encode_i32(total_active_kw, gain=PMS_POWER_GAIN))

        # HR 50000: BMS alarm forwarding
        # bms1 bits [3:0] → alarm bits [3:0], bms2 bits [3:0] → alarm bits [11:8]
        bms1_alarm = bms_alarms.get("bms1", 0) & 0x000F
        bms2_alarm = bms_alarms.get("bms2", 0) & 0x000F
        pms_alarm = bms1_alarm | (bms2_alarm << 8)
        stores["hr"].setValues(PMS_HR_ALARM_1, [pms_alarm])


def _loop(
    stores, lock, host, pcs_ports, bms_ports, pairing,
    tick_interval_s, stop_event,
    suppression_host, suppression_port,
):
    log.info("PMS controller loop started")
    while not stop_event.is_set():
        try:
            _tick(stores, lock, host, pcs_ports, bms_ports, pairing,
                  suppression_host, suppression_port)
        except Exception:
            log.exception("PMS controller tick error")
        stop_event.wait(tick_interval_s)


def start_pms_controller(
    *,
    stores: Dict[str, object],
    lock: threading.RLock,
    host: str,
    pcs_ports: Dict[str, int],
    bms_ports: Dict[str, int],
    pairing: Dict[str, str],
    tick_interval_s: float,
    suppression_host: str = "",
    suppression_port: int = 0,
) -> Tuple[threading.Thread, threading.Event]:
    stop_event = threading.Event()
    t = threading.Thread(
        target=_loop,
        args=(stores, lock, host, pcs_ports, bms_ports, pairing,
              tick_interval_s, stop_event,
              suppression_host, suppression_port),
        daemon=True,
    )
    t.start()
    return t, stop_event
