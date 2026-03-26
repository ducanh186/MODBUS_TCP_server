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
from serial.tools import list_ports as _serial_list_ports
from serial import SerialException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tcp_servers"))

from tcp_servers.tcp_context import (
    LockedDataBlock,
    RejectAllDataBlock,
    ZeroBasedDeviceContext,
    encode_power_kw,
)
from register_codec import decode_i32

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | MULTIMETER | %(levelname)s | %(message)s",
)
log = logging.getLogger("multimeter")

IR0_ACTIVE_POWER = 0
PCS_IR_ACTIVE_POWER = 32080   # Huawei PCS2000HA: I32, gain=1000
PCS_GAIN_POWER = 1000

SERIAL_PORT = os.getenv("MM_RTU_PORT", "COM6")
DEVICE_ID = int(os.getenv("MM_RTU_DEVICE_ID", "10"))


def _updater_loop(
    stores: Dict[str, LockedDataBlock],
    lock: threading.RLock,
    host: str,
    pcs_ports: Dict[str, int],
    loss_ratio: float,
    stop_event: threading.Event,
    interval_s: float = 1.0,
    slave_id: int = 10,
    com_port: str = "COM6",
) -> None:
    log.info("Multimeter updater started")

    last_good: Dict[str, float] = {name: 0.0 for name in pcs_ports}
    comm_status: Dict[str, str] = {name: "unknown" for name in pcs_ports}
    error_counts: Dict[str, int] = {name: 0 for name in pcs_ports}

    while not stop_event.is_set():
        total_pcs_kw = 0.0
        degraded = False

        for pcs_name, pcs_port in pcs_ports.items():
            try:
                client = ModbusTcpClient(host, port=pcs_port)
                client.connect()
                rr = client.read_input_registers(
                    PCS_IR_ACTIVE_POWER, count=2, device_id=0,
                )
                if not rr.isError():
                    pcs_kw = decode_i32(list(rr.registers), gain=PCS_GAIN_POWER)
                    last_good[pcs_name] = pcs_kw
                    comm_status[pcs_name] = "ok"
                    error_counts[pcs_name] = 0
                    total_pcs_kw += pcs_kw
                else:
                    total_pcs_kw += last_good[pcs_name]
                    comm_status[pcs_name] = "degraded"
                    error_counts[pcs_name] += 1
                    degraded = True
                    log.warning(
                        f"{pcs_name}: read error ({rr}) — using last good "
                        f"{last_good[pcs_name]:+.1f} kW "
                        f"(consecutive_errors={error_counts[pcs_name]})"
                    )
                client.close()
            except Exception:
                total_pcs_kw += last_good[pcs_name]
                comm_status[pcs_name] = "degraded"
                error_counts[pcs_name] += 1
                degraded = True
                log.warning(
                    f"{pcs_name}: TCP poll failed port {pcs_port} — "
                    f"using last good {last_good[pcs_name]:+.1f} kW "
                    f"(consecutive_errors={error_counts[pcs_name]})",
                    exc_info=(error_counts[pcs_name] <= 3),
                )

        mm_power_kw = (1.0 - loss_ratio) * total_pcs_kw
        ir0_encoded = encode_power_kw(mm_power_kw)

        with lock:
            stores["ir"].setValues(IR0_ACTIVE_POWER, [ir0_encoded])

        pcs_detail = ", ".join(
            f"{n}={last_good[n]:+.1f}kW[{comm_status[n]}]"
            for n in pcs_ports
        )
        tag = "DEGRADED" if degraded else "OK"
        log.info(
            f"[{tag}] {pcs_detail} | "
            f"sum={total_pcs_kw:+.1f}kW loss={loss_ratio} "
            f"ir0=0x{ir0_encoded:04X}({mm_power_kw:+.1f}kW) | "
            f"dev={slave_id} port={com_port}"
        )

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
    com_port = com_port.upper().strip()

    available = [p.device.upper().strip() for p in _serial_list_ports.comports()]
    if com_port not in available:
        log.warning(
            f"COM port {com_port} not found in system "
            f"(available: {available if available else 'none'}) "
            f"— skipping Multimeter RTU server"
        )
        return

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

    stop_event = threading.Event()
    updater = threading.Thread(
        target=_updater_loop,
        args=(stores, lock, host, pcs_ports, loss_ratio, stop_event,
              tick_interval_s, slave_id, com_port),
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
    except FileNotFoundError as exc:
        log.warning(f"COM port {com_port} not found when opening: {exc} — Multimeter not started")
        stop_event.set()
    except SerialException as exc:
        msg = str(exc).lower()
        if "access is denied" in msg or "permissionerror" in msg or "permission" in msg:
            log.error(
                f"COM port {com_port} is busy or access denied: {exc} "
                f"— close the other application and restart"
            )
        else:
            log.exception(f"Serial error on {com_port}")
        stop_event.set()
    except Exception:
        log.exception(f"Unexpected error starting RTU server on {com_port}")
        stop_event.set()


if __name__ == "__main__":
    run_multimeter_server(
        com_port=SERIAL_PORT,
        slave_id=DEVICE_ID,
        baudrate=9600,
        host="127.0.0.1",
        pcs_ports={"pcs1": 15021, "pcs2": 15022},
        loss_ratio=0.01,
    )
