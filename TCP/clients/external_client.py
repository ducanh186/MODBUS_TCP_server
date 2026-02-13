"""
External client — talks ONLY to PMS (TCP) and Multimeter (RTU).

Usage:
  # Write demand to PMS
  python external_client.py --pms-host 127.0.0.1 --pms-port 15020 --set-kw 1000

  # Read PMS aggregates
  python external_client.py --pms-host 127.0.0.1 --pms-port 15020 --read-pms

  # Read multimeter via RTU
  python external_client.py --rtu-com COM11 --read-multimeter

  # Combined: set demand + read PMS + read multimeter
  python external_client.py --pms-host 127.0.0.1 --pms-port 15020 --set-kw 1000 --read-pms --rtu-com COM11 --read-multimeter
"""

from __future__ import annotations

import argparse
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tcp_servers"))

from pymodbus.client import ModbusTcpClient, ModbusSerialClient

from tcp_servers.tcp_context import (
    encode_power_kw,
    decode_power_kw,
    decode_soc,
    decode_soh,
    decode_capacity_kwh,
)

# PMS register addresses (0-based)
PMS_HR0_DEMAND = 0
PMS_IR0_TOTAL_POWER = 0
PMS_IR1_SOC_AVG = 1
PMS_IR2_SOH_AVG = 2
PMS_IR3_CAP_TOTAL = 3

# Multimeter
MM_IR0_ACTIVE_POWER = 0


def write_pms_demand(host: str, port: int, kw: float) -> None:
    """Write demand_control_power to PMS HR0."""
    client = ModbusTcpClient(host, port=port)
    client.connect()
    u16 = encode_power_kw(kw)
    rr = client.write_register(PMS_HR0_DEMAND, u16, slave=1)
    if rr.isError():
        print(f"ERROR writing PMS demand: {rr}")
    else:
        print(f"PMS demand set to {kw} kW (raw 0x{u16:04X})")
    client.close()


def read_pms(host: str, port: int) -> None:
    """Read PMS HR0 + IR0..IR3 and display."""
    client = ModbusTcpClient(host, port=port)
    client.connect()

    # HR0 demand
    rr = client.read_holding_registers(PMS_HR0_DEMAND, 1, slave=1)
    if rr.isError():
        print(f"ERROR reading PMS HR0: {rr}")
        demand_kw = None
    else:
        demand_kw = decode_power_kw(rr.registers[0])

    # IR0..IR3
    rr = client.read_input_registers(PMS_IR0_TOTAL_POWER, 4, slave=1)
    if rr.isError():
        print(f"ERROR reading PMS IR: {rr}")
        client.close()
        return

    total_power = decode_power_kw(rr.registers[0])
    soc_avg = decode_soc(rr.registers[1])
    soh_avg = decode_soh(rr.registers[2])
    cap_total = decode_capacity_kwh(rr.registers[3])

    print("=== PMS Registers ===")
    if demand_kw is not None:
        print(f"  HR0 demand_control_power : {demand_kw:+.1f} kW")
    print(f"  IR0 active_power_total   : {total_power:+.1f} kW")
    print(f"  IR1 soc_avg              : {soc_avg:.0f} %")
    print(f"  IR2 soh_avg              : {soh_avg:.0f} %")
    print(f"  IR3 capacity_total       : {cap_total:.1f} kWh")
    client.close()


def read_multimeter(com_port: str, slave_id: int = 10, baudrate: int = 9600) -> None:
    """Read multimeter IR0 via Modbus RTU."""
    client = ModbusSerialClient(
        port=com_port,
        baudrate=baudrate,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=2,
    )
    client.connect()
    rr = client.read_input_registers(MM_IR0_ACTIVE_POWER, 1, slave=slave_id)
    if rr.isError():
        print(f"ERROR reading multimeter: {rr}")
    else:
        power_kw = decode_power_kw(rr.registers[0])
        print("=== Multimeter (RTU) ===")
        print(f"  IR0 active_power : {power_kw:+.1f} kW")
    client.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="External Modbus client — PMS (TCP) + Multimeter (RTU) only"
    )
    parser.add_argument("--pms-host", default="127.0.0.1")
    parser.add_argument("--pms-port", type=int, default=15020)
    parser.add_argument("--set-kw", type=float, default=None,
                        help="Write demand_control_power to PMS (kW)")
    parser.add_argument("--read-pms", action="store_true",
                        help="Read PMS aggregates")
    parser.add_argument("--rtu-com", default=None,
                        help="COM port for multimeter RTU (e.g. COM11)")
    parser.add_argument("--rtu-slave", type=int, default=10)
    parser.add_argument("--rtu-baud", type=int, default=9600)
    parser.add_argument("--read-multimeter", action="store_true",
                        help="Read multimeter active_power via RTU")
    parser.add_argument("--loop", type=float, default=0,
                        help="If >0, repeat read every N seconds")

    args = parser.parse_args()

    if args.set_kw is not None:
        write_pms_demand(args.pms_host, args.pms_port, args.set_kw)
        # Small delay so controller picks up the new demand
        time.sleep(0.5)

    if args.loop > 0:
        try:
            while True:
                if args.read_pms:
                    read_pms(args.pms_host, args.pms_port)
                if args.read_multimeter and args.rtu_com:
                    read_multimeter(args.rtu_com, args.rtu_slave, args.rtu_baud)
                print()
                time.sleep(args.loop)
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        if args.read_pms:
            read_pms(args.pms_host, args.pms_port)
        if args.read_multimeter and args.rtu_com:
            read_multimeter(args.rtu_com, args.rtu_slave, args.rtu_baud)

    if not any([args.set_kw is not None, args.read_pms, args.read_multimeter]):
        parser.print_help()


if __name__ == "__main__":
    main()
