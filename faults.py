"""
FaultInjector: mô phỏng "mạng xấu" (network simulation) ở mức đơn giản.

Bật dần:
- delay_ms_min/max: thêm độ trễ phản hồi (latency/jitter)
- chunk_min/max: cắt response thành nhiều mẩu (giống fragmentation)
- drop_rate: rớt response
- close_rate: đóng kết nối ngẫu nhiên
"""

import random
import time
from typing import List


class FaultInjector:
    def __init__(
        self,
        delay_ms_min: int = 0,
        delay_ms_max: int = 0,
        chunk_min: int = 1,
        chunk_max: int = 1,
        drop_rate: float = 0.0,
        close_rate: float = 0.0,
    ):
        self.delay_ms_min = delay_ms_min
        self.delay_ms_max = delay_ms_max
        self.chunk_min = chunk_min
        self.chunk_max = chunk_max
        self.drop_rate = drop_rate
        self.close_rate = close_rate

    def maybe_sleep(self) -> None:
        if self.delay_ms_max <= 0:
            return
        ms = random.randint(self.delay_ms_min, self.delay_ms_max)
        time.sleep(ms / 1000.0)

    def should_drop(self) -> bool:
        return random.random() < self.drop_rate

    def should_close(self) -> bool:
        return random.random() < self.close_rate

    def chunk_bytes(self, data: bytes) -> List[bytes]:
        if self.chunk_max <= 1:
            return [data]
        n = random.randint(self.chunk_min, self.chunk_max)
        if n <= 1 or len(data) <= 1:
            return [data]

        chunks = []
        start = 0
        for i in range(n - 1):
            remaining = len(data) - start
            cut = random.randint(1, max(1, remaining - (n - i - 1)))
            chunks.append(data[start : start + cut])
            start += cut
        chunks.append(data[start:])
        return [c for c in chunks if c]
