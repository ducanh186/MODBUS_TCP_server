"""
PMS Modbus TCP server process.

Exposes:
  HR0 (RW): demand_control_power (kW, scale=0.1, int16)
  IR0 (R):  active_power_total   (kW, scale=0.1, int16)
  IR1 (R):  soc_avg              (%,  scale=1,   uint16)
  IR2 (R):  soh_avg              (%,  scale=1,   uint16)
  IR3 (R):  capacity_total       (kWh,scale=0.1, uint16)

Runs the PMS controller loop in a background thread within this process.
"""

from __future__ import annotations

import logging
import sys
import os

from pymodbus.server import StartTcpServer

# Allow imports when running as subprocess from project root
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
    format="%(asctime)s | PMS | %(levelname)s | %(message)s",
)
log = logging.getLogger("pms_server")


def run_pms_server(
    host: str,
    port: int,
    pcs_ports: dict[str, int],
    bms_ports: dict[str, int],
    pairing: dict[str, str],
    tick_interval_s: float,
) -> None:
    """Start the PMS TCP server and its controller thread."""

    # Initial register values
    hr_init = {0: 0}  # demand_control_power = 0
    ir_init = {
        0: 0,                          # active_power_total
        1: encode_soc(50.0),           # soc_avg
        2: encode_soh(100.0),          # soh_avg
        3: encode_capacity_kwh(200.0), # capacity_total (2 BMS × 100 kWh)
    }

    server_ctx, stores, lock = build_tcp_server_context(
        hr_size=10, ir_size=10,
        hr_init=hr_init, ir_init=ir_init,
        slave_id=1,
    )

    # Start controller thread
    from controllers.pms_controller import start_pms_controller
    ctrl_thread, ctrl_stop = start_pms_controller(
        stores=stores,
        lock=lock,
        host=host,
        pcs_ports=pcs_ports,
        bms_ports=bms_ports,
        pairing=pairing,
        tick_interval_s=tick_interval_s,
    )
    log.info(f"PMS controller thread started (tick={tick_interval_s}s)")

    log.info(f"PMS TCP server listening on {host}:{port}")
    StartTcpServer(server_ctx, address=(host, port))


if __name__ == "__main__":
    # Standalone launch for debugging
    run_pms_server(
        host="127.0.0.1", port=15020,
        pcs_ports={"pcs1": 15021, "pcs2": 15022},
        bms_ports={"bms1": 15024, "bms2": 15025},
        pairing={"pcs1": "bms1", "pcs2": "bms2"},
        tick_interval_s=1.0,
    )
