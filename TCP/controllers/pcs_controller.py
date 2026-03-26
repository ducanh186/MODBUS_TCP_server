"""
PCS controller — runs inside each PCS server process.

Every tick:
1. Read Huawei HR 40043-40044 (fixed_active_p, I32, gain=1000) from own datastore.
2. Read paired BMS SOC/SOH via Modbus TCP.
3. Clamp: if SOC <= 0 and discharge, or SOC >= 100 and charge => active_power = 0.
4. Write all Huawei IR registers:
   - 32000       running_status (Bitfield16)
   - 32064-32065 dc_power (I32, kW, gain=1000)
   - 32066-32071 line/phase voltages (U16, V, gain=10)
   - 32072-32077 phase currents (I32, A, gain=1000)
   - 32078-32079 peak_active_p (I32, kW, gain=1000)
   - 32080-32081 active_power (I32, kW, gain=1000)
   - 32082-32083 reactive_power (I32, kVar, gain=1000)
   - 32084       power_factor (I16, gain=1000)
   - 32085       grid_frequency (U16, Hz, gain=10)
   - 32086       efficiency (U16, %, gain=100)
   - 32087       internal_temp (I16, C, gain=10)
   - 32088       insulation_res (U16, MOhm, gain=1000)
   - 32089       device_status (U16)
   - 32090       error_code (U16)
   - 32463       batt_soc (U16, %, gain=10)
   - 32464       batt_soh (U16, %, gain=10)
   - 32465-32466 rated_ah (U32, Ah, gain=1000)
   - 32467-32468 rated_kwh (U32, kWh, gain=1000)
"""

from __future__ import annotations

import logging
import math
import random
import threading
import time
from typing import Dict, Optional, Tuple

from pymodbus.client import ModbusTcpClient

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tcp_servers"))

from tcp_servers.tcp_context import decode_soc
from register_codec import encode_i32, encode_i16, encode_u16, encode_u32, decode_i32

log = logging.getLogger("pcs_controller")

# ── Huawei PCS2000HA register addresses ────────────────────────────────────
# IR — power block (32064-32090)
IR_DC_POWER        = 32064    # I32, gain=1000, kW
IR_LINE_VOLT_AB    = 32066    # U16, gain=10, V
IR_LINE_VOLT_BC    = 32067
IR_LINE_VOLT_CA    = 32068
IR_PHASE_VOLT_A    = 32069    # U16, gain=10, V
IR_PHASE_VOLT_B    = 32070
IR_PHASE_VOLT_C    = 32071
IR_PHASE_CURR_A    = 32072    # I32, gain=1000, A
IR_PHASE_CURR_B    = 32074
IR_PHASE_CURR_C    = 32076
IR_PEAK_ACTIVE_P   = 32078    # I32, gain=1000, kW
IR_ACTIVE_POWER    = 32080    # I32, gain=1000, kW
IR_REACTIVE_POWER  = 32082    # I32, gain=1000, kVar
IR_POWER_FACTOR    = 32084    # I16, gain=1000
IR_GRID_FREQUENCY  = 32085    # U16, gain=10, Hz
IR_EFFICIENCY      = 32086    # U16, gain=100, %
IR_INTERNAL_TEMP   = 32087    # I16, gain=10, C
IR_INSULATION_RES  = 32088    # U16, gain=1000, MOhm
IR_DEVICE_STATUS   = 32089    # U16
IR_ERROR_CODE      = 32090    # U16

# IR — status (32000)
IR_RUNNING_STATUS  = 32000    # Bitfield16

# IR — battery cluster (32463-32468)
IR_BATT_SOC        = 32463    # U16, gain=10, %
IR_BATT_SOH        = 32464    # U16, gain=10, %
IR_RATED_AH        = 32465    # U32, gain=1000, Ah
IR_RATED_KWH       = 32467    # U32, gain=1000, kWh

# HR — control
HR_FIXED_ACTIVE_P  = 40043    # I32, gain=1000, kW — setpoint from PMS

GAIN_POWER = 1000

# BMS registers (still 0-based, BMS not Huawei-ized yet)
BMS_IR0_SOC = 0
BMS_IR1_SOH = 1

# Running status bits
STATUS_GRID_CONNECTED = 0x0002  # bit1

# Nominal simulation constants
NOMINAL_LINE_VOLTAGE_V   = 380.0   # 3-phase line voltage
NOMINAL_PHASE_VOLTAGE_V  = 220.0   # phase-to-neutral
NOMINAL_EFFICIENCY_PCT   = 97.0    # %
NOMINAL_INSULATION_MOHM  = 10.0    # MΩ
BASE_TEMP_C              = 35.0    # °C base internal temp
RATED_CAPACITY_AH        = 1117.0  # Ah (LUNA2000-213KTL ≈ 213 kWh / 191V nominal)
RATED_CAPACITY_KWH       = 213.0   # kWh

