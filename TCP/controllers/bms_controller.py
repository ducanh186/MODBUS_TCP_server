"""
BMS controller — runs inside each BMS server process.

Every tick:
1. Read paired PCS IR0 (active_power) via Modbus TCP.
2. Read own capacity from IR2 (static for now).
3. Update float SOC accumulator:
     soc_float += -(active_power_kw * dt_s) / (capacity_kwh * 3600) * 100
   Clamp [0, 100].
4. Write IR0 (SOC encoded uint16) to own datastore.

Sign convention:
  active_power > 0 => discharge => SOC decreases
  active_power < 0 => charge    => SOC increases
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
    decode_capacity_kwh,
    encode_soc,
)

log = logging.getLogger("bms_controller")

# Register addresses (0-based)
PCS_IR0_ACTIVE_POWER = 0
BMS_IR0_SOC = 0
BMS_IR2_CAPACITY = 2


def _loop(
    device_name: str,
    stores: Dict[str, object],
    lock: threading.RLock,
    paired_pcs_host: str,
    paired_pcs_port: int,
    tick_interval_s: float,
    stop_event: threading.Event,
    init_soc: float,
    capacity_kwh: float,
) -> None:
    log.info(f"{device_name} controller loop started (soc_init={init_soc}%)")

    soc_float = init_soc
    last_time = time.monotonic()

    while not stop_event.is_set():
        now = time.monotonic()
        dt_s = now - last_time
        last_time = now

        # 1) Read PCS active_power via Modbus TCP
        active_power_kw = 0.0
        try:
            pcs_client = ModbusTcpClient(paired_pcs_host, port=paired_pcs_port)
            pcs_client.connect()
            rr = pcs_client.read_input_registers(PCS_IR0_ACTIVE_POWER, 1, slave=1)
            if not rr.isError():
                active_power_kw = decode_power_kw(rr.registers[0])
            pcs_client.close()
        except Exception:
            log.warning(f"{device_name}: cannot read PCS active_power, assuming 0")

        # 2) SOC update
        if capacity_kwh > 0:
            delta_soc = -(active_power_kw * dt_s) / (capacity_kwh * 3600) * 100.0
            soc_float = max(0.0, min(100.0, soc_float + delta_soc))

        # 3) Write IR0
        with lock:
            stores["ir"].setValues(BMS_IR0_SOC, [encode_soc(soc_float)])

        stop_event.wait(tick_interval_s)


def start_bms_controller(
    *,
    device_name: str,
    stores: Dict[str, object],
    lock: threading.RLock,
    paired_pcs_host: str,
    paired_pcs_port: int,
    tick_interval_s: float,
    init_soc: float = 50.0,
    capacity_kwh: float = 100.0,
) -> Tuple[threading.Thread, threading.Event]:
    stop_event = threading.Event()
    t = threading.Thread(
        target=_loop,
        args=(device_name, stores, lock, paired_pcs_host, paired_pcs_port,
              tick_interval_s, stop_event, init_soc, capacity_kwh),
        daemon=True,
    )
    t.start()
    return t, stop_event
