"""
PCS Modbus TCP server process (parameterised by device name).

Exposes:
  HR0 (RW): power_setpoint (kW, scale=0.1, int16) — written by PMS
  IR0 (R):  active_power   (kW, scale=0.1, int16) — computed by PCS controller

Runs the PCS controller loop in a background thread within this process.
"""

from __future__ import annotations

import logging
import sys
import os

from pymodbus.server import StartTcpServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tcp_context import build_tcp_server_context

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

    hr_init = {0: 0}  # power_setpoint = 0
    ir_init = {0: 0}  # active_power = 0

    server_ctx, stores, lock = build_tcp_server_context(
        hr_size=10, ir_size=10,
        hr_init=hr_init, ir_init=ir_init,
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

    log.info(f"{device_name} TCP server listening on {host}:{port}")
    StartTcpServer(server_ctx, address=(host, port))


if __name__ == "__main__":
    run_pcs_server(
        device_name="PCS1",
        host="127.0.0.1", port=15021,
        paired_bms_host="127.0.0.1", paired_bms_port=15024,
        tick_interval_s=1.0,
    )
