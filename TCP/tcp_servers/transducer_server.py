"""
Transducer Modbus TCP server process — simulates grid frequency sensor.

Exposes:
  IR0 (R): frequency_hz (Hz, scale=0.001, uint16) — updated by controller every 0.1s

Read-only device (no holding registers).
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
    encode_frequency_hz,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | TRANSDUCER | %(levelname)s | %(message)s",
)
log = logging.getLogger("transducer_server")


def run_transducer_server(
    device_name: str,
    host: str,
    port: int,
    tick_interval_s: float = 0.1,
) -> None:
    """Start a Transducer TCP server and its controller thread."""

    ir_init = {
        0: encode_frequency_hz(50.0),   # 50.000 Hz → 50000
    }

    server_ctx, stores, lock = build_tcp_server_context(
        hr_size=0, ir_size=10,
        hr_init=None, ir_init=ir_init,
        slave_id=1,
    )

    from controllers.transducer_controller import start_transducer_controller
    ctrl_thread, ctrl_stop = start_transducer_controller(
        device_name=device_name,
        stores=stores,
        lock=lock,
        tick_interval_s=tick_interval_s,
    )
    log.info(f"{device_name} controller thread started (tick={tick_interval_s}s)")

    log.info(f"{device_name} TCP server listening on {host}:{port}")
    StartTcpServer(server_ctx, address=(host, port))


if __name__ == "__main__":
    run_transducer_server(
        device_name="TRANSDUCER",
        host="127.0.0.1", port=15026,
    )
