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

        self.task = None
        self.tags = []

        self.run_time = deque(maxlen=100)

        self.defer_count = 0
        self.deferred = True
    
    def __del__(self):
        if self.task:
            self.task.cancel()
    
    async def _loop_task(self):
        pass

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return asyncio.get_event_loop()

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

    ##################################################
    ### LOOP METHODS
    ##################################################
    async def start(self):
        self._active = True
        if not self.task or self.task.done():
            self.task = asyncio.create_task(self._loop_task())
            return self.task
        return None
    
    async def stop(self):
        self._active = False
        if self.task:
            task = self.task
            task.cancel()
            self.task = None
            try:
                await task
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
        if bot_client._is_initialized and self._active:
            return True
        return False
    
    @property
    def to_defer(self) -> bool:        
        if self.defer_count < 6:
            rand = random.randint(1,11000) #0.01%
            if rand % 10 == 0:
                return False
            return True
        if self.defer_count < 12:
            rand = random.randint(1,2200) #0.05%
            if rand % 10 == 0:
                return False
            return True
        if self.defer_count < 18:
            rand = random.randint(1,1100) #1%
            if rand % 10 == 0:
                return False
            return True        
        return False
    
    @classmethod
    def runtime_min(cls) -> int:
        try:
            return min([min(i.run_time) for i in cls._loops.values() if i.loop_active and len(i.run_time) > 0])
        except:
            return 0    
    @classmethod
    def runtime_max(cls) -> int:
        try:
            return max([max(i.run_time) for i in cls._loops.values() if i.loop_active and len(i.run_time) > 0])
        except:
            return 0            
    @classmethod
    def runtime_avg(cls) -> int:
        try:
            return sum([sum(i.run_time) for i in cls._loops.values() if i.loop_active and len(i.run_time) > 0]) / sum([len(i.run_time) for i in cls._loops.values() if i.loop_active and len(i.run_time) > 0])
        except ZeroDivisionError:
            return 0