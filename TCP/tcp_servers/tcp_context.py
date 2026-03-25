"""
Shared helpers for building Modbus TCP server contexts and locked datastores.

Provides:
- LockedDataBlock:              Thread-safe 0-based ModbusSequentialDataBlock.
- MultiRangeDataBlock:          Thread-safe multi-range DataBlock for Huawei addresses.
- RejectAllDataBlock:           Returns ILLEGAL_ADDRESS for unsupported function codes.
- ZeroBasedDeviceContext:       Cancels pymodbus 3.x implicit +1 on address.
- build_tcp_server_context:     Factory for single-device 0-based context.
- build_multirange_server_context: Factory for Huawei-style multi-range context.
- encode_init:                  Convert a float init value to uint16 via scale.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional, Tuple

from pymodbus.datastore import (
    ModbusDeviceContext,
    ModbusSequentialDataBlock,
    ModbusServerContext,
)
from pymodbus.datastore.store import ExcCodes


# ---------------------------------------------------------------------------
# DataBlock classes
# ---------------------------------------------------------------------------

class LockedDataBlock(ModbusSequentialDataBlock):
    """Thread-safe 0-based datablock guarded by an RLock."""

    def __init__(self, lock: threading.RLock, size: int,
                 init_values: Optional[Dict[int, int]] = None):
        values = [0] * size
        if init_values:
            for addr, u16 in init_values.items():
                values[addr] = u16
        super().__init__(0, values)
        self._lock = lock

    def getValues(self, address: int, count: int = 1) -> List[int]:
        with self._lock:
            return super().getValues(address, count)

    def setValues(self, address: int, values: List[int]) -> None:
        with self._lock:
            return super().setValues(address, values)


class RejectAllDataBlock(ModbusSequentialDataBlock):
    """DataBlock that rejects every read/write with ILLEGAL_ADDRESS."""

    def getValues(self, address: int, count: int = 1):
        return ExcCodes.ILLEGAL_ADDRESS

    def setValues(self, address: int, values: List[int]):
        return ExcCodes.ILLEGAL_ADDRESS


class MultiRangeDataBlock(ModbusSequentialDataBlock):
    """DataBlock supporting multiple non-contiguous address ranges.

    Each range is a contiguous island of registers backed by a small list.
    Reads/writes that fall entirely within one range succeed.
    Addresses outside any range or crossing range boundaries → ILLEGAL_ADDRESS.

    Example:
        ranges = [
            (30000, 85),                          # identity+rating, 85 regs
            (32000, 91),                          # status+power,    91 regs
            (32000, 91, {32080: 0, 32085: 0}),   # with init values
        ]
    """

    def __init__(self, lock: threading.RLock,
                 ranges: List[tuple]) -> None:
        super().__init__(0, [0])  # dummy init for parent
        self._lock = lock
        self._ranges: Dict[int, Dict] = {}  # {start: {"size": n, "values": [...]}}

        for r in ranges:
            if len(r) == 3:
                start, size, init_vals = r
            else:
                start, size = r
                init_vals = None
            values = [0] * size
            if init_vals:
                for addr, val in init_vals.items():
                    offset = addr - start
                    if 0 <= offset < size:
                        values[offset] = val
            self._ranges[start] = {"size": size, "values": values}

    def _find_range(self, address: int, count: int = 1):
        """Return (start, range_dict) if [address, address+count) is within one range."""
        for start, rng in self._ranges.items():
            if start <= address and address + count <= start + rng["size"]:
                return start, rng
        return None, None

    def validate(self, address: int, count: int = 1) -> bool:
        start, _ = self._find_range(address, count)
        return start is not None

    def getValues(self, address: int, count: int = 1):
        with self._lock:
            start, rng = self._find_range(address, count)
            if start is None:
                return ExcCodes.ILLEGAL_ADDRESS
            offset = address - start
            return list(rng["values"][offset: offset + count])

    def setValues(self, address: int, values: List[int]):
        with self._lock:
            count = len(values)
            start, rng = self._find_range(address, count)
            if start is None:
                return ExcCodes.ILLEGAL_ADDRESS
            offset = address - start
            rng["values"][offset: offset + count] = values


# ---------------------------------------------------------------------------
# ZeroBasedDeviceContext
# ---------------------------------------------------------------------------

class ZeroBasedDeviceContext(ModbusDeviceContext):
    """
    Override to NOT add +1 to address.

    pymodbus 3.x parent does ``address += 1`` in getValues/setValues.
    We skip that so protocol address 0 → DataBlock index 0.
    """

    def getValues(self, func_code: int, address: int, count: int = 1):
        return self.store[self.decode(func_code)].getValues(address, count)

    def setValues(self, func_code: int, address: int, values: List[int]):
        return self.store[self.decode(func_code)].setValues(address, values)


# ---------------------------------------------------------------------------
# Codec helpers (kept from device.py for consistency)
# ---------------------------------------------------------------------------

def _int16_to_u16(x: int) -> int:
    """Signed int16 → unsigned uint16."""
    return x & 0xFFFF


def _u16_to_int16(x: int) -> int:
    """Unsigned uint16 → signed int16."""
    return x - 0x10000 if x >= 0x8000 else x


def encode_power_kw(kw: float) -> int:
    """kW (float, scale 0.1) → uint16 (two's complement)."""
    raw = int(round(kw / 0.1))
    return _int16_to_u16(raw)


def decode_power_kw(reg_u16: int) -> float:
    """uint16 → kW float (scale 0.1, signed)."""
    return _u16_to_int16(reg_u16 & 0xFFFF) * 0.1


def encode_soc(percent: float) -> int:
    """SOC % → uint16, scale=1, clamp [0,100]."""
    return int(round(max(0.0, min(100.0, percent)))) & 0xFFFF


def decode_soc(reg_u16: int) -> float:
    return float(reg_u16 & 0xFFFF)


def encode_soh(percent: float) -> int:
    return int(round(max(0.0, min(100.0, percent)))) & 0xFFFF


def decode_soh(reg_u16: int) -> float:
    return float(reg_u16 & 0xFFFF)


def encode_capacity_kwh(kwh: float) -> int:
    """Capacity kWh → uint16, scale=0.1, clamp ≥ 0."""
    raw = int(round(max(0.0, kwh) / 0.1))
    return raw & 0xFFFF


def decode_capacity_kwh(reg_u16: int) -> float:
    return (reg_u16 & 0xFFFF) * 0.1


def encode_frequency_hz(hz: float) -> int:
    """Frequency Hz → uint16, scale 0.001 Hz (50.000 Hz → 50000)."""
    return int(round(max(0.0, hz) / 0.001)) & 0xFFFF


def decode_frequency_hz(reg_u16: int) -> float:
    """uint16 → frequency Hz (scale 0.001)."""
    return (reg_u16 & 0xFFFF) * 0.001


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_tcp_server_context(
    *,
    hr_size: int = 10,
    ir_size: int = 10,
    hr_init: Optional[Dict[int, int]] = None,
    ir_init: Optional[Dict[int, int]] = None,
    slave_id: int = 1,
) -> Tuple[ModbusServerContext, Dict[str, LockedDataBlock], threading.RLock]:
    """
    Build a single-slave Modbus server context.

    Returns:
        (server_context, {"hr": block, "ir": block}, lock)
    """
    lock = threading.RLock()

    hr = LockedDataBlock(lock, hr_size, hr_init) if hr_size > 0 else RejectAllDataBlock(0, [0])
    ir = LockedDataBlock(lock, ir_size, ir_init) if ir_size > 0 else RejectAllDataBlock(0, [0])

    device_ctx = ZeroBasedDeviceContext(
        di=RejectAllDataBlock(0, [0]),
        co=RejectAllDataBlock(0, [0]),
        hr=hr,
        ir=ir,
    )

    server_ctx = ModbusServerContext(devices={slave_id: device_ctx}, single=False)
    stores = {"hr": hr, "ir": ir}
    return server_ctx, stores, lock


def build_multirange_server_context(
    *,
    hr_ranges: Optional[List[tuple]] = None,
    ir_ranges: Optional[List[tuple]] = None,
    slave_id: int = 1,
) -> Tuple[ModbusServerContext, Dict[str, MultiRangeDataBlock], threading.RLock]:
    """Build a server context using MultiRangeDataBlock for Huawei-style addresses.

    Args:
        hr_ranges: list of (start, size) or (start, size, {addr: val}) for holding registers
        ir_ranges: same for input registers
        slave_id:  Modbus unit id (default 1)

    Returns:
        (server_context, {"hr": block, "ir": block}, lock)

    Example:
        ctx, stores, lock = build_multirange_server_context(
            hr_ranges=[(40039, 163)],
            ir_ranges=[(30000, 85), (32000, 91)],
        )
    """
    lock = threading.RLock()

    hr = MultiRangeDataBlock(lock, hr_ranges) if hr_ranges else RejectAllDataBlock(0, [0])
    ir = MultiRangeDataBlock(lock, ir_ranges) if ir_ranges else RejectAllDataBlock(0, [0])

    device_ctx = ZeroBasedDeviceContext(
        di=RejectAllDataBlock(0, [0]),
        co=RejectAllDataBlock(0, [0]),
        hr=hr,
        ir=ir,
    )

    server_ctx = ModbusServerContext(devices={slave_id: device_ctx}, single=False)
    stores = {"hr": hr, "ir": ir}
    return server_ctx, stores, lock
