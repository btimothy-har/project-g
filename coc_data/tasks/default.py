import asyncio
import pendulum
import coc
import copy
import logging

from typing import *
from collections import deque, defaultdict

from coc_main.client.global_client import GlobalClient

LOG = logging.getLogger("coc.data")

############################################################
############################################################
#####
##### DEFAULT TASK LOOP
#####
############################################################
############################################################
class TaskLoop(GlobalClient):
    
    @staticmethod
    async def report_fatal_error(message,error):
        LOG.exception(f"{message}: {error}",exc_info=error)

    def __init__(self):
        self._active = False
        self._running = False
        self._tags = set()

        self._last_refresh = pendulum.now().subtract(minutes=30)
        
        self._loop_semaphore = asyncio.Semaphore(100)
        self._task_semaphore = asyncio.Semaphore(10)

        self._cached = {}
        self._locks = defaultdict(asyncio.Lock)

        self.last_loop = pendulum.now()
        self.run_time = deque(maxlen=1000)
        
    async def _loop_task(self):
        pass

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return asyncio.get_event_loop()
    @property
    def api_maintenance(self) -> bool:
        return self.coc_client.maintenance
    
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
            if self._ready and self._active:
                return True
            return False
        except:
            return False