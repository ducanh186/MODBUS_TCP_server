"""
BMS controller — runs inside each BMS server process.

Every tick:
1. Read paired PCS IR 32080-32081 (active_power, I32, gain=1000) via Modbus TCP.
2. Update float SOC accumulator:
     soc_float += -(active_power_kw * dt_s) / (capacity_kwh * 3600) * 100
   Clamp [0, 100].
3. Write own Huawei registers:
   - IR 30035 (container_soc, U16, gain=1)
   - IR 30105 (bcu1_soc, U16, gain=1)
   - IR 30107-30108 (bcu1_chg_dis_p, I32, gain=1000)
   - IR 30056-30057 (chg_dis_power, I32, gain=10)
   - IR 39014 (tele_alarm_1, SOC-based alarm bits)

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

from register_codec import encode_i32, encode_u16, decode_i32

log = logging.getLogger("bms_controller")

# PCS Huawei addresses (read via Modbus TCP)
PCS_IR_ACTIVE_POWER = 32080   # I32, gain=1000, kW
PCS_GAIN_POWER      = 1000

# BMS own Huawei addresses (written to own datastore)
from specs.bms_registers import (
    ADDR_CONTAINER_SOC,
    ADDR_CHG_DIS_POWER,
    ADDR_BCU1_SOC,
    ADDR_BCU1_SOH,
    ADDR_BCU1_CHG_DIS_P,
    ADDR_TELE_ALARM_1,
)


def _compute_alarm(soc: float) -> int:
    """Compute BMS alarm bitfield from SOC value.

    Bit 0: SOC >= 100%   (BMS0000)
    Bit 1: 90 <= SOC < 100 (BMS0001)
    Bit 2: 0 < SOC <= 10  (BMS0002)
    Bit 3: SOC <= 0%     (BMS0003)
    """
    soc_r = round(soc)
    alarm = 0
    if soc_r >= 100:
        alarm |= 1 << 0
    elif soc_r >= 90:
        alarm |= 1 << 1
    if soc_r <= 0:
        alarm |= 1 << 3
    elif soc_r <= 10:
        alarm |= 1 << 2
    return alarm


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

        # 1) Read PCS active_power via Modbus TCP (I32 at IR 32080-32081)
        active_power_kw = 0.0
        try:
            pcs_client = ModbusTcpClient(paired_pcs_host, port=paired_pcs_port)
            pcs_client.connect()
            rr = pcs_client.read_input_registers(PCS_IR_ACTIVE_POWER, count=2, device_id=0)
            if not rr.isError():
                active_power_kw = decode_i32(list(rr.registers), gain=PCS_GAIN_POWER)
            pcs_client.close()
        except Exception:
            log.warning(f"{device_name}: cannot read PCS active_power, assuming 0")

        # 2) SOC update
        if capacity_kwh > 0:
            delta_soc = -(active_power_kw * dt_s) / (capacity_kwh * 3600) * 100.0
            soc_float = max(0.0, min(100.0, soc_float + delta_soc))

        # 3) Write Huawei registers
        alarm = _compute_alarm(soc_float)
        soc_u16 = encode_u16(round(soc_float))[0]  # U16, gain=1

        with lock:
            ir = stores["ir"]
            # Container SOC (30035)
            ir.setValues(ADDR_CONTAINER_SOC, [soc_u16])
            # BCU-1 SOC (30105) + SOH (30106)
            ir.setValues(ADDR_BCU1_SOC, [soc_u16])
            # BCU-1 charge/discharge power (30107-30108, I32, gain=1000)
            ir.setValues(ADDR_BCU1_CHG_DIS_P, encode_i32(active_power_kw, gain=1000))
            # Container charge/discharge power (30056-30057, I32, gain=10)
            ir.setValues(ADDR_CHG_DIS_POWER, encode_i32(active_power_kw, gain=10))
            # Subsystem alarm (39014)
            ir.setValues(ADDR_TELE_ALARM_1, [alarm])

        stop_event.wait(tick_interval_s)

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
