import logging
import asyncio
import math
import pendulum

from typing import *

from collections import deque
from ..api_client import BotClashClient as client
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

    @classmethod
    def loops(cls) -> List['TaskLoop']:
        return list(cls._loops.values())

    @classmethod
    def keys(cls) -> List[str]:
        return list(cls._loops.keys())
    
    def __init__(self):
        self.task = None
        self._active = False

        self.run_time = deque(maxlen=100)
        
        self.api_error = False
        self.error_reports = 0
    
    def __del__(self):
        if self.task:
            self.task.cancel()
    
    async def _loop_task(self):
        pass

    @property
    def coc_client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog('ClashOfClansClient')

    ##################################################
    ### MAIN LOOP HELPERS
    ##################################################
    @property
    def main_log(self) -> logging.Logger:
        return bot_client.coc_main_log
    
    @property
    def data_log(self) -> logging.Logger:
        return bot_client.coc_data_log
    
    @property
    def task_semaphore(self) -> asyncio.Semaphore:
        cog = bot_client.bot.get_cog('ClashOfClansTasks')
        return cog.task_semaphore
    
    @property
    def task_lock(self) -> asyncio.Lock:
        cog = bot_client.bot.get_cog('ClashOfClansTasks')
        return cog.task_lock
    
    @property
    def api_semaphore(self) -> asyncio.Semaphore:
        cog = bot_client.bot.get_cog('ClashOfClansTasks')
        return cog.api_semaphore

    @property
    def last_error_report(self) -> Optional[pendulum.DateTime]:
        cog = bot_client.bot.get_cog('ClashOfClansTasks')
        return cog.last_coc_task_error
    @last_error_report.setter
    def last_error_report(self,value:pendulum.DateTime):
        cog = bot_client.bot.get_cog('ClashOfClansTasks')
        cog.last_coc_task_error = value

    ##################################################
    ### LOOP METHODS
    ##################################################
    async def start(self):
        self._active = True
        if not self.task or self.task.done():
            self.task = asyncio.create_task(self._loop_task())
    
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
    
    async def report_fatal_error(self,message,error):
        if not self.last_error_report or pendulum.now().int_timestamp - self.last_error_report.int_timestamp > 60:
            self.last_error_report = pendulum.now()
            await bot_client.bot.send_to_owners(f"{message}```{error}```")
    
    ##################################################
    ### LOOP METRICS
    ##################################################
    @property
    def loop_active(self) -> bool:
        if bot_client._is_initialized and self._active:
            return True
        return False
    
    @property
    def sleep_time(self) -> int:
        return 60
    
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