"""Simple rate limiting utilities"""

import asyncio
import time
from .config import config

class SimpleRateLimiter:
    def __init__(self, delay=config.request_delay):
        self.delay = delay
        self.last_request_time = 0

    async def __aenter__(self):
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.delay:
            await asyncio.sleep(self.delay - time_since_last)

        self.last_request_time = time.time()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass