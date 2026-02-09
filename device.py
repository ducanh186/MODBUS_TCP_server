"""
DeviceModel: mô phỏng "thiết bị thật" ở mức tối thiểu.

- Holding Registers (thanh ghi giữ) là 16-bit, read/write.
- Address dùng 0-based: 0..holding_size-1.
"""

import threading
import time
from typing import List


class DeviceModel:
    def __init__(self, holding_size: int = 100):
        self._lock = threading.Lock()
        self.holding = [0] * holding_size

        self._bg_thread = None
        self._stop = threading.Event()

    def read_holding(self, address: int, count: int) -> List[int]:
        with self._lock:
            self._check_range(address, count)
            return self.holding[address : address + count]

    def write_single(self, address: int, value: int) -> None:
        with self._lock:
            self._check_range(address, 1)
            self.holding[address] = value & 0xFFFF

    def _check_range(self, address: int, count: int) -> None:
        if address < 0 or count <= 0:
            raise ValueError("invalid address/count")
        if address + count > len(self.holding):
            raise ValueError("illegal address")

    def start_background_updates(self) -> None:
        if self._bg_thread is not None:
            return
        self._bg_thread = threading.Thread(target=self._bg_loop, daemon=True)
        self._bg_thread.start()

    def _bg_loop(self) -> None:
        # Ví dụ: register 1 tăng mỗi giây để thấy "device sống"
        while not self._stop.is_set():
            with self._lock:
                if len(self.holding) > 1:
                    self.holding[1] = (self.holding[1] + 1) & 0xFFFF
            time.sleep(1.0)

    def stop(self) -> None:
        self._stop.set()
