import coc
import asyncio

from aiolimiter import AsyncLimiter
from collections import deque
from time import process_time

############################################################
############################################################
#####
##### THROTTLER / COUNTER
#####
############################################################
############################################################
class CounterThrottler(coc.BasicThrottler):
    def __init__(self,sleep_time):
        self.limiter = AsyncLimiter(1,sleep_time)
        self.sent_lock = asyncio.Lock()
        self.sent_time = process_time()
        self.current_sent = 0
        self.sent = deque(maxlen=3600)

        self.rcvd_lock = asyncio.Lock()
        self.rcvd_time = process_time()
        self.current_rcvd = 0
        self.rcvd = deque(maxlen=3600)

        super().__init__(sleep_time)
    
    async def __aenter__(self):
        await self.limiter.acquire()
        await self.increment_sent()
        return self
    
    async def __aexit__(self, exc_type, exc, tb):
        await self.increment_rcvd()
        return self
    
    async def reset_counter(self):
        async with self.sent_lock, self.rcvd_lock:
            self.sent = deque(maxlen=3600)
            self.sent_time = process_time()
            self.rcvd = deque(maxlen=3600)
            self.rcvd_time = process_time()
    
    async def increment_sent(self):
        async with self.sent_lock:
            self.current_sent += 1
    
    async def increment_rcvd(self):
        async with self.rcvd_lock:
            self.current_rcvd += 1