"""
Modbus TCP server context and identity factory.

Addressing — 0-based everywhere:
    pymodbus 3.x ModbusDeviceContext.getValues/setValues silently do
    ``address += 1`` before forwarding to the DataBlock.  We override that
    in ZeroBasedDeviceContext so protocol address 0 → DataBlock index 0.
    Tick code, client code, and devices_spec all use 0-based addresses.

Threading — shared RLock:
    One threading.RLock guards every DataBlock read/write.
    * LockedDataBlock.getValues/setValues acquire the lock per-call,
      so Modbus-server reads are safe against concurrent tick writes.
    * tick_once() also wraps a full batch in ``with lock:`` for
      cross-device consistency.  RLock is reentrant, so the inner
      per-register calls don't deadlock.
"""

import threading

from pymodbus.datastore import (
    ModbusDeviceContext,
    ModbusSequentialDataBlock,
    ModbusServerContext,
)
from pymodbus.datastore.store import ExcCodes
from pymodbus import ModbusDeviceIdentification

from device import DeviceModel
from devices_spec import DEVICES


# ---------------------------------------------------------------------------
# DataBlock classes
# ---------------------------------------------------------------------------

class LockedDataBlock(ModbusSequentialDataBlock):
    """
    Thread-safe 0-based datablock.

    Storage: values[i] corresponds to register address i.  No padding slot.
    Every public access is guarded by a shared RLock.
    """

    def __init__(self, lock, size, init_values=None):
        """
        Args:
            lock:        threading.RLock shared across all blocks.
            size:        number of registers (e.g. 10).
            init_values: dict {0-based addr: uint16} for non-zero init.
        """
        values = [0] * size
        if init_values:
            for addr, u16 in init_values.items():
                values[addr] = u16
        super().__init__(0, values)
        self._lock = lock

    def getValues(self, address, count=1):
        with self._lock:
            return super().getValues(address, count)

    def setValues(self, address, values):
        with self._lock:
            return super().setValues(address, values)


class RejectAllDataBlock(ModbusSequentialDataBlock):
    """DataBlock that rejects every read/write with ILLEGAL_ADDRESS."""

    def getValues(self, address, count=1):
        return ExcCodes.ILLEGAL_ADDRESS

    def setValues(self, address, values):
        return ExcCodes.ILLEGAL_ADDRESS


# ---------------------------------------------------------------------------
# ZeroBasedDeviceContext — cancel pymodbus's implicit +1
# ---------------------------------------------------------------------------

class ZeroBasedDeviceContext(ModbusDeviceContext):
    """
    Override getValues/setValues to NOT add +1.

    pymodbus 3.x parent does ``address += 1`` in both methods.
    We skip that so protocol address 0 → DataBlock address 0.
    async variants (async_getValues/async_setValues) delegate to
    these sync methods via MRO, so they also get the fix.
    """

    def getValues(self, func_code, address, count=1):
        return self.store[self.decode(func_code)].getValues(address, count)

    def setValues(self, func_code, address, values):
        return self.store[self.decode(func_code)].setValues(address, values)


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def _build_init_values(registers):
    """Convert devices_spec register dict → {0-based addr: uint16}."""
    init = {}
    for addr, reg in registers.items():
        raw = int(round(reg["init"] / reg["scale"]))
        init[addr] = DeviceModel._int16_to_u16(raw)
    return init


def create_server_context():
    """
    Build Modbus server context with locked 0-based datablocks.

    Returns:
        (server_context, stores, lock)
        - stores: {unit_id: {"hr": block, "ir": block}}
        - lock:   shared threading.RLock — pass to tick loop.
    """
    lock = threading.RLock()
    slaves = {}
    stores = {}

    for name, spec in DEVICES.items():
        uid = spec["unit_id"]
        hr_size = spec["hr_size"]
        ir_size = spec["ir_size"]

        # HR block
        if hr_size > 0 and spec["hr_registers"]:
            hr = LockedDataBlock(lock, hr_size,
                                 _build_init_values(spec["hr_registers"]))
        else:
            hr = RejectAllDataBlock(0, [0])

        # IR block
        if ir_size > 0 and spec["ir_registers"]:
            ir = LockedDataBlock(lock, ir_size,
                                 _build_init_values(spec["ir_registers"]))
        else:
            ir = RejectAllDataBlock(0, [0])

        ctx = ZeroBasedDeviceContext(
            di=RejectAllDataBlock(0, [0]),
            co=RejectAllDataBlock(0, [0]),
            hr=hr, ir=ir,
        )
        slaves[uid] = ctx
        stores[uid] = {"hr": hr, "ir": ir}

    return ModbusServerContext(devices=slaves, single=False), stores, lock


def create_device_identity():
    identity = ModbusDeviceIdentification()
    identity.VendorName = "Modbus Simulator"
    identity.ProductCode = "SIM"
    identity.ProductName = "Multi-Device Simulator"
    identity.ModelName = "v1.0"
    identity.MajorMinorRevision = "1.0"
    return identity