# Device status codes (from PCS.txt doc)
DEVICE_STATUS_STANDBY    = 0x0000  # standby: initializing
DEVICE_STATUS_PQ_RUNNING = 0x0206  # runs: PQ running


def _read_bms_soc_soh(host: str, port: int) -> Tuple[float, float]:
    """Read SOC and SOH from paired BMS (0-based addressing)."""
    soc, soh = 50.0, 100.0  # fallback
    try:
        c = ModbusTcpClient(host, port=port)
        c.connect()
        rr = c.read_input_registers(BMS_IR0_SOC, count=2, device_id=0)
        if not rr.isError() and len(rr.registers) >= 2:
            soc = decode_soc(rr.registers[0])
            soh = float(rr.registers[1])  # BMS IR1 = SOH (uint16, 1%/LSB)
        c.close()
    except Exception:
        pass
    return soc, soh


def _read_transducer_freq(host: str, port: int) -> Optional[float]:
    """Read frequency from Transducer IR0 (uint16, gain=1000, Hz)."""
    try:
        c = ModbusTcpClient(host, port=port)
        c.connect()
        rr = c.read_input_registers(0, count=1, device_id=0)
        c.close()
        if not rr.isError() and rr.registers[0] > 0:
            return rr.registers[0] / 1000.0  # e.g. 50000 → 50.0
    except Exception:
        pass
    return None


