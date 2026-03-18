"""
Transducer controller — simulates grid frequency measurement.

Every 0.1s:
1. Random walk: delta = uniform(-0.05, 0.05), freq = clamp(prev + delta, 49.8, 50.2)
2. Write IR0 = frequency encoded uint16, scale 0.001 Hz (50.000 Hz → 50000)

Init frequency = 50.0 Hz.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from typing import Dict, Tuple

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tcp_servers"))

from tcp_servers.tcp_context import encode_frequency_hz

log = logging.getLogger("transducer_controller")

TRANSDUCER_IR0_FREQUENCY = 0

FREQ_MIN = 49.8
FREQ_MAX = 50.2
FREQ_INIT = 50.0
DELTA_MAX = 0.05


def _loop(
    device_name: str,
    stores: Dict[str, object],
    lock: threading.RLock,
    tick_interval_s: float,
    stop_event: threading.Event,
) -> None:
    log.info(f"{device_name} controller loop started (freq_init={FREQ_INIT} Hz, tick={tick_interval_s}s)")

    freq = FREQ_INIT

    while not stop_event.is_set():
        delta = random.uniform(-DELTA_MAX, DELTA_MAX)
        freq = max(FREQ_MIN, min(FREQ_MAX, freq + delta))

        with lock:
            stores["ir"].setValues(TRANSDUCER_IR0_FREQUENCY, [encode_frequency_hz(freq)])

        stop_event.wait(tick_interval_s)


def start_transducer_controller(
    *,
    device_name: str,
    stores: Dict[str, object],
    lock: threading.RLock,
    tick_interval_s: float = 0.1,
) -> Tuple[threading.Thread, threading.Event]:
    stop_event = threading.Event()
    t = threading.Thread(
        target=_loop,
        args=(device_name, stores, lock, tick_interval_s, stop_event),
        daemon=True,
    )
    t.start()
    return t, stop_event
