from pymodbus.datastore import ModbusDeviceContext, ModbusSequentialDataBlock, ModbusServerContext
from pymodbus import ModbusDeviceIdentification
from device import DeviceModel


def create_pms_datastore():
    """Create datastore for PMS with initial values"""
    holding_registers = ModbusSequentialDataBlock(0, [0] * 100)

    holding_registers.setValues(DeviceModel.HR0_ADDRESS, [DeviceModel.encode_power_kw(0.0)])
    holding_registers.setValues(DeviceModel.HR1_ADDRESS, [DeviceModel.encode_power_kw(0.0)])

    return holding_registers


def create_slave_context():
    holding_registers = create_pms_datastore()
    device_context = ModbusDeviceContext(
        di=None,
        co=None,
        hr=holding_registers,
        ir=None
    )
    return device_context


def create_server_context():
    device_context = create_slave_context()
    server_context = ModbusServerContext(devices={1: device_context}, single=False)
    return server_context


def create_device_identity():
    identity = ModbusDeviceIdentification()
    identity.VendorName = "PMS Simulator"
    identity.ProductCode = "PMS"
    identity.ProductName = "Power Management System"
    identity.ModelName = "PMS v1.0"
    identity.MajorMinorRevision = "1.0"
    return identity
