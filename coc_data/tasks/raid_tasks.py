import asyncio
import coc
import pendulum
import logging

from typing import *
from redbot.core.utils import AsyncIter,bounded_gather

from .default import TaskLoop, GlobalClient

from coc_main.coc_objects.clans.clan import aClan
from coc_main.coc_objects.events.raid_weekend import aRaidWeekend

default_sleep = 60
LOG = logging.getLogger("coc.data")

############################################################
############################################################
#####
##### DEFAULT RAID TASKS
#####
############################################################
############################################################
class DefaultRaidTasks():

    @staticmethod
    async def _raid_start(clan:aClan,raid:aRaidWeekend):           
        try:
            await asyncio.sleep(120)

            new_clan = await GlobalClient.coc_client.get_clan(clan.tag)
            raid.starting_trophies = new_clan.capital_points
            await raid.save_to_database()

        except:
            LOG.exception(f"Error in New Raid task.")
    
    @staticmethod
    async def _raid_ongoing(clan:aClan,raid:aRaidWeekend):           
        try:
            if raid.do_i_save:
                await raid.save_to_database()
        except:
            LOG.exception(f"Error in New Raid task.")
    
    @staticmethod
    async def _raid_ended(clan:aClan,raid:aRaidWeekend):
        try:
            await asyncio.sleep(180)            
            new_clan = await GlobalClient.coc_client.get_clan(clan.tag)
            raid.ending_trophies = new_clan.capital_points
            await raid.save_to_database()
        except:
            LOG.exception(f"Error in Raid Ended task.")

class ClanRaidLoop(TaskLoop):
    _instance = None

    _raid_start_events = [DefaultRaidTasks._raid_start]
    _raid_ongoing_events = [DefaultRaidTasks._raid_ongoing]
    _raid_ended_events = [DefaultRaidTasks._raid_ended]
    
    @classmethod
    def add_raid_end_event(cls,event):
        if event.__name__ not in [e.__name__ for e in cls._raid_ended_events]:
            cls._raid_ended_events.append(event)
            LOG.info(f"Registered {event.__name__} {event} to Raid Ended Events.")
    
    @classmethod
    def remove_raid_end_event(cls,event):        
        if event.__name__ in [e.__name__ for e in cls._raid_ended_events]:
            event = [e for e in cls._raid_ended_events if e.__name__ == event.__name__][0]
            cls._raid_ended_events.remove(event)
            LOG.info(f"Removed {event.__name__} {event} from Raid Ended Events.")
    
    @classmethod
    def add_raid_ongoing_event(cls,event):
        if event.__name__ not in [e.__name__ for e in cls._raid_ongoing_events]:
            cls._raid_ongoing_events.append(event)
            LOG.info(f"Registered {event.__name__} {event} to Raid Ongoing Events.")
    
    @classmethod
    def remove_raid_ongoing_event(cls,event):        
        if event.__name__ in [e.__name__ for e in cls._raid_ongoing_events]:
            event = [e for e in cls._raid_ongoing_events if e.__name__ == event.__name__][0]
            cls._raid_ongoing_events.remove(event)
            LOG.info(f"Removed {event.__name__} {event} from Raid Ongoing Events.")

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._is_new = True
        return cls._instance

    def __init__(self):        
        if self._is_new:
            super().__init__()
            self._is_new = False            
    
    async def start(self):
        LOG.info(f"Raid Loop started.")
        await super().start()
    
    async def stop(self):
        try:
            LOG.info(f"Raid Loop stopped.")
        except:
            pass
        await super().stop()
    
    ##################################################
    ### PRIMARY TASK LOOP
    ##################################################
    async def _loop_task(self):
        try:
            while self.loop_active:
                if self.api_maintenance:
                    await asyncio.sleep(10)
                    continue

                c_tags = list(self._tags)
                if len(c_tags) <= 0:
                    await asyncio.sleep(10)
                    continue

                st = pendulum.now()
                self._running = True
                a_iter = AsyncIter(c_tags)

                tasks = [self._run_single_loop(tag) async for tag in a_iter]
                await bounded_gather(*tasks,semaphore=self._loop_semaphore)

                self.last_loop = et = pendulum.now()
                self._running = False
                try:
                    runtime = et - st
                    self.run_time.append(runtime.total_seconds())
                except:
                    pass

                await asyncio.sleep(10)
                continue

        except Exception as exc:
            if self.loop_active:
                await TaskLoop.report_fatal_error(
                    message="FATAL RAID LOOP ERROR",
                    error=exc,
                    )
                await self.start()
    ############################################################
    #####
    ##### SINGLE LOOP
    #####
    ############################################################    
    async def _run_single_loop(self,tag:str):
        try:
            lock = self._locks[tag]
            if lock.locked():
                return
            await lock.acquire()
            cached = self._cached.get(tag,None)
        
            clan = await self.coc_client.get_clan(tag)    
            
            raid_log = None
            new_raid = None            
            
            raid_log = await self.coc_client.get_raid_log(clan_tag=tag,limit=1)
            wait = getattr(raid_log,'_response_retry',default_sleep)
            self.loop.call_later(wait,self.unlock,lock)
                
            if raid_log and len(raid_log) > 0:
                new_raid = raid_log[0]
                self._cached[tag] = new_raid
            
            if cached and new_raid:
                await self._dispatch_events(clan,cached,new_raid)
        
        except (coc.NotFound,coc.Maintenance):
            return self.loop.call_later(3600,self.unlock,lock)
        except coc.PrivateWarLog:
            return self.loop.call_later(60,self.unlock,lock)        
        except asyncio.CancelledError:
            return
        
        except Exception as exc:
            if self.loop_active:
                await TaskLoop.report_fatal_error(
                    message=f"FATAL CAPITAL RAID LOOP ERROR: {tag}",
                    error=exc,
                    )
            return self.unlock(lock)
    
    async def _dispatch_events(self,clan:aClan,cached_raid:coc.RaidLogEntry,new_raid:coc.RaidLogEntry):        
        try:
            current_raid = await aRaidWeekend.create_from_api(clan,new_raid)
        except:
            return
        tasks = []

        #New Raid Started
        if new_raid.start_time != cached_raid.start_time:
            a_iter = AsyncIter(ClanRaidLoop._raid_start_events)
            tasks.extend([event(clan,current_raid) async for event in a_iter])

        #Raid Ended
        elif new_raid.state in ['ended'] and getattr(cached_raid,'state',None) == 'ongoing':
            a_iter = AsyncIter(ClanRaidLoop._raid_ended_events)
            tasks.extend([event(clan,current_raid) async for event in a_iter])
        
        #Ongoing Raid
        elif new_raid.state == 'ongoing' and getattr(cached_raid,'state',None) == 'ongoing':
            a_iter = AsyncIter(ClanRaidLoop._raid_ongoing_events)
            tasks.extend([event(clan,current_raid) async for event in a_iter])
        
        lock = self._locks['dispatch']
        async with lock:
            sem = self._task_semaphore
            while True:
                if not sem._waiters: 
                    break
                if sem._waiters and len(sem._waiters) < len(tasks):
                    break
                await asyncio.sleep(0.1)
        await bounded_gather(*tasks,semaphore=sem)