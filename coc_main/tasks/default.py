import coc
import asyncio
import math
import pendulum
import random

from typing import *

from collections import deque
from ..api_client import BotClashClient as client
from ..exceptions import InvalidTag, ClashAPIError
from ..cog_coc_client import ClashOfClansClient

bot_client = client()

############################################################
############################################################
#####
##### DEFAULT TASK LOOP
#####
############################################################
############################################################
class TaskLoop():
    
    @staticmethod
    async def report_fatal_error(message,error):
        cog = bot_client.bot.get_cog('ClashOfClansTasks')
        await cog.report_error(message,error)
    
    @classmethod
    def loops(cls) -> List['TaskLoop']:
        return list(cls._loops.values())

    @classmethod
    def keys(cls) -> List[str]:
        return list(cls._loops.keys())

    def __init__(self):
        self._active = False
        self._running = False
        self._collector = None
        self._last_loop = None
        self._queue = asyncio.Queue()

        self.run_time = deque(maxlen=100)
    
    async def _loop_task(self):
        pass

    async def _collector_task(self):
        pass

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return asyncio.get_event_loop()
    
    @property
    def last_loop(self) -> pendulum.DateTime:
        if self._last_loop:
            return self._last_loop
        return pendulum.now()

    @property
    def coc_client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog('ClashOfClansClient')
 
    @property
    def api_maintenance(self) -> bool:
        return self.coc_client.api_maintenance
    
    @property
    def task_lock(self) -> asyncio.Lock:
        cog = bot_client.bot.get_cog('ClashOfClansTasks')
        return cog.task_lock
    
    @property
    def task_semaphore(self) -> asyncio.Semaphore:
        cog = bot_client.bot.get_cog('ClashOfClansTasks')
        return cog.task_semaphore
    
    @property
    def api_semaphore(self) -> asyncio.Semaphore:
        cog = bot_client.bot.get_cog('ClashOfClansTasks')
        return cog.api_semaphore
    
    ##################################################
    ### LOOP METHODS
    ##################################################
    async def start(self):
        self._active = True
        self._collector = asyncio.create_task(self._collector_task())
        await self._loop_task()
    
    async def stop(self):
        self._active = False        
        try:
            self._collector.cancel()
            await self._collector
        except:
            pass
    
    def unlock(self,lock:asyncio.Lock):
        try:
            lock.release()
        except:
            pass

    ##################################################
    ### LOOP METRICS
    ##################################################
    @property
    def loop_active(self) -> bool:
        try:
            if bot_client._is_initialized and self._active:
                return True
            return False
        except:
            return False
    
    @classmethod
    def runtime_min(cls) -> int:
        loop = cls()
        try:
            return min(loop.run_time) if loop.loop_active and len(loop.run_time) > 0 else 0
        except:
            return 0    
    @classmethod
    def runtime_max(cls) -> int:
        loop = cls()
        try:
            return max(loop.run_time) if loop.loop_active and len(loop.run_time) > 0 else 0
        except:
            return 0                
    @classmethod
    def runtime_avg(cls) -> int:
        loop = cls()
        try:
            return sum(loop.run_time)/len(loop.run_time) if loop.loop_active and len(loop.run_time) > 0 else 0
        except:
            return 0