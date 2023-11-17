import coc
import asyncio
import pendulum
import aiohttp

from typing import *

from ..api_client import BotClashClient as client
from ..cog_coc_client import ClashOfClansClient
from ..exceptions import InvalidTag, ClashAPIError

from .default import TaskLoop

from ..coc_objects.clans.clan import aClan
from ..coc_objects.events.raid_weekend import aRaidWeekend
from ..discord.feeds.reminders import EventReminders
from ..discord.feeds.raid_results import RaidResultsFeed
from ..discord.feeds.reminders import EventReminders, db_ClanEventReminder

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
    async def _raid_start(clan:aClan,raid:aRaidWeekend):

        def _get_client() -> ClashOfClansClient:
            return bot_client.bot.get_cog('ClashOfClansClient')
        
        try:
            await asyncio.sleep(120)
            coc_client = _get_client()

            new_clan = await coc_client.fetch_clan(clan.tag)
            raid.starting_trophies = new_clan.capital_points
            await raid.save_to_database()

        except:
            bot_client.coc_main_log.exception(f"Error in New Raid task.")
    
    @staticmethod
    async def _raid_ended(clan:aClan,raid:aRaidWeekend):

        def _get_client() -> ClashOfClansClient:
            return bot_client.bot.get_cog('ClashOfClansClient')
        
        try:
            await asyncio.sleep(120)
            coc_client = _get_client()
            
            new_clan = await coc_client.fetch_clan(tag=clan.tag)
            raid.ending_trophies = new_clan.capital_points
            await raid.save_to_database()

            if raid.attack_count > 0:
                await RaidResultsFeed.send_results(new_clan,raid)

        except:
            bot_client.coc_main_log.exception(f"Error in Raid Ended task.")

