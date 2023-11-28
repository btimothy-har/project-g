import coc
import asyncio
import math
import pendulum
import random
import copy

from typing import *
from aiolimiter import AsyncLimiter

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
        self._tags = set()
        
        self._db_tags = set()
        self._last_db_update = pendulum.now().subtract(minutes=30)
        
        self.last_loop = pendulum.now()
        self.dispatch_time = deque(maxlen=1000)
        self.run_time = deque(maxlen=1000)
    
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
    
    @property
    def task_limiter(self) -> AsyncLimiter:
        cog = bot_client.bot.get_cog('ClashOfClansTasks')
        return cog.task_limiter
    
    @property
    def api_limiter(self) -> AsyncLimiter:
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
    def runtime_avg(self) -> int:
        runtime = copy.copy(self.run_time)
        try:
            return sum(runtime)/len(runtime) if len(runtime) > 0 else 0
        except:
            return 0
    
    @property
    def dispatch_avg(self) -> int:
        runtime = copy.copy(self.dispatch_time)
        try:
            return sum(runtime)/len(runtime) if len(runtime) > 0 else 0
        except:
            return 0