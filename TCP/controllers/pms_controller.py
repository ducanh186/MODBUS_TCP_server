"""
PMS controller — runs inside the PMS server process.

Every tick:
1. Read PMS HR0 (demand_control_power) from own datastore.
2. Split demand equally across PCS devices.
3. Write each PCS HR 40043-40044 (fixed_active_p I32 gain=1000) via Modbus TCP.
4. Read each PCS IR 32080-32081 (active_power I32 gain=1000) via Modbus TCP.
5. Read each BMS Huawei registers via Modbus TCP:
   - IR 30105-30106 (bcu1_soc + bcu1_soh, U16, gain=1)
   - IR 30058-30059 (rated_capacity, U32, gain=10)
   - IR 39014 (tele_alarm_1, SOC-based alarm bits)
6. Compute aggregates and write PMS IR0..IR4 in own datastore.
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
    encode_soc,
    encode_soh,
    encode_capacity_kwh,
)
from register_codec import encode_i32, decode_i32, decode_u16, decode_u32

log = logging.getLogger("pms_controller")

# PMS own registers (0-based, PMS not Huawei-ized yet)
HR0_DEMAND = 0
IR0_TOTAL_POWER = 0
IR1_SOC_AVG = 1
IR2_SOH_AVG = 2
IR3_CAP_TOTAL = 3
IR4_ALARM = 4

# PCS Huawei addresses (written/read via Modbus TCP)
PCS_HR_FIXED_ACTIVE_P = 40043   # I32, gain=1000, kW — write setpoint
PCS_IR_ACTIVE_POWER   = 32080   # I32, gain=1000, kW — read output
PCS_GAIN_POWER        = 1000

# BMS Huawei addresses (read via Modbus TCP)
BMS_IR_BCU1_SOC      = 30105   # U16, gain=1, %
BMS_IR_BCU1_SOH      = 30106   # U16, gain=1, %
BMS_IR_RATED_CAPACITY = 30058  # U32, gain=10, kWh
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

    # 1) Read demand from own HR0
    with lock:
        demand_u16 = stores["hr"].getValues(HR0_DEMAND, 1)[0]
    demand_kw = decode_power_kw(demand_u16)

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
    soc_sum = 0.0
    soh_sum = 0.0
    cap_sum_kwh = 0.0
    bms_count = 0
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

        # 5) Read paired BMS (Huawei addresses)
        bms_name = pairing.get(pcs_name)
        if bms_name and bms_name in bms_ports:
            bms_port = bms_ports[bms_name]
            try:
                bms_client = ModbusTcpClient(host, port=bms_port)
                bms_client.connect()
                # Read BCU-1 SOC + SOH (30105-30106, 2 contiguous U16 regs)
                rr_soc = bms_client.read_input_registers(BMS_IR_BCU1_SOC, count=2, device_id=0)
                if not rr_soc.isError():
                    soc_sum += decode_u16(list(rr_soc.registers[:1]))
                    soh_sum += decode_u16(list(rr_soc.registers[1:]))
                # Read rated_capacity (30058-30059, U32 gain=10)
                rr_cap = bms_client.read_input_registers(BMS_IR_RATED_CAPACITY, count=2, device_id=0)
                if not rr_cap.isError():
                    cap_sum_kwh += decode_u32(list(rr_cap.registers), gain=10)
                # Read alarm (39014)
                rr_alarm = bms_client.read_input_registers(BMS_IR_TELE_ALARM_1, count=1, device_id=0)
                if not rr_alarm.isError():
                    bms_alarms[bms_name] = rr_alarm.registers[0]
                if not rr_soc.isError():
                    bms_count += 1
                bms_client.close()
            except Exception:
                log.exception(f"PMS: error communicating with {bms_name} on port {bms_port}")

    # 6) Write aggregates into PMS IR0..IR4
    with lock:
        stores["ir"].setValues(IR0_TOTAL_POWER, [encode_power_kw(total_active_kw)])
        if bms_count > 0:
            stores["ir"].setValues(IR1_SOC_AVG, [encode_soc(soc_sum / bms_count)])
            stores["ir"].setValues(IR2_SOH_AVG, [encode_soh(soh_sum / bms_count)])
        stores["ir"].setValues(IR3_CAP_TOTAL, [encode_capacity_kwh(cap_sum_kwh)])

        # Aggregate BMS alarms → PMS IR4
        # bms1 bits [3:0] → IR4 bits [3:0], bms2 bits [3:0] → IR4 bits [11:8]
        bms1_alarm = bms_alarms.get("bms1", 0) & 0x000F
        bms2_alarm = bms_alarms.get("bms2", 0) & 0x000F
        pms_alarm = bms1_alarm | (bms2_alarm << 8)
        stores["ir"].setValues(IR4_ALARM, [pms_alarm])


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
