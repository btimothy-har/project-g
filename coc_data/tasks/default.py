import asyncio
import pendulum
import coc
import copy

from typing import *
from collections import deque, defaultdict

from coc_main.api_client import BotClashClient as client
from coc_main.api_client import clash_event_error
from coc_main.cog_coc_client import ClashOfClansClient

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
        await clash_event_error(error)

    def __init__(self):
        self._active = False
        self._running = False
        self._tags = set()

        self._last_db_update = pendulum.now().subtract(minutes=30)
        
        self._loop_semaphore = asyncio.Semaphore(100)
        self._task_semaphore = asyncio.Semaphore(10)

        self._cached = {}
        self._locks = defaultdict(asyncio.Lock)
        
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
    
    ##################################################
    ### LOOP METHODS
    ##################################################
    async def start(self):
        self._active = True
        await self._loop_task()
    
    async def stop(self):
        self._active = False
    
    def add_to_loop(self,*tags:str):
        for tag in tags:
            if not isinstance(tag, str):
                raise TypeError("clan tag must be of type str not {0!r}".format(tag))
            self._tags.add(coc.utils.correct_tag(tag))

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