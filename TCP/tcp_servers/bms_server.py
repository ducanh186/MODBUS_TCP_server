"""
BMS Modbus TCP server process (parameterised by device name).

Exposes:
  IR0 (R): soc      (%,   scale=1,   uint16) — updated by BMS controller
  IR1 (R): soh      (%,   scale=1,   uint16) — static 100
  IR2 (R): capacity (kWh, scale=0.1, uint16) — static 100.0

Runs the BMS controller loop in a background thread within this process.
"""

from __future__ import annotations

import logging
import sys
import os

from pymodbus.server import StartTcpServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tcp_context import (
    build_tcp_server_context,
    encode_soc,
    encode_soh,
    encode_capacity_kwh,
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

    ir_init = {
        0: encode_soc(init_soc),
        1: encode_soh(init_soh),
        2: encode_capacity_kwh(init_capacity_kwh),
    }

    server_ctx, stores, lock = build_tcp_server_context(
        hr_size=0, ir_size=10,
        hr_init=None, ir_init=ir_init,
        slave_id=1,
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

    log.info(f"{device_name} TCP server listening on {host}:{port}")
    StartTcpServer(server_ctx, address=(host, port))


if __name__ == "__main__":
    run_bms_server(
        device_name="BMS1",
        host="127.0.0.1", port=15024,
        paired_pcs_host="127.0.0.1", paired_pcs_port=15021,
        tick_interval_s=1.0,
    )
