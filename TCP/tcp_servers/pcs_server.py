"""
PCS Modbus TCP server process (parameterised by device name).

Address layout (Phase A — 3B):
  HR  0-9      Legacy 0-based range (controller backward compat)
    HR0 (RW): power_setpoint (kW, scale=0.1, int16) — written by PMS
  HR  30000-30088  Huawei identity + rating (read-only static)
  IR  0-9      Legacy 0-based range
    IR0 (R):  active_power (kW, scale=0.1, int16) — computed by controller

Phase B will add: HR 40039-40201 (control), IR 32000-32090 (power readings).
"""

from __future__ import annotations

import logging
import sys
import os

from pymodbus.server import StartTcpServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tcp_context import build_multirange_server_context
from specs.pcs_registers import (
    STATIC_RANGE_START,
    STATIC_RANGE_SIZE,
    build_static_init,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | PCS | %(levelname)s | %(message)s",
)
log = logging.getLogger("pcs_server")


def run_pcs_server(
    device_name: str,
    host: str,
    port: int,
    paired_bms_host: str,
    paired_bms_port: int,
    tick_interval_s: float,
) -> None:
    """Start a PCS TCP server and its controller thread."""

    # Build Huawei static init data (identity + rating)
    static_init = build_static_init(overrides={"sn": f"SIM-{device_name}"})

    server_ctx, stores, lock = build_multirange_server_context(
        hr_ranges=[
            (0, 10, {0: 0}),                                    # legacy: HR0 = setpoint
            (STATIC_RANGE_START, STATIC_RANGE_SIZE, static_init),  # Huawei identity+rating
        ],
        ir_ranges=[
            (0, 10, {0: 0}),                                    # legacy: IR0 = active_power
        ],
        slave_id=1,
    )

    from controllers.pcs_controller import start_pcs_controller
    ctrl_thread, ctrl_stop = start_pcs_controller(
        device_name=device_name,
        stores=stores,
        lock=lock,
        paired_bms_host=paired_bms_host,
        paired_bms_port=paired_bms_port,
        tick_interval_s=tick_interval_s,
    )
    log.info(f"{device_name} controller thread started (tick={tick_interval_s}s)")
    log.info(f"{device_name} Huawei static registers: HR {STATIC_RANGE_START}-{STATIC_RANGE_START + STATIC_RANGE_SIZE - 1}")

    log.info(f"{device_name} TCP server listening on {host}:{port}")
    StartTcpServer(server_ctx, address=(host, port))


if __name__ == "__main__":
    run_pcs_server(
        device_name="PCS1",
        host="127.0.0.1", port=15021,
        paired_bms_host="127.0.0.1", paired_bms_port=15024,
        tick_interval_s=1.0,
    )
