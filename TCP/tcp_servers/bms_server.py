"""
BMS Modbus TCP server process (parameterised by device name).

Address layout (Huawei LUNA2000C ESS):
  IR  30000-30065  Container status + env + SOC + energy + power + capacity
  IR  30101-30108  BCU-1 basic (SOC, SOH, charge/discharge power)
  IR  30118-30119  Container alarms
  IR  39014-39017  Subsystem telealarm (SOC-based alarms in simulator)

No Holding Registers — BMS is read-only.
Runs the BMS controller loop in a background thread within this process.
"""

from __future__ import annotations

import logging
import sys
import os

from pymodbus.server import StartTcpServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tcp_context import build_multirange_server_context
from specs.bms_registers import (
    CONTAINER_RANGE_START,
    CONTAINER_RANGE_SIZE,
    BCU1_RANGE_START,
    BCU1_RANGE_SIZE,
    CONTAINER_ALARM_RANGE_START,
    CONTAINER_ALARM_RANGE_SIZE,
    SUBSYSTEM_ALARM_RANGE_START,
    SUBSYSTEM_ALARM_RANGE_SIZE,
    build_static_init,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | BMS | %(levelname)s | %(message)s",
)
log = logging.getLogger("bms_server")


def run_bms_server(
    device_name: str,
    host: str,
    port: int,
    paired_pcs_host: str,
    paired_pcs_port: int,
    tick_interval_s: float,
    init_soc: float = 50.0,
    init_soh: float = 100.0,
    init_capacity_kwh: float = 100.0,
) -> None:
    """Start a BMS TCP server and its controller thread."""

    # Build init values for all IR ranges
    all_init = build_static_init(overrides={
        "container_soc": int(init_soc),
        "bcu1_soc": int(init_soc),
        "bcu1_soh": int(init_soh),
        "rated_capacity": init_capacity_kwh,
    })

    # Split init by range
    def _pick(start, size):
        return {k: v for k, v in all_init.items() if start <= k < start + size}

    server_ctx, stores, lock = build_multirange_server_context(
        ir_ranges=[
            (CONTAINER_RANGE_START, CONTAINER_RANGE_SIZE, _pick(CONTAINER_RANGE_START, CONTAINER_RANGE_SIZE)),
            (BCU1_RANGE_START, BCU1_RANGE_SIZE, _pick(BCU1_RANGE_START, BCU1_RANGE_SIZE)),
            (CONTAINER_ALARM_RANGE_START, CONTAINER_ALARM_RANGE_SIZE),
            (SUBSYSTEM_ALARM_RANGE_START, SUBSYSTEM_ALARM_RANGE_SIZE),
        ],
        slave_id=0,
    )

    from controllers.bms_controller import start_bms_controller
    ctrl_thread, ctrl_stop = start_bms_controller(
        device_name=device_name,
        stores=stores,
        lock=lock,
        paired_pcs_host=paired_pcs_host,
        paired_pcs_port=paired_pcs_port,
        tick_interval_s=tick_interval_s,
        init_soc=init_soc,
        capacity_kwh=init_capacity_kwh,
    )
    log.info(f"{device_name} controller thread started (tick={tick_interval_s}s)")
    log.info(f"{device_name} Huawei registers: IR {CONTAINER_RANGE_START}-{CONTAINER_RANGE_START + CONTAINER_RANGE_SIZE - 1} (container), "
             f"IR {BCU1_RANGE_START}-{BCU1_RANGE_START + BCU1_RANGE_SIZE - 1} (BCU-1), "
             f"IR {SUBSYSTEM_ALARM_RANGE_START}-{SUBSYSTEM_ALARM_RANGE_START + SUBSYSTEM_ALARM_RANGE_SIZE - 1} (alarm)")
    log.info(f"{device_name} unit_id=0, TCP server listening on {host}:{port}")
    StartTcpServer(server_ctx, address=(host, port))


if __name__ == "__main__":
    run_bms_server(
        device_name="BMS1",
        host="127.0.0.1", port=15024,
        paired_pcs_host="127.0.0.1", paired_pcs_port=15021,
        tick_interval_s=1.0,
    )
