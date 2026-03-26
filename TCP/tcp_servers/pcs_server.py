"""
PCS Modbus TCP server process (parameterised by device name).

Address layout (Huawei PCS2000HA full map):
  IR  30000-30088  Identity + Rating (read-only static)
  IR  32000-32013  Running status + Alarms (dynamic, controller writes)
  IR  32064-32090  Power readings (dynamic, controller writes active_power)
  IR  32463-32468  Battery cluster on PCS (dynamic)
  HR  40039-40044  Control commands (PMS writes fixed_active_p at 40043)
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
    STATUS_RANGE_START,
    STATUS_RANGE_SIZE,
    POWER_RANGE_START,
    POWER_RANGE_SIZE,
    BATTERY_RANGE_START,
    BATTERY_RANGE_SIZE,
    CONTROL_RANGE_START,
    CONTROL_RANGE_SIZE,
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
    transducer_host: str = "",
    transducer_port: int = 0,
) -> None:
    """Start a PCS TCP server and its controller thread."""

    # Build Huawei static init data (identity + rating)
    static_init = build_static_init(overrides={"sn": f"SIM-{device_name}"})

    server_ctx, stores, lock = build_multirange_server_context(
        hr_ranges=[
            (CONTROL_RANGE_START, CONTROL_RANGE_SIZE, {}),         # HR 40039-40044: control
        ],
        ir_ranges=[
            (STATIC_RANGE_START, STATIC_RANGE_SIZE, static_init),  # IR 30000-30088: identity+rating
            (STATUS_RANGE_START, STATUS_RANGE_SIZE, {}),           # IR 32000-32013: status+alarms
            (POWER_RANGE_START, POWER_RANGE_SIZE, {}),             # IR 32064-32090: power readings
            (BATTERY_RANGE_START, BATTERY_RANGE_SIZE, {}),         # IR 32463-32468: battery cluster
        ],
        slave_id=0,
    )

    from controllers.pcs_controller import start_pcs_controller
    ctrl_thread, ctrl_stop = start_pcs_controller(
        device_name=device_name,
        stores=stores,
        lock=lock,
        paired_bms_host=paired_bms_host,
        paired_bms_port=paired_bms_port,
        transducer_host=transducer_host,
        transducer_port=transducer_port,
        tick_interval_s=tick_interval_s,
    )
    log.info(f"{device_name} controller thread started (tick={tick_interval_s}s)")
    log.info(f"{device_name} Huawei registers: IR {STATIC_RANGE_START}-{STATIC_RANGE_START + STATIC_RANGE_SIZE - 1} (static), "
             f"IR {POWER_RANGE_START}-{POWER_RANGE_START + POWER_RANGE_SIZE - 1} (power), "
             f"HR {CONTROL_RANGE_START}-{CONTROL_RANGE_START + CONTROL_RANGE_SIZE - 1} (control)")
    log.info(f"{device_name} unit_id=0, TCP server listening on {host}:{port}")
    StartTcpServer(server_ctx, address=(host, port))


if __name__ == "__main__":
    run_pcs_server(
        device_name="PCS1",
        host="127.0.0.1", port=15021,
        paired_bms_host="127.0.0.1", paired_bms_port=15024,
        tick_interval_s=1.0,
        transducer_host="127.0.0.1", transducer_port=15026,
    )
