HOST = "127.0.0.1"
PORT = 15020

DEVICES = {
    "PMS": {
        "device_type": "PMS",
        "unit_id": 1,
        "hr_size": 10,
        "ir_size": 10,
        "hr_registers": {
            0: {"name": "demand_control_power", "scale": 0.1, "unit": "kW", "init": 0.0},
        },
        "ir_registers": {
            0: {"name": "total_active_power", "scale": 0.1, "unit": "kW", "init": 0.0},
            1: {"name": "soc_avg", "scale": 1, "unit": "%", "init": 0},
            2: {"name": "soh_avg", "scale": 1, "unit": "%", "init": 0},
            3: {"name": "capacity_total", "scale": 0.1, "unit": "kWh", "init": 0.0},
        },
    },
    "PCS1": {
        "device_type": "PCS",
        "unit_id": 2,
        "hr_size": 0,
        "ir_size": 10,
        "hr_registers": {},
        "ir_registers": {
            0: {"name": "active_power", "scale": 0.1, "unit": "kW", "init": 0.0},
        },
    },
    "PCS2": {
        "device_type": "PCS",
        "unit_id": 3,
        "hr_size": 0,
        "ir_size": 10,
        "hr_registers": {},
        "ir_registers": {
            0: {"name": "active_power", "scale": 0.1, "unit": "kW", "init": 0.0},
        },
    },
    "BMS1": {
        "device_type": "BMS",
        "unit_id": 4,
        "hr_size": 0,
        "ir_size": 10,
        "hr_registers": {},
        "ir_registers": {
            0: {"name": "soc", "scale": 1, "unit": "%", "init": 50},
            1: {"name": "soh", "scale": 1, "unit": "%", "init": 100},
            2: {"name": "capacity", "scale": 0.1, "unit": "kWh", "init": 100.0},
        },
    },
    "BMS2": {
        "device_type": "BMS",
        "unit_id": 5,
        "hr_size": 0,
        "ir_size": 10,
        "hr_registers": {},
        "ir_registers": {
            0: {"name": "soc", "scale": 1, "unit": "%", "init": 50},
            1: {"name": "soh", "scale": 1, "unit": "%", "init": 100},
            2: {"name": "capacity", "scale": 0.1, "unit": "kWh", "init": 100.0},
        },
    },
}

# PCS <-> BMS pairing (by unit_id)
PCS_TO_BMS = {
    2: 4,   # PCS1 (uid=2) <-> BMS1 (uid=4)
    3: 5,   # PCS2 (uid=3) <-> BMS2 (uid=5)
}
