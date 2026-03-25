"""E2E test: MultiRangeDataBlock served over real Modbus TCP, read by client."""
import sys, os, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tcp_servers"))

from tcp_servers.tcp_context import build_multirange_server_context, ZeroBasedDeviceContext
from tcp_servers.register_codec import encode, decode
from pymodbus.server import StartTcpServer
from pymodbus.client import ModbusTcpClient

HOST, PORT = "127.0.0.1", 15099

# -- Build server with Huawei-style addresses --
server_ctx, stores, lock = build_multirange_server_context(
    hr_ranges=[(40039, 163)],                     # control block
    ir_ranges=[(30000, 85), (32000, 91)],         # identity+rating, status+power
    slave_id=1,
)

# Pre-populate registers (server-side encoding)
stores["ir"].setValues(30000, encode("STR", "LUNA2000-213KTL-H0", quantity=15))
stores["ir"].setValues(30070, encode("U16", 586))
stores["ir"].setValues(30073, encode("U32", 2000.0, gain=1000))
stores["ir"].setValues(30075, encode("U32", 2100.0, gain=1000))
stores["ir"].setValues(30077, encode("U32", 2200.0, gain=1000))
stores["ir"].setValues(30079, encode("I32", -1500.0, gain=1000))
stores["ir"].setValues(30081, encode("I32", 1500.0, gain=1000))
stores["ir"].setValues(30083, encode("U32", 2000.0, gain=1000))
stores["ir"].setValues(32080, encode("I32", -350.5, gain=1000))
stores["ir"].setValues(32085, encode("U16", 50.1, gain=10))

# Start server in background thread
srv_thread = threading.Thread(
    target=lambda: StartTcpServer(server_ctx, address=(HOST, PORT)),
    daemon=True,
)
srv_thread.start()
time.sleep(0.5)

# -- Client reads --
client = ModbusTcpClient(HOST, port=PORT)
assert client.connect(), "Cannot connect"

print("=== Mega-read: 85 input registers from 30000 ===")
rr = client.read_input_registers(30000, count=85, device_id=1)
assert not rr.isError(), f"Read failed: {rr}"
raw = rr.registers

model = decode("STR", raw[0:15])
model_id = decode("U16", [raw[70]])
rated_kw = decode("U32", raw[73:75], gain=1000)
pmax = decode("U32", raw[75:77], gain=1000)
smax = decode("U32", raw[77:79], gain=1000)
qmax_feed = decode("I32", raw[79:81], gain=1000)
qmax_supply = decode("I32", raw[81:83], gain=1000)
pmax_real = decode("U32", raw[83:85], gain=1000)

print(f"  model       = {model}")
print(f"  model_id    = {model_id}")
print(f"  rated_power = {rated_kw} kW")
print(f"  pmax        = {pmax} kW")
print(f"  smax        = {smax} kVA")
print(f"  qmax_feed   = {qmax_feed} kVar")
print(f"  qmax_supply = {qmax_supply} kVar")
print(f"  pmax_real   = {pmax_real} kW")

assert model == "LUNA2000-213KTL-H0"
assert model_id == 586
assert rated_kw == 2000.0
assert qmax_feed == -1500.0

print("\n=== Read power block from 32000 (27 regs for 32064-32090 area) ===")
rr2 = client.read_input_registers(32080, count=2, device_id=1)
assert not rr2.isError()
active_power = decode("I32", rr2.registers, gain=1000)
print(f"  active_power (32080) = {active_power} kW")
assert active_power == -350.5

rr3 = client.read_input_registers(32085, count=1, device_id=1)
grid_freq = decode("U16", rr3.registers, gain=10)
print(f"  grid_freq (32085) = {grid_freq} Hz")
assert grid_freq == 50.1

print("\n=== ILLEGAL ADDRESS test ===")
rr_bad = client.read_input_registers(31000, count=1, device_id=1)
print(f"  read 31000 (no range) → isError={rr_bad.isError()}")
assert rr_bad.isError()

print("\n=== Write HR (control command at 40043) ===")
setpoint_regs = encode("I32", -800.0, gain=1000)
wr = client.write_registers(40043, setpoint_regs, device_id=1)
assert not wr.isError(), f"Write failed: {wr}"
# Read back
rr4 = client.read_holding_registers(40043, count=2, device_id=1)
setpoint_back = decode("I32", rr4.registers, gain=1000)
print(f"  wrote -800.0 kW at HR 40043, read back = {setpoint_back} kW")
assert setpoint_back == -800.0

client.close()
print("\nALL E2E TESTS PASSED")
