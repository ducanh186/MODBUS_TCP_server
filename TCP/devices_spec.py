HOST = "127.0.0.1"
PORT = 15020

DEVICES = {
    "PMS": {
        "unit_id": 1,
        "hr_size": 100,
        "registers": {
            0: {"name": "demand_control_power", "access": "RW", "scale": 0.1, "unit": "kW", "init": 0.0},
            1: {"name": "total_active_power", "access": "R", "scale": 0.1, "unit": "kW", "init": 0.0},
        },
    },
    "PCS1": {
        "unit_id": 2,
        "hr_size": 100,
        "registers": {
            0: {"name": "active_power", "access": "RW", "scale": 0.1, "unit": "kW", "init": 0.0},
        },
    },
    "PCS2": {
        "unit_id": 3,
        "hr_size": 100,
        "registers": {
            0: {"name": "active_power", "access": "RW", "scale": 0.1, "unit": "kW", "init": 0.0},
        },
    },
    "BMS1": {
        "unit_id": 4,
        "hr_size": 100,
        "registers": {
            0: {"name": "soc", "access": "R", "scale": 1, "unit": "%", "init": 50},
            1: {"name": "soh", "access": "R", "scale": 1, "unit": "%", "init": 100},
            2: {"name": "capacity", "access": "R", "scale": 0.1, "unit": "kWh", "init": 100.0},
        },
    },
    "BMS2": {
        "unit_id": 5,
        "hr_size": 100,
        "registers": {
            0: {"name": "soc", "access": "R", "scale": 1, "unit": "%", "init": 50},
            1: {"name": "soh", "access": "R", "scale": 1, "unit": "%", "init": 100},
            2: {"name": "capacity", "access": "R", "scale": 0.1, "unit": "kWh", "init": 100.0},
        },
    },
}
