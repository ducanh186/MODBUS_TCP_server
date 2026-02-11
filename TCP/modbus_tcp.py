from pymodbus.datastore import ModbusDeviceContext, ModbusSequentialDataBlock, ModbusServerContext
from pymodbus import ModbusDeviceIdentification
from device import DeviceModel
from devices_spec import DEVICES

INTERNAL_OFFSET = 1


class RejectAllDataBlock(ModbusSequentialDataBlock):

    def validate(self, address, count=1):
        return False


def _build_block(size, registers):
    if size == 0 or not registers:
        return RejectAllDataBlock(0, [0])
    values = [0] * (size + INTERNAL_OFFSET)
    for addr, reg in registers.items():
        raw = int(round(reg["init"] / reg["scale"]))
        values[addr + INTERNAL_OFFSET] = DeviceModel._int16_to_u16(raw)
    return ModbusSequentialDataBlock(0, values)


def create_server_context():
    slaves = {}
    for name, spec in DEVICES.items():
        hr = _build_block(spec["hr_size"], spec["hr_registers"])
        ir = _build_block(spec["ir_size"], spec["ir_registers"])
        ctx = ModbusDeviceContext(di=None, co=None, hr=hr, ir=ir)
        slaves[spec["unit_id"]] = ctx
    return ModbusServerContext(devices=slaves, single=False)


def create_device_identity():
    identity = ModbusDeviceIdentification()
    identity.VendorName = "Modbus Simulator"
    identity.ProductCode = "SIM"
    identity.ProductName = "Multi-Device Simulator"
    identity.ModelName = "v1.0"
    identity.MajorMinorRevision = "1.0"
    return identity
