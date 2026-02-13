"""
PCS controller — runs inside each PCS server process.

Every tick:
1. Read own HR0 (power_setpoint) from own datastore.
2. Read paired BMS SOC via Modbus TCP.
3. Clamp: if SOC <= 0 and discharge, or SOC >= 100 and charge => active_power = 0.
4. Write own IR0 (active_power) to own datastore.
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

from tcp_servers.tcp_context import (
    decode_power_kw,
    encode_power_kw,
    decode_soc,
)

log = logging.getLogger("pcs_controller")

# Register addresses (0-based)
HR0_SETPOINT = 0
IR0_ACTIVE_POWER = 0
BMS_IR0_SOC = 0


def _tick(
    device_name: str,
    stores: Dict[str, object],
    lock: threading.RLock,
    paired_bms_host: str,
    paired_bms_port: int,
) -> None:
    """One tick of the PCS controller."""

    # 1) Read own setpoint from HR0
    with lock:
        setpoint_u16 = stores["hr"].getValues(HR0_SETPOINT, 1)[0]
    setpoint_kw = decode_power_kw(setpoint_u16)

    # 2) Read paired BMS SOC
    soc = 50.0  # fallback
    try:
        bms_client = ModbusTcpClient(paired_bms_host, port=paired_bms_port)
        bms_client.connect()
        rr = bms_client.read_input_registers(BMS_IR0_SOC, 1, slave=1)
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

    # 4) Write own IR0
    with lock:
        stores["ir"].setValues(IR0_ACTIVE_POWER, [encode_power_kw(active_power_kw)])


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
