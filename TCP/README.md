# MODBUS_TCP_server/TCP

Primary simulator entrypoint:

- `python plant.py --config config/plant.yaml`

Deprecated entrypoint:

- `python server.py` (single-process legacy path)

Notes:

- `plant.py` is the maintained multi-process architecture for demo and ongoing development.
- Legacy files (`server.py`, `devices_spec.py`, `modbus_tcp.py`, `tick.py`) are kept for reference only.
