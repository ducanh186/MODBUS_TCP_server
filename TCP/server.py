import logging
from pymodbus.server import StartTcpServer

from modbus_tcp import create_server_context, create_device_identity
from device import DeviceModel

HOST = "127.0.0.1"
PORT = 15020

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")


def run_server():
    context = create_server_context()
    identity = create_device_identity()

    hr0 = context[1].getValues(3, DeviceModel.HR0_ADDRESS, 1)[0]
    hr1 = context[1].getValues(3, DeviceModel.HR1_ADDRESS, 1)[0]

    logging.info(f"Starting PMS Modbus TCP Server at {HOST}:{PORT}")
    logging.info("Device ID: 1")
    logging.info(f"HR0 (demand_control_power): {DeviceModel.decode_power_kw(hr0)} kW")
    logging.info(f"HR1 (active_power):         {DeviceModel.decode_power_kw(hr1)} kW")

    StartTcpServer(context=context, identity=identity, address=(HOST, PORT))


if __name__ == "__main__":
    run_server()
