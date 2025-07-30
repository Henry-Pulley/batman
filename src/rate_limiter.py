import asyncio
import time
from collections import deque
from .config import config

class TokenBucketRateLimiter:
    """Token bucket rate limiter for better burst handling"""

    def __init__(self, rate=10, capacity=50):
        self.rate = rate  # tokens per second
        self.capacity = capacity  # max tokens
        self.tokens = capacity
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens=1):
        """Acquire tokens, waiting if necessary"""
        async with self._lock:
            while self.tokens < tokens:
                now = time.time()
                elapsed = now - self.last_update
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                self.last_update = now

                if self.tokens < tokens:
                    sleep_time = (tokens - self.tokens) / self.rate
                    await asyncio.sleep(sleep_time)

            self.tokens -= tokens

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass