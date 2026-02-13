"""
Debug client — developer-only tool to read any device directly.

NOT for mentor demo. Reads PCS/BMS registers directly by port.

Usage:
  python debug_client.py --host 127.0.0.1 --port 15021 --read-ir 0 3
  python debug_client.py --host 127.0.0.1 --port 15024 --read-ir 0 3
  python debug_client.py --host 127.0.0.1 --port 15020 --read-hr 0 1
  python debug_client.py --host 127.0.0.1 --port 15020 --write-hr 0 1000
"""

from __future__ import annotations

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tcp_servers"))

from pymodbus.client import ModbusTcpClient
from tcp_servers.tcp_context import decode_power_kw


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug Modbus TCP client (any device)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True, help="TCP port of target device")
    parser.add_argument("--slave", type=int, default=1)
    parser.add_argument("--read-hr", nargs=2, type=int, metavar=("ADDR", "COUNT"),
                        help="Read holding registers: addr count")
    parser.add_argument("--read-ir", nargs=2, type=int, metavar=("ADDR", "COUNT"),
                        help="Read input registers: addr count")
    parser.add_argument("--write-hr", nargs=2, type=int, metavar=("ADDR", "VALUE"),
                        help="Write single holding register: addr value_u16")

    args = parser.parse_args()
    client = ModbusTcpClient(args.host, port=args.port)
    client.connect()

    if args.read_hr:
        addr, count = args.read_hr
        rr = client.read_holding_registers(addr, count, slave=args.slave)
        if rr.isError():
            print(f"Error: {rr}")
        else:
            print(f"HR[{addr}..{addr+count-1}] = {rr.registers}")
            for i, v in enumerate(rr.registers):
                signed = v - 0x10000 if v >= 0x8000 else v
                print(f"  [{addr+i}] raw=0x{v:04X}  u16={v}  i16={signed}  "
                      f"power_kw={signed*0.1:.1f}")

    if args.read_ir:
        addr, count = args.read_ir
        rr = client.read_input_registers(addr, count, slave=args.slave)
        if rr.isError():
            print(f"Error: {rr}")
        else:
            print(f"IR[{addr}..{addr+count-1}] = {rr.registers}")
            for i, v in enumerate(rr.registers):
                signed = v - 0x10000 if v >= 0x8000 else v
                print(f"  [{addr+i}] raw=0x{v:04X}  u16={v}  i16={signed}  "
                      f"power_kw={signed*0.1:.1f}")

    if args.write_hr:
        addr, value = args.write_hr
        rr = client.write_register(addr, value & 0xFFFF, slave=args.slave)
        if rr.isError():
            print(f"Error: {rr}")
        else:
            print(f"HR[{addr}] written = 0x{value & 0xFFFF:04X}")

    client.close()


if __name__ == "__main__":
    main()
