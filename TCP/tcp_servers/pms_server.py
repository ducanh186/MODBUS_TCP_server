"""
PMS (SmartLogger) Modbus TCP server process — Huawei address map.

Address layout (Holding Registers only — FC03/FC06/FC10):
  HR  40420-40429  Control (active/reactive adj, direction, power factor)
  HR  40521-40577  Telemetry (input power, active power, voltages, currents)
  HR  40713-40722  Identity (ESN string)
  HR  50000-50001  Alarm (SmartLogger alarm bitfields)

No Input Registers — SmartLogger uses HR for everything.

Simulator extension:
  HR 40424 = demand_direction (0=discharge, 1=charge).
  Real spec uses 40424 as "Active adjustment (alternative)" U32.

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

from tcp_context import build_multirange_server_context
from specs.pms_registers import (
    CONTROL_RANGE_START,
    CONTROL_RANGE_SIZE,
    TELEMETRY_RANGE_START,
    TELEMETRY_RANGE_SIZE,
    IDENTITY_RANGE_START,
    IDENTITY_RANGE_SIZE,
    ALARM_RANGE_START,
    ALARM_RANGE_SIZE,
    build_static_init,
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
    *,
    suppression_host: str = "",
    suppression_port: int = 0,
) -> None:
    """Start the PMS TCP server and its controller thread."""

    # Build init values for all HR ranges
    all_init = build_static_init()

    # Split init by range
    def _pick(start, size):
        return {k: v for k, v in all_init.items() if start <= k < start + size}

    server_ctx, stores, lock = build_multirange_server_context(
        hr_ranges=[
            (CONTROL_RANGE_START, CONTROL_RANGE_SIZE, _pick(CONTROL_RANGE_START, CONTROL_RANGE_SIZE)),
            (TELEMETRY_RANGE_START, TELEMETRY_RANGE_SIZE, _pick(TELEMETRY_RANGE_START, TELEMETRY_RANGE_SIZE)),
            (IDENTITY_RANGE_START, IDENTITY_RANGE_SIZE, _pick(IDENTITY_RANGE_START, IDENTITY_RANGE_SIZE)),
            (ALARM_RANGE_START, ALARM_RANGE_SIZE),
        ],
        slave_id=0,
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
        suppression_host=suppression_host,
        suppression_port=suppression_port,
    )
    log.info(f"PMS controller thread started (tick={tick_interval_s}s)")

    log.info(
        "PMS Huawei registers: HR %d-%d (control), HR %d-%d (telemetry), "
        "HR %d-%d (identity), HR %d-%d (alarm)",
        CONTROL_RANGE_START, CONTROL_RANGE_START + CONTROL_RANGE_SIZE - 1,
        TELEMETRY_RANGE_START, TELEMETRY_RANGE_START + TELEMETRY_RANGE_SIZE - 1,
        IDENTITY_RANGE_START, IDENTITY_RANGE_START + IDENTITY_RANGE_SIZE - 1,
        ALARM_RANGE_START, ALARM_RANGE_START + ALARM_RANGE_SIZE - 1,
    )
    log.info(f"PMS unit_id=0, TCP server listening on {host}:{port}")
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