class ClanRaidLoop(TaskLoop):
    _instance = None
    _cached = {}
    _locks = {}
    _reminder_locks = {}

    _raid_start_events = [DefaultRaidTasks._raid_start]
    _raid_ended_events = [DefaultRaidTasks._raid_ended]

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
            self._tags = []
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

    def add_to_loop(self,tag:str):
        n_tag = coc.utils.correct_tag(tag)
        if n_tag not in self._tags:
            self._tags.append(n_tag)
            bot_client.coc_main_log.info(f"Added {n_tag} to Raid Loop.")
    
    def remove_to_loop(self,tag:str):
        n_tag = coc.utils.correct_tag(tag)
        if n_tag in self._tags:
            self._tags.remove(n_tag)
            bot_client.coc_main_log.info(f"Removed {n_tag} from Raid Loop.")
    
    ##################################################
    ### PRIMARY TASK LOOP
    ##################################################
    async def _loop_task(self):
        try:
            while self.loop_active:
                if self.api_maintenance:
                    await asyncio.sleep(30)
                    continue

                st = pendulum.now()
                if st.day_of_week not in [5,6,7,1]:
                    await asyncio.sleep(60)
                    continue

                if len(self._tags) == 0:
                    await asyncio.sleep(30)
                    continue

                sleep = (1 / len(self._tags))
                for tag in self._tags:
                    await asyncio.sleep(sleep)
                    task = asyncio.create_task(self._run_single_loop(tag))
                    await self._queue.put(task)

                await asyncio.sleep(30)

        except Exception as exc:
            if self.loop_active:
                bot_client.coc_main_log.exception(
                    f"FATAL RAID LOOP ERROR. Attempting restart. {exc}"
                    )
                await TaskLoop.report_fatal_error(
                    message="FATAL RAID LOOP ERROR",
                    error=exc,
                    )
                await self._loop_task()
    
    async def _collector_task(self):
        try:
            while True:
                await asyncio.sleep(0)
                task = await self._queue.get()
                if task.done() or task.cancelled():
                    try:
                        await task
                    except asyncio.CancelledError:
                        continue
                    except Exception as exc:
                        if self.loop_active:
                            bot_client.coc_main_log.exception(f"RAID TASK ERROR: {exc}")
                            await TaskLoop.report_fatal_error(
                                message="RAID TASK ERROR",
                                error=exc,
                                )
                    finally:
                        self._queue.task_done()
                else:
                    await self._queue.put(task)

        except asyncio.CancelledError:
            while not self._queue.empty():
                await asyncio.sleep(0)
                task = await self._queue.get()
                try:
                    await task
                except:
                    continue
                finally:
                    self._queue.task_done()
    
    async def _run_single_loop(self,tag:str):
        try:
            lock = self._locks[tag]
        except KeyError:
            self._locks[tag] = lock = asyncio.Lock()

        try:
            async with self.task_semaphore:
                if lock.locked():
                    return
                await lock.acquire()

                cached_raid = self._cached.get(tag,None)
                
                st = pendulum.now()
                try:
                    clan = await bot_client.coc.get_clan(tag,cls=aClan)
                except (coc.ClashOfClansException,RuntimeError,aiohttp.ServerDisconnectedError) as exc:
                    return self.unlock(lock)
                
                raid_log = None
                new_raid = None
                try:
                    raid_log = await bot_client.coc.get_raid_log(clan_tag=tag,limit=1)
                except (coc.ClashOfClansException,RuntimeError,aiohttp.ServerDisconnectedError) as exc:
                    return self.unlock(lock)
                finally:
                    if raid_log and len(raid_log) > 0:
                        new_raid = raid_log[0]
                        self._cached[tag] = new_raid
                    
                    wait = getattr(raid_log,'_response_retry',default_sleep)
                    self.loop.call_later(wait,self.unlock,lock)
                
                if cached_raid and new_raid:
                    await self._dispatch_events(clan,cached_raid,new_raid)
        
        except Exception as exc:
            if self.loop_active:
                bot_client.coc_main_log.exception(
                    f"FATAL CAPITAL RAID LOOP ERROR: {tag}"
                    )
                await TaskLoop.report_fatal_error(
                    message=f"FATAL CAPITAL RAID LOOP ERROR: {tag}",
                    error=exc,
                    )
            return self.unlock(lock)

        finally:
            et = pendulum.now()
            try:
                runtime = et - st
                self.run_time.append(runtime.total_seconds())
            except:
                pass
    
    async def _dispatch_events(self,clan:aClan,cached_raid:coc.RaidLogEntry,new_raid:coc.RaidLogEntry):        
        current_raid = await aRaidWeekend.create_from_api(clan,new_raid)

        #New Raid Started
        if new_raid.start_time != cached_raid.start_time:
            for event in ClanRaidLoop._raid_start_events:
                task = asyncio.create_task(event(clan,current_raid))
                await self._queue.put(task)

        #Raid Ended
        elif new_raid.state in ['ended'] and getattr(cached_raid,'state',None) == 'ongoing':
            for event in ClanRaidLoop._raid_ended_events:
                task = asyncio.create_task(event(clan,current_raid))
                await self._queue.put(task)
        
        raid_reminders = await EventReminders.raid_reminders_for_clan(clan)
        for r in raid_reminders:
            task = asyncio.create_task(self._setup_raid_reminder(clan,current_raid,r))
            await self._queue.put(task)
    
    ##################################################
    ### SUPPORTING FUNCTIONS
    ##################################################
    async def _setup_raid_reminder(self,clan:aClan,current_raid:aRaidWeekend,reminder:db_ClanEventReminder):
        def _update_reminder(new_tracking:List[int]=[]):
            reminder.interval_tracker = new_tracking
            reminder.save()
        
        try:
            lock = self._reminder_locks[str(reminder.id)]
        except KeyError:
            self._reminder_locks[str(reminder.id)] = lock = asyncio.Lock()
        
        if lock.locked():
            return

        async with lock:
            try:
                time_remaining = current_raid.end_time.int_timestamp - pendulum.now().int_timestamp

                if len(reminder.interval_tracker) > 0:
                    next_reminder = max(reminder.interval_tracker)

                    #Reminder is overdue
                    if next_reminder > (time_remaining / 3600):
                        channel = bot_client.bot.get_channel(reminder.channel_id)

                        if channel:
                            event_reminder = EventReminders(channel_id=reminder.channel_id)
                            remind_members = [m for m in current_raid.members if m.attack_count < 6]

                            await asyncio.gather(*(event_reminder.add_account(m.tag) for m in remind_members))
                            await event_reminder.send_raid_reminders(clan,current_raid)
                
                if len(reminder.reminder_interval) > 0:
                    track = []
                    for remind in reminder.reminder_interval:
                        if remind < (time_remaining / 3600):
                            track.append(remind)
                    
                    await bot_client.run_in_thread(_update_reminder,track)
            
            except Exception:
                bot_client.coc_main_log.exception(f"Error in Raid Reminder task.")