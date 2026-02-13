"""
PMS controller — runs inside the PMS server process.

Every tick:
1. Read PMS HR0 (demand_control_power) from own datastore.
2. Split demand equally across PCS devices.
3. Write each PCS HR0 (power_setpoint) via Modbus TCP.
4. Read each PCS IR0 (active_power) via Modbus TCP.
5. Read each BMS IR0/1/2 (soc/soh/capacity) via Modbus TCP.
6. Compute aggregates and write PMS IR0..IR3 in own datastore.
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
    encode_power_kw,
    decode_power_kw,
    decode_soc,
    decode_soh,
    decode_capacity_kwh,
    encode_soc,
    encode_soh,
    encode_capacity_kwh,
)

log = logging.getLogger("pms_controller")

# Register addresses (0-based)
HR0_DEMAND = 0
IR0_TOTAL_POWER = 0
IR1_SOC_AVG = 1
IR2_SOH_AVG = 2
IR3_CAP_TOTAL = 3

PCS_HR0_SETPOINT = 0
PCS_IR0_ACTIVE_POWER = 0

BMS_IR0_SOC = 0
BMS_IR1_SOH = 1
BMS_IR2_CAPACITY = 2


def _tick(
    stores: Dict[str, object],
    lock: threading.RLock,
    host: str,
    pcs_ports: Dict[str, int],
    bms_ports: Dict[str, int],
    pairing: Dict[str, str],
) -> None:
    """One tick of the PMS controller."""

    num_pcs = len(pcs_ports)
    if num_pcs == 0:
        return

    # 1) Read demand from own HR0
    with lock:
        demand_u16 = stores["hr"].getValues(HR0_DEMAND, 1)[0]
    demand_kw = decode_power_kw(demand_u16)

    # 2) Split demand equally
    setpoint_kw = demand_kw / num_pcs
    setpoint_u16 = encode_power_kw(setpoint_kw)

    total_active_kw = 0.0
    soc_sum = 0.0
    soh_sum = 0.0
    cap_sum_kwh = 0.0
    bms_count = 0

    for pcs_name, pcs_port in pcs_ports.items():
        # 3) Write PCS HR0 setpoint via Modbus TCP
        try:
            pcs_client = ModbusTcpClient(host, port=pcs_port)
            pcs_client.connect()
            pcs_client.write_register(PCS_HR0_SETPOINT, setpoint_u16, slave=1)

            # 4) Read PCS IR0 active_power
            rr = pcs_client.read_input_registers(PCS_IR0_ACTIVE_POWER, 1, slave=1)
            if not rr.isError():
                pcs_active_kw = decode_power_kw(rr.registers[0])
                total_active_kw += pcs_active_kw
            pcs_client.close()
        except Exception:
            log.exception(f"PMS: error communicating with {pcs_name} on port {pcs_port}")

        # 5) Read paired BMS
        bms_name = pairing.get(pcs_name)
        if bms_name and bms_name in bms_ports:
            bms_port = bms_ports[bms_name]
            try:
                bms_client = ModbusTcpClient(host, port=bms_port)
                bms_client.connect()
                rr = bms_client.read_input_registers(BMS_IR0_SOC, 3, slave=1)
                if not rr.isError():
                    soc_sum += decode_soc(rr.registers[0])
                    soh_sum += decode_soh(rr.registers[1])
                    cap_sum_kwh += decode_capacity_kwh(rr.registers[2])
                    bms_count += 1
                bms_client.close()
            except Exception:
                log.exception(f"PMS: error communicating with {bms_name} on port {bms_port}")

    # 6) Write aggregates into PMS IR0..IR3
    with lock:
        stores["ir"].setValues(IR0_TOTAL_POWER, [encode_power_kw(total_active_kw)])
        if bms_count > 0:
            stores["ir"].setValues(IR1_SOC_AVG, [encode_soc(soc_sum / bms_count)])
            stores["ir"].setValues(IR2_SOH_AVG, [encode_soh(soh_sum / bms_count)])
        stores["ir"].setValues(IR3_CAP_TOTAL, [encode_capacity_kwh(cap_sum_kwh)])


def _loop(
    stores, lock, host, pcs_ports, bms_ports, pairing,
    tick_interval_s, stop_event,
):
    log.info("PMS controller loop started")
    while not stop_event.is_set():
        try:
            _tick(stores, lock, host, pcs_ports, bms_ports, pairing)
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
) -> Tuple[threading.Thread, threading.Event]:
    stop_event = threading.Event()
    t = threading.Thread(
        target=_loop,
        args=(stores, lock, host, pcs_ports, bms_ports, pairing,
              tick_interval_s, stop_event),
        daemon=True,
    )
    t.start()
    return t, stop_event
