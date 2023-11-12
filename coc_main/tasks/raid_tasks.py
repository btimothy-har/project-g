import coc
import asyncio
import pendulum

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
    _loops = {}
    _raid_start_events = [DefaultRaidTasks._raid_start]
    _raid_ended_events = [DefaultRaidTasks._raid_ended]

    def __new__(cls,clan_tag:str):
        if clan_tag not in cls._loops:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._loops[clan_tag] = instance
        return cls._loops[clan_tag]

    def __init__(self,clan_tag:str):
        self.tag = clan_tag
        
        if self._is_new:
            super().__init__()
            self._is_new = False
            self._lock = asyncio.Lock()
            self.cached_raid = None
    
    async def start(self):
        i = await super().start()
        if i:
            bot_client.coc_main_log.debug(f"{self.tag}: Raid Loop started.")
    
    async def stop(self):
        await super().stop()
        self.unlock(self._lock)
        try:
            bot_client.coc_main_log.debug(f"{self.tag}: Raid Loop stopped.")
        except:
            pass
    
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
    
    ##################################################
    ### PRIMARY TASK LOOP
    ##################################################
    async def _loop_task(self):
        try:
            while self.loop_active:
                await asyncio.sleep(10)
                if self.api_maintenance:
                    continue                
                await self._run_single_loop()
        
        except asyncio.CancelledError:
            return await self.stop()

        except Exception as exc:
            if not self.loop_active:
                return await self.stop()
            
            bot_client.coc_main_log.exception(
                f"{self.tag}: FATAL RAID LOOP ERROR. Attempting restart. {exc}"
                )
            await TaskLoop.report_fatal_error(
                message="FATAL RAID LOOP ERROR",
                error=exc,
                )
            await self.stop()
            return await self.start()
    
    async def _run_single_loop(self):
        if self._lock.locked():
            return
        await self._lock.acquire()

        async with self.task_semaphore:
            st = pendulum.now()
            try:
                clan = await self.coc_client.fetch_clan(tag=self.tag)
            except InvalidTag:
                raise asyncio.CancelledError
            except ClashAPIError:
                return self.unlock(self._lock)
            
            raid_log = None
            try:
                raid_log = await bot_client.coc.get_raid_log(clan_tag=self.tag,limit=1)
            except (coc.NotFound,coc.Maintenance,coc.GatewayError):
                return
            finally:
                self.loop.call_later(
                    getattr(raid_log,'_response_retry',default_sleep),
                    self.unlock,
                    self._lock
                    )
            
            if raid_log and len(raid_log) > 0:
                new_raid = raid_log[0]

                if self.cached_raid and new_raid:
                    old_raid = self.cached_raid
                    await self._dispatch_events(clan,old_raid,new_raid)
            
                self.cached_raid = new_raid

            et = pendulum.now()
            runtime = et - st
            self.run_time.append(runtime.total_seconds())
    
    async def _dispatch_events(self,clan:aClan,cached_raid:coc.RaidLogEntry,new_raid:coc.RaidLogEntry):        
        current_raid = await aRaidWeekend.create_from_api(clan,new_raid)

        #New Raid Started
        if new_raid.start_time != cached_raid.start_time:
            for event in ClanRaidLoop._raid_start_events:
                asyncio.create_task(event(clan,current_raid))

        #Raid Ended
        elif new_raid.state in ['ended'] and getattr(cached_raid,'state',None) == 'ongoing':
            for event in ClanRaidLoop._raid_ended_events:
                asyncio.create_task(event(clan,current_raid))
        
        raid_reminders = await EventReminders.raid_reminders_for_clan(clan)
        for r in raid_reminders:
            asyncio.create_task(self._setup_raid_reminder(clan,current_raid,r))
    
    ##################################################
    ### SUPPORTING FUNCTIONS
    ##################################################
    async def _setup_raid_reminder(self,clan:aClan,current_raid:aRaidWeekend,reminder:db_ClanEventReminder):
        def _update_reminder(new_tracking:List[int]=[]):
            reminder.interval_tracker = new_tracking
            reminder.save()

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
                if len(reminder.interval_tracker) != len(reminder.reminder_interval):
                    track = []
                    for remind in reminder.reminder_interval:
                        if remind < (time_remaining / 3600):
                            track.append(remind)
                    
                    await bot_client.run_in_thread(_update_reminder,track)
        
        except Exception as exc:
            bot_client.coc_main_log.exception(f"Error in Raid Reminder task.")