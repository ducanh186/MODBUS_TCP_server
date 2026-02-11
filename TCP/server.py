import logging
from pymodbus.server import StartTcpServer
from modbus_tcp import create_server_context, create_device_identity
from devices_spec import HOST, PORT, DEVICES

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")


def run_server():
    context = create_server_context()
    identity = create_device_identity()

    device_list = ", ".join(f"{name}(uid={spec['unit_id']})" for name, spec in DEVICES.items())
    logging.info(f"Starting Modbus TCP Server on {HOST}:{PORT}")
    logging.info(f"Devices: {device_list}")

    StartTcpServer(context, identity=identity, address=(HOST, PORT))


if __name__ == "__main__":
    run_server()
