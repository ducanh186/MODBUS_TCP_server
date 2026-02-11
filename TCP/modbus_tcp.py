from pymodbus.datastore import ModbusDeviceContext, ModbusSequentialDataBlock, ModbusServerContext
from pymodbus import ModbusDeviceIdentification
from device import DeviceModel
from devices_spec import DEVICES

INTERNAL_OFFSET = 1


class ZeroBasedDataBlock(ModbusSequentialDataBlock):

    def validate(self, address, count=1):
        return super().validate(address + INTERNAL_OFFSET, count)

    def getValues(self, address, count=1):
        return super().getValues(address + INTERNAL_OFFSET, count)

    def setValues(self, address, values):
        return super().setValues(address + INTERNAL_OFFSET, values)


def create_device_datastore(device_spec):
    hr_values = [0] * (device_spec["hr_size"] + INTERNAL_OFFSET)
    for addr, reg in device_spec["registers"].items():
        raw = int(round(reg["init"] / reg["scale"]))
        hr_values[addr + INTERNAL_OFFSET] = DeviceModel._int16_to_u16(raw)
    return ZeroBasedDataBlock(0, hr_values)


def create_server_context():
    slaves = {}
    for name, spec in DEVICES.items():
        hr = create_device_datastore(spec)
        ctx = ModbusDeviceContext(di=None, co=None, hr=hr, ir=None)
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
