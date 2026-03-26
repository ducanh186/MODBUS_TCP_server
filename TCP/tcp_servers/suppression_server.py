"""
Suppression Logger Modbus TCP server process — 抑制 signal.

Exposes:
  HR0 (RW): suppression_percent (%, uint16, range 0-100, default 100)

No controller thread — purely a register store that clients write to.
PMS reads HR0 each tick to enforce discharge suppression.
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
    format="%(asctime)s | SUPPRESSION | %(levelname)s | %(message)s",
)
log = logging.getLogger("suppression_server")


def run_suppression_server(
    device_name: str,
    host: str,
    port: int,
) -> None:
    """Start a Suppression Logger TCP server (no controller needed)."""

    hr_init = {0: 100}  # suppression_percent default = 100 (no suppression)

    server_ctx, stores, lock = build_tcp_server_context(
        hr_size=10, ir_size=0,
        hr_init=hr_init, ir_init=None,
        slave_id=0,
    )

    log.info(f"{device_name} TCP server listening on {host}:{port}")
    log.info(f"{device_name} HR0 = suppression_percent (default=100, range 0-100)")
    StartTcpServer(server_ctx, address=(host, port))


if __name__ == "__main__":
    run_suppression_server(
        device_name="SUPPRESSION",
        host="127.0.0.1", port=15027,
    )
