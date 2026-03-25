"""Quick smoke test for MultiRangeDataBlock + register_codec."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tcp_servers"))

from tcp_servers.tcp_context import MultiRangeDataBlock
from tcp_servers.register_codec import encode, decode
from pymodbus.datastore.store import ExcCodes
import threading

lock = threading.RLock()
block = MultiRangeDataBlock(lock, [(30000, 85), (32000, 91)])

# Write identity data
block.setValues(30000, encode("STR", "LUNA2000-213KTL-H0", quantity=15))
block.setValues(30070, encode("U16", 586))
block.setValues(30073, encode("U32", 2000.0, gain=1000))

# Mega-read: 85 regs from 30000
raw = block.getValues(30000, 85)
assert len(raw) == 85

model = decode("STR", raw[0:15])
assert model == "LUNA2000-213KTL-H0", f"Got: {model}"

model_id = decode("U16", [raw[70]])
assert model_id == 586, f"Got: {model_id}"

assert raw[71] == 0 and raw[72] == 0, "Gap should be 0"

rated_power = decode("U32", raw[73:75], gain=1000)
assert rated_power == 2000.0, f"Got: {rated_power}"

print(f"model={model}, id={model_id}, gap71={raw[71]}, rated_kw={rated_power}")

# ILLEGAL_ADDRESS: out of range 1
assert block.getValues(30080, 10) == ExcCodes.ILLEGAL_ADDRESS
# ILLEGAL_ADDRESS: outside any range
assert block.getValues(40000, 1) == ExcCodes.ILLEGAL_ADDRESS

# Range 2: power block
block.setValues(32080, encode("I32", -500.0, gain=1000))
power = decode("I32", block.getValues(32080, 2), gain=1000)
assert power == -500.0, f"Got: {power}"
print(f"active_power={power} kW")

# Write at invalid address
assert block.setValues(40000, [123]) == ExcCodes.ILLEGAL_ADDRESS

print("ALL TESTS PASSED")
