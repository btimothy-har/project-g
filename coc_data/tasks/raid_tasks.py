import asyncio
import coc
import copy
import pendulum

from typing import *
from redbot.core.utils import AsyncIter,bounded_gather
from .default import TaskLoop

from coc_main.api_client import BotClashClient as client
from coc_main.cog_coc_client import ClashOfClansClient
from coc_main.exceptions import InvalidTag, ClashAPIError

from coc_main.coc_objects.clans.clan import aClan
from coc_main.coc_objects.events.raid_weekend import aRaidWeekend
from coc_main.discord.feeds.reminders import EventReminder
from coc_main.discord.feeds.raid_results import RaidResultsFeed

bot_client = client()
default_sleep = 60

############################################################
############################################################
#####
##### DEFAULT RAID TASKS
#####
############################################################
############################################################
class DefaultRaidTasks():

    @staticmethod
    def _get_client() -> ClashOfClansClient:
        return bot_client.bot.get_cog('ClashOfClansClient')     

    @staticmethod
    async def _raid_start(clan:aClan,raid:aRaidWeekend):           
        try:
            await asyncio.sleep(120)
            coc_client = DefaultRaidTasks._get_client()

            new_clan = await coc_client.fetch_clan(clan.tag)
            raid.starting_trophies = new_clan.capital_points
            await raid.save_to_database()

        except:
            bot_client.coc_main_log.exception(f"Error in New Raid task.")
    
    @staticmethod
    async def _raid_ended(clan:aClan,raid:aRaidWeekend):
        try:
            await asyncio.sleep(120)
            coc_client = DefaultRaidTasks._get_client()
            
            new_clan = await coc_client.fetch_clan(tag=clan.tag)
            raid.ending_trophies = new_clan.capital_points
            await raid.save_to_database()

            if raid.attack_count > 0:
                await RaidResultsFeed.start_feed(new_clan,raid)

        except:
            bot_client.coc_main_log.exception(f"Error in Raid Ended task.")

class ClanRaidLoop(TaskLoop):
    _instance = None

    _raid_start_events = [DefaultRaidTasks._raid_start]
    _raid_ended_events = [DefaultRaidTasks._raid_ended]
    
    @classmethod
    async def _setup_raid_reminder(cls,clan:aClan,current_raid:aRaidWeekend,reminder:EventReminder):        
        remind_members = [m for m in current_raid.members if m.attack_count < 6]
        await reminder.send_reminder(current_raid,*remind_members)
    
    @classmethod
    def add_raid_end_event(cls,event):
        if event.__name__ not in [e.__name__ for e in cls._raid_ended_events]:
            cls._raid_ended_events.append(event)
            bot_client.coc_main_log.info(f"Registered {event.__name__} {event} to Raid Ended Events.")
    
    @classmethod
    def remove_raid_end_event(cls,event):        
        if event.__name__ in [e.__name__ for e in cls._raid_ended_events]:
            event = [e for e in cls._raid_ended_events if e.__name__ == event.__name__][0]
            cls._raid_ended_events.remove(event)
            bot_client.coc_main_log.info(f"Removed {event.__name__} {event} from Raid Ended Events.")

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
        bot_client.coc_main_log.info(f"Raid Loop started.")
        await super().start()
    
    async def stop(self):
        try:
            bot_client.coc_main_log.info(f"Raid Loop stopped.")
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

                c_tags = copy.copy(bot_client.coc._clan_updates)
                tags = list(c_tags)

                if len(tags) <= 0:
                    await asyncio.sleep(10)
                    continue

                st = pendulum.now()
                self._running = True
                a_iter = AsyncIter(tags)

                tasks = [self._run_single_loop(tag) async for tag in a_iter]
                await bounded_gather(*tasks,semaphore=self._loop_semaphore)

                et = pendulum.now()
                bot_client.last_loop['raid'] = et
                self._running = False
                try:
                    runtime = et - st
                    bot_client.raid_loop_runtime.append(runtime.total_seconds())
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
    
    async def _run_single_loop(self,tag:str):
        try:
            lock = self._locks[tag]
            if lock.locked():
                return
            await lock.acquire()
            cached = self._cached.get(tag,None)
            
            try:
                clan = await self.coc_client.fetch_clan(tag)
            except InvalidTag:
                return self.loop.call_later(3600,self.unlock,lock)
            except ClashAPIError:
                return self.loop.call_later(10,self.unlock,lock)
            
            raid_log = None
            new_raid = None
            count = 0
            
            while True:
                try:
                    count += 1
                    raid_log = await bot_client.coc.get_raid_log(clan_tag=tag,limit=1)
                    break
                except (coc.NotFound,coc.PrivateWarLog,coc.Maintenance,coc.GatewayError):
                    return self.loop.call_later(10,self.unlock,lock)
                except:
                    if count > 5:
                        return self.loop.call_later(10,self.unlock,lock)
                    await asyncio.sleep(0.5)

            wait = getattr(raid_log,'_response_retry',default_sleep)
            self.loop.call_later(wait,self.unlock,lock)
                
            if raid_log and len(raid_log) > 0:
                new_raid = raid_log[0]
                self._cached[tag] = new_raid
            
            if cached and new_raid:
                await self._dispatch_events(clan,cached,new_raid)
        
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
        
        raid_reminders = await EventReminder.raid_reminders_for_clan(clan)
        a_iter = AsyncIter(raid_reminders)
        tasks.extend(
            [ClanRaidLoop._setup_raid_reminder(clan,current_raid,reminder) async for reminder in a_iter]
            )
        
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