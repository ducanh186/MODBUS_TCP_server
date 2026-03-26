from __future__ import annotations

import argparse
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tcp_servers"))

from pymodbus.client import ModbusTcpClient, ModbusSerialClient
from tcp_servers.tcp_context import decode_power_kw
from register_codec import decode_i32

DEFAULT_HOST = "127.0.0.1"
PCS1_PORT = 15021
PCS2_PORT = 15022
RTU_COM = "COM5"
RTU_SLAVE = 10
RTU_BAUD = 9600
LOSS_RATIO = 0.01
TOLERANCE_KW = 0.2


def read_pcs_ir0(host: str, port: int) -> float:
    client = ModbusTcpClient(host, port=port)
    client.connect()
    rr = client.read_input_registers(32080, count=2, device_id=0)
    client.close()
    if rr.isError():
        raise RuntimeError(f"Cannot read PCS on port {port}: {rr}")
    return decode_i32(list(rr.registers), gain=1000)


def read_mm_ir0(com_port: str, slave_id: int, baudrate: int) -> float:
    client = ModbusSerialClient(
        port=com_port,
        baudrate=baudrate,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=2,
    )
    client.connect()
    rr = client.read_input_registers(0, count=1, device_id=slave_id)
    client.close()
    if rr.isError():
        raise RuntimeError(f"Cannot read Multimeter on {com_port}: {rr}")
    return decode_power_kw(rr.registers[0])


def main() -> None:
    parser = argparse.ArgumentParser(description="RTU Smoke Test")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--pcs1-port", type=int, default=PCS1_PORT)
    parser.add_argument("--pcs2-port", type=int, default=PCS2_PORT)
    parser.add_argument("--rtu-com", default=RTU_COM)
    parser.add_argument("--rtu-slave", type=int, default=RTU_SLAVE)
    parser.add_argument("--rtu-baud", type=int, default=RTU_BAUD)
    parser.add_argument("--loss-ratio", type=float, default=LOSS_RATIO)
    parser.add_argument("--tolerance", type=float, default=TOLERANCE_KW)
    parser.add_argument(
        "--wait", type=float, default=2.0,
        help="Seconds to wait before reading (let updater cycle)",
    )
    args = parser.parse_args()

    print(f"Waiting {args.wait}s for updater cycle...")
    time.sleep(args.wait)

    print(f"\n--- Step 1: Read PCS1 IR0 (TCP :{args.pcs1_port}) ---")
    pcs1_kw = read_pcs_ir0(args.host, args.pcs1_port)
    print(f"  PCS1 active_power = {pcs1_kw:+.1f} kW")

    print(f"\n--- Step 2: Read PCS2 IR0 (TCP :{args.pcs2_port}) ---")
    pcs2_kw = read_pcs_ir0(args.host, args.pcs2_port)
    print(f"  PCS2 active_power = {pcs2_kw:+.1f} kW")

    print(f"\n--- Step 3: Read Multimeter IR0 (RTU {args.rtu_com} slave={args.rtu_slave}) ---")
    mm_kw = read_mm_ir0(args.rtu_com, args.rtu_slave, args.rtu_baud)
    print(f"  Multimeter active_power = {mm_kw:+.1f} kW")

    expected_kw = (pcs1_kw + pcs2_kw) * (1.0 - args.loss_ratio)
    delta = abs(mm_kw - expected_kw)

    print(f"\n--- Step 4: Validate ---")
    print(f"  Expected: ({pcs1_kw:+.1f} + {pcs2_kw:+.1f}) * (1 - {args.loss_ratio}) = {expected_kw:+.1f} kW")
    print(f"  Actual:   {mm_kw:+.1f} kW")
    print(f"  Delta:    {delta:.2f} kW (tolerance +/-{args.tolerance} kW)")

    if delta <= args.tolerance:
        print(f"\n  PASS — Multimeter IR0 matches expected within +/-{args.tolerance} kW")
        sys.exit(0)
    else:
        print(f"\n  FAIL — Delta {delta:.2f} kW exceeds tolerance +/-{args.tolerance} kW")
        sys.exit(1)


if __name__ == "__main__":
    main()
