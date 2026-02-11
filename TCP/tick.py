"""
Tick loop for dynamic simulation.

Runs in a background daemon thread, updates device registers every tick:
1. Read PMS HR0 (demand_control_power) -> split equally to PCS1/PCS2
2. Write PCS IR0 (active_power) for each PCS
3. Update BMS IR0 (soc) based on: delta_soc = -(power * dt) / (capacity * 3600) * 100
4. Aggregate PMS IR0..IR3 from PCS + BMS values

Addressing:
    All register addresses are 0-based.  The +1 shift required by
    pymodbus internals is handled inside LockedDataBlock / ZeroBasedDeviceContext
    (see modbus_tcp.py), so tick code simply uses addr 0, 1, 2, ... directly.

Threading:
    A shared threading.RLock (created in modbus_tcp.create_server_context)
    guards both individual register access (inside LockedDataBlock) and
    the full tick batch (with lock: in tick_once).  RLock is reentrant,
    so inner per-register calls don't deadlock with the outer batch lock.
"""

import logging
import threading
import time

from device import DeviceModel
from devices_spec import DEVICES, PCS_TO_BMS

log = logging.getLogger(__name__)

# Internal float state to avoid quantization loss on low-resolution registers.
# Without this, SOC (scale=1 = integer) would never change when delta < 0.5 per tick.
# { bms_uid: {"soc": float} }
_float_state = {}

# --- Register addresses
PMS_HR0_DEMAND = 0
PMS_IR0_TOTAL_POWER = 0
PMS_IR1_SOC_AVG = 1
PMS_IR2_SOH_AVG = 2
PMS_IR3_CAP_TOTAL = 3

PCS_IR0_ACTIVE_POWER = 0

BMS_IR0_SOC = 0
BMS_IR1_SOH = 1
BMS_IR2_CAPACITY = 2


# --- Low-level register helpers ---

def _get_reg(block, addr):
    """Read one uint16 register from a datablock (0-based address)."""
    return block.getValues(addr, 1)[0]


def _set_reg(block, addr, value_u16):
    """Write one uint16 register to a datablock (0-based address)."""
    block.setValues(addr, [value_u16])


# --- Tick logic ---

def tick_once(stores, dt_s, lock):
    """
    One tick of the simulation.  All register writes are wrapped in `lock`
    so that a concurrent Modbus read never sees a half-updated batch.
    """
    # Identify unit IDs by device type
    pms_uid = next(spec["unit_id"] for spec in DEVICES.values()
                   if spec["device_type"] == "PMS")
    pcs_uids = [spec["unit_id"] for spec in DEVICES.values()
                if spec["device_type"] == "PCS"]
    num_pcs = len(pcs_uids)

    with lock:
        # --- 1) Read demand from PMS HR0 ---
        pms_hr = stores[pms_uid]["hr"]
        demand_u16 = _get_reg(pms_hr, PMS_HR0_DEMAND)
        demand_kw = DeviceModel.decode_power_kw(demand_u16)

        # --- 2) Split demand equally to each PCS ---
        per_pcs_kw = demand_kw / num_pcs if num_pcs > 0 else 0.0

        total_active_power_kw = 0.0
        soc_sum = 0.0
        soh_sum = 0.0
        cap_sum_kwh = 0.0
        bms_count = 0

        for pcs_uid in pcs_uids:
            pcs_ir = stores[pcs_uid]["ir"]

            # Write PCS active_power
            _set_reg(pcs_ir, PCS_IR0_ACTIVE_POWER,
                     DeviceModel.encode_power_kw(per_pcs_kw))
            total_active_power_kw += per_pcs_kw

            # --- 3) Update paired BMS SOC ---
            bms_uid = PCS_TO_BMS.get(pcs_uid)
            if bms_uid is None or bms_uid not in stores:
                continue

            bms_ir = stores[bms_uid]["ir"]

            # Read current BMS values
            soc_now = DeviceModel.decode_soc(_get_reg(bms_ir, BMS_IR0_SOC))
            soh_now = DeviceModel.decode_soh(_get_reg(bms_ir, BMS_IR1_SOH))
            cap_kwh = DeviceModel.decode_capacity_kwh(
                _get_reg(bms_ir, BMS_IR2_CAPACITY))

            # Initialise float accumulator on first tick (avoids quantization loss)
            if bms_uid not in _float_state:
                _float_state[bms_uid] = {"soc": soc_now}

            soc_float = _float_state[bms_uid]["soc"]

            # SOC delta: ΔSoc(%) = -(power_kW × Δt_s) / (capacity_kWh × 3600) × 100
            #   power > 0 (discharge) => SOC decreases
            #   power < 0 (charge)    => SOC increases
            if cap_kwh > 0:
                delta_soc = -(per_pcs_kw * dt_s) / (cap_kwh * 3600) * 100.0
                soc_float = max(0.0, min(100.0, soc_float + delta_soc))
            
            _float_state[bms_uid]["soc"] = soc_float
            _set_reg(bms_ir, BMS_IR0_SOC, DeviceModel.encode_soc(soc_float))

            # Accumulate for PMS aggregate
            soc_sum += soc_float
            soh_sum += soh_now
            cap_sum_kwh += cap_kwh
            bms_count += 1

        # --- 4) Aggregate PMS IR registers ---
        pms_ir = stores[pms_uid]["ir"]
        _set_reg(pms_ir, PMS_IR0_TOTAL_POWER,
                 DeviceModel.encode_power_kw(total_active_power_kw))

        if bms_count > 0:
            _set_reg(pms_ir, PMS_IR1_SOC_AVG,
                     DeviceModel.encode_soc(soc_sum / bms_count))
            _set_reg(pms_ir, PMS_IR2_SOH_AVG,
                     DeviceModel.encode_soh(soh_sum / bms_count))

        _set_reg(pms_ir, PMS_IR3_CAP_TOTAL,
                 DeviceModel.encode_capacity_kwh(cap_sum_kwh))


# --- Background thread ---

def _tick_loop(stores, interval, lock, stop_event):
    """Background loop: calls tick_once() every `interval` seconds."""
    log.info(f"Tick loop running, interval={interval}s")
    last = time.monotonic()

    while not stop_event.is_set():
        now = time.monotonic()
        dt_s = now - last
        last = now

        try:
            tick_once(stores, dt_s, lock)
        except Exception:
            log.exception("Tick error")

        stop_event.wait(interval)


def start_tick_loop(stores, lock, interval=1.0):
    """
    Start tick loop in a daemon thread.

    Args:
        stores: {unit_id: {"hr": block, "ir": block}} from create_server_context.
        lock:   shared threading.RLock from create_server_context.
        interval: seconds between ticks (default 1.0).

    Returns:
        (thread, stop_event)
        - stop_event: set this to gracefully stop the tick loop.
    """
    stop_event = threading.Event()
    t = threading.Thread(
        target=_tick_loop,
        args=(stores, interval, lock, stop_event),
        daemon=True,
    )
    t.start()
    return t, stop_event
