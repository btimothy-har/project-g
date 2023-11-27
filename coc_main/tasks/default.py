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
        self._task = None

        self.run_time = deque(maxlen=100)
    
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
    def api_semaphore(self) -> asyncio.Semaphore:
        cog = bot_client.bot.get_cog('ClashOfClansTasks')
        return cog.api_semaphore
    
    ##################################################
    ### LOOP METHODS
    ##################################################
    async def start(self):
        self._active = True
        if not self._task or self._task.done():
            self._task = asyncio.create_task(self._loop_task())
    
    async def stop(self):
        self._active = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            finally:
                self._task = None
    
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
        run_time = [r for loop in cls.loops() for r in loop.run_time if loop.loop_active]
        try:
            return min(run_time) if len(run_time) > 0 else 0
        except:
            return 0        
         
    @classmethod
    def runtime_max(cls) -> int:
        run_time = [r for loop in cls.loops() for r in loop.run_time if loop.loop_active]
        try:
            return max(run_time) if len(run_time) > 0 else 0
        except:
            return 0
           
    @classmethod
    def runtime_avg(cls) -> int:
        #combine all run_time loops and average
        run_time = [r for loop in cls.loops() for r in loop.run_time if loop.loop_active]
        try:
            return sum(run_time)/len(run_time) if len(run_time) > 0 else 0
        except:
            return 0