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
        self._status = "Not Running"
        self._last_loop = None
        self._tags = set()

        self.run_time = deque(maxlen=1000)
    
    def add_to_loop(self,tag:str):
        n_tag = coc.utils.correct_tag(tag)        
        if n_tag not in self._tags:
            self._tags.add(n_tag)
            return True, n_tag
        return False, n_tag
    
    def remove_to_loop(self,tag:str):
        n_tag = coc.utils.correct_tag(tag)
        if n_tag in self._tags:
            self._tags.discard(n_tag)
            return True, n_tag
        return False, n_tag
    
    async def _loop_task(self):
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
        await self._loop_task()
    
    async def stop(self):
        self._active = False
    
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
    
    @property
    def runtime_min(self) -> int:
        try:
            return min(self.run_time) if self.loop_active and len(self.run_time) > 0 else 0
        except:
            return 0    
    @property
    def runtime_max(self) -> int:
        try:
            return max(self.run_time) if self.loop_active and len(self.run_time) > 0 else 0
        except:
            return 0                
    @property
    def runtime_avg(self) -> int:
        try:
            return sum(self.run_time)/len(self.run_time) if self.loop_active and len(self.run_time) > 0 else 0
        except:
            return 0