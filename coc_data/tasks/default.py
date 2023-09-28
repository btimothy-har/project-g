import asyncio
import math
import pendulum
import random

from collections import deque

from coc_client.api_client import BotClashClient

############################################################
############################################################
#####
##### DEFAULT TASK LOOP
#####
############################################################
############################################################
class TaskLoop():
    def __init__(self):
        self.client = BotClashClient() 

        self.task = None
        self._active = False

        self.run_time = deque(maxlen=100)
        self.api_time = deque(maxlen=100)
        
        self.api_error = False
        self.error_reports = 0
    
    def __del__(self):
        if self.task:
            self.task.cancel()
    
    async def _loop_task(self):
        pass

    ##################################################
    ### MAIN LOOP HELPERS
    ##################################################
    @property
    def bot(self):
        return self.client.bot

    @property
    def main_log(self):
        return self.client.cog.coc_main_log
    
    @property
    def data_log(self):
        return self.client.cog.coc_data_log
    
    @property
    def clash_semaphore(self):
        return self.client.cog.clash_semaphore
    
    @property
    def clash_task_lock(self):
        return self.client.cog.clash_task_lock

    @property
    def last_error_report(self):
        return self.client.cog.last_error_report
    @last_error_report.setter
    def last_error_report(self,value):
        self.client.cog.last_error_report = value
    
    @classmethod
    def client_count(cls,client_number:int):
        return len([i for i in cls._loops.values() if i.client_number == client_number])

    @classmethod
    def loops(cls):
        return list(cls._loops.values())

    @classmethod
    def keys(cls):
        return list(cls._loops.keys())

    @classmethod
    def runtime_min(cls):
        try:
            return min([i.run_time[-1] for i in cls._loops.values() if i.loop_active and len(i.run_time) > 0])
        except:
            return 0
    
    @classmethod
    def runtime_max(cls):
        try:
            return max([i.run_time[-1] for i in cls._loops.values() if i.loop_active and len(i.run_time) > 0])
        except:
            return 0    
    @classmethod
    def runtime_avg(cls):
        try:
            return sum([i.run_time[-1] for i in cls._loops.values() if i.loop_active and len(i.run_time) > 0]) / len([i for i in cls._loops.values() if i.loop_active and len(i.run_time) > 0])
        except ZeroDivisionError:
            return 0
    
    @classmethod
    def api_min(cls):
        try:
            return min([i.api_time[-1] for i in cls._loops.values() if i.loop_active and len(i.api_time) > 0])
        except:
            return 0
    
    @classmethod
    def api_max(cls):
        try:
            return max([i.api_time[-1] for i in cls._loops.values() if i.loop_active and len(i.api_time) > 0])
        except:
            return 0    
    @classmethod
    def api_avg(cls):
        try:
            return sum([i.api_time[-1] for i in cls._loops.values() if i.loop_active and len(i.api_time) > 0]) / len([i for i in cls._loops.values() if i.loop_active and len(i.api_time) > 0])
        except ZeroDivisionError:
            return 0
    
    
    
    @classmethod
    def degraded_count(cls):
        return len([i for i in cls._loops.values() if i.is_degraded])
    
    @classmethod
    def degraded_pct(cls):
        try:
            return cls.degraded_count() / len([i for i in cls._loops.values() if i.loop_active])
        except ZeroDivisionError:
            return 0
    
    @staticmethod
    def degraded_sleep_time(runtime:int):
        if runtime > 60:
            return min(math.ceil(runtime * 3),600)
        #if runtime exceeds 45 seconds, degrade sleep to x2.5
        elif runtime > 45:
            return math.ceil(runtime * 2.5)
        #if runtime exceeds 30 seconds, degrade sleep to x2
        elif runtime > 30:
            return math.ceil(runtime * 2)
        return 0

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
        if not self.last_error_report or pendulum.now().int_timestamp - self.last_error_report.int_timestamp > 600:
            self.last_error_report = pendulum.now()
            await self.bot.send_to_owners(f"{message}```{error}```")
    
    ##################################################
    ### LOOP METRICS
    ##################################################
    @property
    def loop_active(self):
        if self.client._is_initialized and self._active:
            return True
        return False
    
    @property
    def sleep_time(self):
        return 60
    
    @property
    def is_degraded(self):
        if not self.loop_active:
            return False
 
        try:
            if sum(self.run_time) / len(self.run_time) >= 40:
                return True
            if len([i for i in self.run_time if i >= 40]) / len(self.run_time) > 0.05:
                return True
        except ZeroDivisionError:
            pass
        return False