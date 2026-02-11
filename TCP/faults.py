"""
"""

import random
import time
from typing import List


class FaultInjector:
    def __init__(self):
        self.enabled = False
        
    def inject_delay(self, min_ms: int, max_ms: int) -> None:
    
        if not self.enabled:
            return
        # TODO: implement delay injection
        pass
        
    def should_drop_response(self, drop_rate: float = 0.0) -> bool:
        """Random response dropping"""
        if not self.enabled:
            return False
        # TODO: implement response dropping
        return False
        
    def chunk_response(self, response: bytes, min_chunk: int = 1, max_chunk: int = 1) -> List[bytes]:
        """Fragment response into chunks"""
        if not self.enabled:
            return [response]
        # TODO: implement response chunking
        return [response]
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
