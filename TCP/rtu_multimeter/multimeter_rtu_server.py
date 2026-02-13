"""
Multimeter RTU server + updater — runs as a separate process.

Exposes:
  IR0 (R): active_power (kW, scale=0.1, int16)
           = (1 - loss_ratio) * (PCS1.active_power + PCS2.active_power)

Uses pymodbus ModbusSerialServer on a com0com virtual port (e.g. COM10).
An updater thread polls PCS1 and PCS2 via Modbus TCP every 1 second.
"""

from __future__ import annotations

import logging
import sys
import os
import threading
import time
from typing import Dict

from pymodbus.server import StartSerialServer
from pymodbus.client import ModbusTcpClient
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tcp_servers"))

from tcp_servers.tcp_context import (
    LockedDataBlock,
    RejectAllDataBlock,
    ZeroBasedDeviceContext,
    encode_power_kw,
    decode_power_kw,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | MULTIMETER | %(levelname)s | %(message)s",
)
log = logging.getLogger("multimeter")

# Register address (0-based)
IR0_ACTIVE_POWER = 0
PCS_IR0_ACTIVE_POWER = 0


def _updater_loop(
    stores: Dict[str, LockedDataBlock],
    lock: threading.RLock,
    host: str,
    pcs_ports: Dict[str, int],
    loss_ratio: float,
    stop_event: threading.Event,
    interval_s: float = 1.0,
) -> None:
    """Background thread: polls PCS active powers, computes multimeter IR0."""
    log.info("Multimeter updater started")
    while not stop_event.is_set():
        total_pcs_kw = 0.0
        for pcs_name, pcs_port in pcs_ports.items():
            try:
                client = ModbusTcpClient(host, port=pcs_port)
                client.connect()
                rr = client.read_input_registers(PCS_IR0_ACTIVE_POWER, 1, slave=1)
                if not rr.isError():
                    total_pcs_kw += decode_power_kw(rr.registers[0])
                client.close()
            except Exception:
                log.warning(f"Multimeter: cannot read {pcs_name} on port {pcs_port}")

        mm_power_kw = (1.0 - loss_ratio) * total_pcs_kw

        with lock:
            stores["ir"].setValues(IR0_ACTIVE_POWER, [encode_power_kw(mm_power_kw)])

        stop_event.wait(interval_s)


def run_multimeter_server(
    com_port: str,
    slave_id: int,
    baudrate: int,
    host: str,
    pcs_ports: Dict[str, int],
    loss_ratio: float,
    tick_interval_s: float = 1.0,
) -> None:
    """Start multimeter RTU server and updater thread."""

    lock = threading.RLock()
    ir_block = LockedDataBlock(lock, 10, {0: 0})

    device_ctx = ZeroBasedDeviceContext(
        di=RejectAllDataBlock(0, [0]),
        co=RejectAllDataBlock(0, [0]),
        hr=RejectAllDataBlock(0, [0]),
        ir=ir_block,
    )
    server_ctx = ModbusServerContext(
        devices={slave_id: device_ctx}, single=False,
    )
    stores = {"ir": ir_block}

    # Start updater thread
    stop_event = threading.Event()
    updater = threading.Thread(
        target=_updater_loop,
        args=(stores, lock, host, pcs_ports, loss_ratio, stop_event, tick_interval_s),
        daemon=True,
    )
    updater.start()

    log.info(f"Multimeter RTU server on {com_port} (slave_id={slave_id}, baud={baudrate})")
    try:
        StartSerialServer(
            server_ctx,
            port=com_port,
            baudrate=baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=1,
        )
    except Exception:
        log.exception(f"Failed to start RTU server on {com_port}")
        stop_event.set()


if __name__ == "__main__":
    run_multimeter_server(
        com_port="COM10",
        slave_id=10,
        baudrate=9600,
        host="127.0.0.1",
        pcs_ports={"pcs1": 15021, "pcs2": 15022},
        loss_ratio=0.01,
    )
