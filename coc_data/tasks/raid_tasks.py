import asyncio
import pendulum

from redbot.core.utils import AsyncIter

from .default import TaskLoop

from ..feeds.reminders import EventReminders
from ..objects.clans.clan import aClan, db_ClanEventReminder
from ..objects.events.raid_weekend import aRaidWeekend
from ..feeds.raid_results import RaidResultsFeed

from ..constants.coc_constants import *
from ..exceptions import *

class ClanRaidLoop(TaskLoop):
    _loops = {}

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
            self.clan = None
            self.cached_raid = None
            self._is_new = False
    
    async def start(self):
        await super().start()
        self.main_log.debug(f"{self.tag}: Raid Loop started.")
    
    async def stop(self):
        await super().stop()
        try:
            self.main_log.debug(f"{self.tag}: Raid Loop stopped.")
        except:
            pass
    
    @property
    def sleep_time(self):
        if pendulum.now().day_of_week not in [5,6,7,1]:
            return 3600
        elif self.api_error:
            self.api_error = False
            return 900
        return 300
    
    ##################################################
    ### PRIMARY TASK LOOP
    ##################################################
    async def _loop_task(self):
        try:
            await self._clan_raid_loop()
                        
        except asyncio.CancelledError:
            await self.stop()

        except Exception as exc:
            self.main_log.exception(
                f"{self.tag}: FATAL RAID LOOP ERROR. Attempting Restart after 300 seconds. {exc}"
                )
            await self.report_fatal_error(
                message="FATAL RAID LOOP ERROR",
                error=exc,
                )
            self.error_loops += 1
            await self.stop()
            await asyncio.sleep(300)
            await self.start()
    
    async def _clan_raid_loop(self):
        while self.loop_active:
            try:
                reminder_tasks = None
                result_tasks = None
                reward_task = None

                st = pendulum.now()
                if not self.loop_active:
                    raise asyncio.CancelledError
                
                if self.clash_task_lock.locked():
                    async with self.clash_task_lock:
                        await asyncio.sleep(0)
                
                if self.clan and st.day_of_week not in [5,6,7,1]:
                    return
                
                try:
                    self.clan = self.client.cog.get_clan(self.tag)
                except CacheNotReady:
                    return
                
                if not self.loop_active:
                    return

                async with self.clash_semaphore:
                    st = pendulum.now()
                    current_raid = await self.client.cog.get_raid_weekend(self.tag)
                    api_end = pendulum.now()
                    if not current_raid:
                        return None
                    if current_raid.do_i_save:
                        current_raid.save_raid_to_db()
                
                    #Current Raid Management
                    if current_raid.state in ['ongoing','ended'] and pendulum.now() < current_raid.end_time.add(hours=2):

                        if current_raid.state in ['ongoing']:
                            reminder_tasks = [asyncio.create_task(self._setup_raid_reminder(current_raid,r)) for r in self.clan.raid_reminders]
                            
                    #Raid State Changes
                    if self.cached_raid and current_raid.state != self.cached_raid.state:
                        #Raid Started
                        if current_raid.state in ['ongoing'] and current_raid.start_time != self.cached_raid.start_time:
                            current_raid.starting_trophies = self.clan.capital_points
                            current_raid.save_raid_to_db()
                        
                        #Raid Ended
                        if current_raid.state in ['ended']:
                            self.clan = await aClan.create(self.tag,no_cache=True)
                            
                            current_raid.ending_trophies = self.clan.capital_points
                            current_raid.save_raid_to_db()

                            if current_raid.attack_count > 0:
                                results_image = await current_raid.get_results_image()
                                result_tasks = [asyncio.create_task(RaidResultsFeed.send_results(self.clan,f,results_image)) for f in self.clan.raid_result_feed]
                            
                            if self.clan.is_alliance_clan:
                                bank_cog = self.bot.get_cog("Bank")
                                reward_task = [asyncio.create_task(bank_cog.raid_bank_rewards(m)) for m in current_raid.members]

                    self.cached_raid = current_raid

                    if reminder_tasks:
                        await asyncio.gather(*reminder_tasks)                    
                    if result_tasks:
                        await asyncio.gather(*result_tasks)                    
                    if reward_task:
                        await asyncio.gather(*reward_task)
            
            except ClashAPIError as exc:
                if hasattr(self.bot,'coc_client_alt'):
                    self.switch_api_client()
                else:
                    self.api_error = True

            except asyncio.CancelledError:
                await self.stop()

            finally:
                if not self.loop_active:
                    return                
                et = pendulum.now()

                try:
                    api_time = api_end.int_timestamp-st.int_timestamp
                    self.api_time.append(api_time)
                except:
                    pass
                try:
                    run_time = et.int_timestamp-st.int_timestamp
                    self.run_time.append(run_time)
                except:
                    pass

                self.data_log.debug(
                    f"{self.tag}: Raid State for {self.clan} updated. Runtime: {run_time} seconds."
                    )
                await asyncio.sleep(self.sleep_time)
    
    async def _setup_raid_reminder(self,current_raid:aRaidWeekend,reminder:db_ClanEventReminder):
        try:
            time_remaining = current_raid.end_time.int_timestamp - pendulum.now().int_timestamp

            if len(reminder.interval_tracker) > 0:
                next_reminder = max(reminder.interval_tracker)

                if time_remaining < (next_reminder * 3600):
                    channel = self.bot.get_channel(reminder.channel_id)

                    if channel:        
                        event_reminder = EventReminders()

                        remind_members = [m for m in current_raid.members if m.attack_count < 6]

                        create_reminder_task = [asyncio.create_task(event_reminder.add_account(m.tag)) for m in remind_members]        
                        await asyncio.gather(*create_reminder_task,return_exceptions=True)

                        await event_reminder.send_raid_reminders(self.clan,current_raid)

                        raid_reminder_tracking = reminder.interval_tracker.copy()
                        raid_reminder_tracking.remove(next_reminder)
                        reminder.interval_tracker = raid_reminder_tracking
                        reminder.save()
                
            if len(reminder.interval_tracker) != len(reminder.reminder_interval) and len(reminder.reminder_interval) > 0:
                track = []
                for i in reminder.reminder_interval:
                    if i < (time_remaining / 3600):
                        track.append(i)
                if len(track) > 0:
                    reminder.interval_tracker = track
                    reminder.save()
        
        except Exception as exc:
            self.main_log.exception(
                f"{self.tag}: Raid Weekend Reminder Error - {exc}"
                )