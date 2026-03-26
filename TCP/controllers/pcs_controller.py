"""
PCS controller — runs inside each PCS server process.

Every tick:
1. Read Huawei HR 40043-40044 (fixed_active_p, I32, gain=1000) from own datastore.
2. Read paired BMS SOC via Modbus TCP.
3. Clamp: if SOC <= 0 and discharge, or SOC >= 100 and charge => active_power = 0.
4. Write Huawei IR 32080-32081 (active_power, I32, gain=1000) to own datastore.
5. Write running_status to IR 32000.
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

from tcp_servers.tcp_context import decode_soc
from register_codec import encode_i32, decode_i32

log = logging.getLogger("pcs_controller")

# Huawei PCS2000HA register addresses
HR_FIXED_ACTIVE_P = 40043    # I32, gain=1000, kW — setpoint from PMS
IR_ACTIVE_POWER   = 32080    # I32, gain=1000, kW — computed output
IR_RUNNING_STATUS = 32000    # Bitfield16 — bit1 = grid-connected
GAIN_POWER        = 1000

# BMS registers (still 0-based, BMS not Huawei-ized yet)
BMS_IR0_SOC = 0

# Running status bits
STATUS_GRID_CONNECTED = 0x0002  # bit1


def _tick(
    device_name: str,
    stores: Dict[str, object],
    lock: threading.RLock,
    paired_bms_host: str,
    paired_bms_port: int,
) -> None:
    """One tick of the PCS controller."""

    # 1) Read own setpoint from Huawei HR 40043-40044 (I32, 2 regs)
    with lock:
        regs = stores["hr"].getValues(HR_FIXED_ACTIVE_P, 2)
    setpoint_kw = decode_i32(list(regs), gain=GAIN_POWER)

    # 2) Read paired BMS SOC
    soc = 50.0  # fallback
    try:
        bms_client = ModbusTcpClient(paired_bms_host, port=paired_bms_port)
        bms_client.connect()
        rr = bms_client.read_input_registers(BMS_IR0_SOC, count=1, device_id=0)
        if not rr.isError():
            soc = decode_soc(rr.registers[0])
        bms_client.close()
    except Exception:
        log.warning(f"{device_name}: cannot read BMS SOC, using fallback {soc}%")

    # 3) Clamp
    active_power_kw = setpoint_kw
    if soc <= 0.0 and setpoint_kw > 0.0:
        active_power_kw = 0.0
        log.info(f"{device_name}: SOC=0, clamping discharge to 0")
    elif soc >= 100.0 and setpoint_kw < 0.0:
        active_power_kw = 0.0
        log.info(f"{device_name}: SOC=100, clamping charge to 0")

    # 4) Write Huawei IR 32080-32081 (active_power I32 gain=1000)
    # 5) Write running_status IR 32000
    with lock:
        stores["ir"].setValues(IR_ACTIVE_POWER, encode_i32(active_power_kw, gain=GAIN_POWER))
        stores["ir"].setValues(IR_RUNNING_STATUS, [STATUS_GRID_CONNECTED])


def _loop(
    device_name, stores, lock, paired_bms_host, paired_bms_port,
    tick_interval_s, stop_event,
):
    log.info(f"{device_name} controller loop started")
    while not stop_event.is_set():
        try:
            _tick(device_name, stores, lock, paired_bms_host, paired_bms_port)
        except Exception:
            log.exception(f"{device_name} controller tick error")
        stop_event.wait(tick_interval_s)


def start_pcs_controller(
    *,
    device_name: str,
    stores: Dict[str, object],
    lock: threading.RLock,
    paired_bms_host: str,
    paired_bms_port: int,
    tick_interval_s: float,
) -> Tuple[threading.Thread, threading.Event]:
    stop_event = threading.Event()
    t = threading.Thread(
        target=_loop,
        args=(device_name, stores, lock, paired_bms_host, paired_bms_port,
              tick_interval_s, stop_event),
        daemon=True,
    )
    t.start()
    return t, stop_event