def _tick(
    device_name: str,
    stores: Dict[str, object],
    lock: threading.RLock,
    paired_bms_host: str,
    paired_bms_port: int,
    transducer_host: Optional[str],
    transducer_port: Optional[int],
    peak_power_kw: list,  # mutable container [float] to track peak
) -> None:
    """One tick of the PCS controller."""

    # ── 1) Read own setpoint from HR 40043-40044 ──────────────────────────
    with lock:
        regs = stores["hr"].getValues(HR_FIXED_ACTIVE_P, 2)
    setpoint_kw = decode_i32(list(regs), gain=GAIN_POWER)

    # ── 2) Read paired BMS SOC + SOH ──────────────────────────────────────
    soc, soh = _read_bms_soc_soh(paired_bms_host, paired_bms_port)

    # ── 3) Clamp by SOC ──────────────────────────────────────────────────
    active_power_kw = setpoint_kw
    if soc <= 0.0 and setpoint_kw > 0.0:
        active_power_kw = 0.0
        log.info(f"{device_name}: SOC=0, clamping discharge to 0")
    elif soc >= 100.0 and setpoint_kw < 0.0:
        active_power_kw = 0.0
        log.info(f"{device_name}: SOC=100, clamping charge to 0")

    # ── 4) Derive all power-block registers ───────────────────────────────
    is_active = abs(active_power_kw) > 0.01

    # Efficiency: nominal when active, 0 when idle
    efficiency_pct = NOMINAL_EFFICIENCY_PCT if is_active else 0.0

    # DC power = active_power / (efficiency/100) — DC side is higher due to losses
    if is_active and efficiency_pct > 0:
        dc_power_kw = active_power_kw / (efficiency_pct / 100.0)
    else:
        dc_power_kw = 0.0

    # Voltages: nominal + small jitter when active
    if is_active:
        v_jitter = random.uniform(-0.5, 0.5)
        line_volt_v = NOMINAL_LINE_VOLTAGE_V + v_jitter
        phase_volt_v = NOMINAL_PHASE_VOLTAGE_V + v_jitter * 0.577  # ≈ 1/√3
    else:
        line_volt_v = NOMINAL_LINE_VOLTAGE_V
        phase_volt_v = NOMINAL_PHASE_VOLTAGE_V

    # Phase currents: I = P / (3 × V_phase) — balanced 3-phase
    if is_active and phase_volt_v > 0:
        phase_current_a = active_power_kw * 1000.0 / (3.0 * phase_volt_v)  # A
    else:
        phase_current_a = 0.0

    # Peak active power today (track absolute max)
    if abs(active_power_kw) > abs(peak_power_kw[0]):
        peak_power_kw[0] = active_power_kw

    # Reactive power: 0 kVar (pure PQ mode, unity PF)
    reactive_power_kvar = 0.0

    # Power factor: 1.0 when active (sign matches active_power sign), 0 when idle
    if is_active:
        power_factor = 1.0 if active_power_kw >= 0 else -1.0
    else:
        power_factor = 0.0

    # Grid frequency: read from Transducer if available, else 50.0 Hz
    grid_freq_hz = 50.0
    if transducer_host and transducer_port:
        freq = _read_transducer_freq(transducer_host, transducer_port)
        if freq is not None:
            grid_freq_hz = freq

    # Internal temperature: base + load-dependent heating + small noise
    load_ratio = min(abs(active_power_kw) / 2000.0, 1.0)  # fraction of rated power
    temp_c = BASE_TEMP_C + load_ratio * 10.0 + random.uniform(-0.5, 0.5)

    # Device status
    device_status = DEVICE_STATUS_PQ_RUNNING if is_active else DEVICE_STATUS_STANDBY

    # ── 5) Write all IR registers ─────────────────────────────────────────
    with lock:
        ir = stores["ir"]

        # Running status (32000)
        ir.setValues(IR_RUNNING_STATUS, [STATUS_GRID_CONNECTED])

        # Power block (32064-32090)
        ir.setValues(IR_DC_POWER,       encode_i32(dc_power_kw, gain=1000))
        ir.setValues(IR_LINE_VOLT_AB,   encode_u16(line_volt_v, gain=10))
        ir.setValues(IR_LINE_VOLT_BC,   encode_u16(line_volt_v, gain=10))
        ir.setValues(IR_LINE_VOLT_CA,   encode_u16(line_volt_v, gain=10))
        ir.setValues(IR_PHASE_VOLT_A,   encode_u16(phase_volt_v, gain=10))
        ir.setValues(IR_PHASE_VOLT_B,   encode_u16(phase_volt_v, gain=10))
        ir.setValues(IR_PHASE_VOLT_C,   encode_u16(phase_volt_v, gain=10))
        ir.setValues(IR_PHASE_CURR_A,   encode_i32(phase_current_a, gain=1000))
        ir.setValues(IR_PHASE_CURR_B,   encode_i32(phase_current_a, gain=1000))
        ir.setValues(IR_PHASE_CURR_C,   encode_i32(phase_current_a, gain=1000))
        ir.setValues(IR_PEAK_ACTIVE_P,  encode_i32(peak_power_kw[0], gain=1000))
        ir.setValues(IR_ACTIVE_POWER,   encode_i32(active_power_kw, gain=1000))
        ir.setValues(IR_REACTIVE_POWER, encode_i32(reactive_power_kvar, gain=1000))
        ir.setValues(IR_POWER_FACTOR,   encode_i16(power_factor, gain=1000))
        ir.setValues(IR_GRID_FREQUENCY, encode_u16(grid_freq_hz, gain=10))
        ir.setValues(IR_EFFICIENCY,     encode_u16(efficiency_pct, gain=100))
        ir.setValues(IR_INTERNAL_TEMP,  encode_i16(temp_c, gain=10))
        ir.setValues(IR_INSULATION_RES, encode_u16(NOMINAL_INSULATION_MOHM, gain=1000))
        ir.setValues(IR_DEVICE_STATUS,  [device_status])
        ir.setValues(IR_ERROR_CODE,     [0])

        # Battery cluster (32463-32468) — mirror from BMS
        ir.setValues(IR_BATT_SOC,  encode_u16(soc, gain=10))
        ir.setValues(IR_BATT_SOH,  encode_u16(soh, gain=10))
        ir.setValues(IR_RATED_AH,  encode_u32(RATED_CAPACITY_AH, gain=1000))
        ir.setValues(IR_RATED_KWH, encode_u32(RATED_CAPACITY_KWH, gain=1000))


def _loop(
    device_name, stores, lock, paired_bms_host, paired_bms_port,
    transducer_host, transducer_port,
    tick_interval_s, stop_event,
):
    log.info(f"{device_name} controller loop started")
    peak_power_kw = [0.0]  # mutable container for peak tracking
    while not stop_event.is_set():
        try:
            _tick(device_name, stores, lock, paired_bms_host, paired_bms_port,
                  transducer_host, transducer_port, peak_power_kw)
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
    transducer_host: str = "",
    transducer_port: int = 0,
    tick_interval_s: float,
) -> Tuple[threading.Thread, threading.Event]:
    stop_event = threading.Event()
    t = threading.Thread(
        target=_loop,
        args=(device_name, stores, lock, paired_bms_host, paired_bms_port,
              transducer_host, transducer_port,
              tick_interval_s, stop_event),
        daemon=True,
    )
    t.start()
    return t, stop_event
