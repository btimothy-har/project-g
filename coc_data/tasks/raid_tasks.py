import asyncio
import pendulum

from redbot.core.utils import AsyncIter

from .default import TaskLoop

from coc_client.api_client import BotClashClient

from ..feeds.reminders import EventReminders
from ..objects.clans.clan import aClan, db_ClanEventReminder
from ..objects.events.raid_weekend import aRaidWeekend
from ..feeds.raid_results import RaidResultsFeed

from ..constants.coc_constants import *
from ..exceptions import *

bot_client = BotClashClient()

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
            return 1800
        elif pendulum.now().day_of_week in [5,1]:
            return 300 #5mins
        return 600 #10mins
    
    ##################################################
    ### PRIMARY TASK LOOP
    ##################################################
    async def _loop_task(self):
        try:
            while self.loop_active:
                try:
                    st = pendulum.now()
                    if not self.loop_active:
                        raise asyncio.CancelledError
                    
                    if self.clash_task_lock.locked():
                        async with self.clash_task_lock:
                            await asyncio.sleep(0)
                    
                    if not self.loop_active:
                        raise asyncio.CancelledError
                    
                    work_start = pendulum.now()
                    if self.clan and st.day_of_week not in [5,6,7,1]:
                        continue

                    try:
                        self.clan = await bot_client.cog.fetch_clan(tag=self.tag)
                    except InvalidTag:
                        raise asyncio.CancelledError

                    current_raid = await self.clan.get_raid_weekend()
                    if not current_raid:
                        continue
                    if current_raid.do_i_save:
                        current_raid.save_to_database()
                
                    #Current Raid Management
                    if current_raid.state in ['ongoing']:
                        await asyncio.gather(*(self._setup_raid_reminder(current_raid,r) for r in self.clan.capital_raid_reminders))
                            
                    #Raid State Changes
                    if self.cached_raid and current_raid.state != self.cached_raid.state:
                        
                        #Raid Started
                        if current_raid.state in ['ongoing'] and current_raid.start_time != self.cached_raid.start_time:
                            current_raid.starting_trophies = self.clan.capital_points
                            current_raid.save_to_database()
                        
                        #Raid Ended
                        if current_raid.state in ['ended']:
                            self.clan = await bot_client.cog.fetch_clan(tag=self.tag,no_cache=True)

                            current_raid.ending_trophies = self.clan.capital_points
                            current_raid.save_to_database()

                            if current_raid.attack_count > 0:
                                results_image = await current_raid.get_results_image()
                                await asyncio.gather(*(RaidResultsFeed.send_results(self.clan,f,results_image) for f in self.clan.raid_result_feed))
                            
                            if self.clan.is_alliance_clan:
                                bank_cog = bot_client.bot.get_cog("Bank")
                                if bank_cog:
                                    await asyncio.gather(*(bank_cog.raid_bank_rewards(m) for m in current_raid.members))

                    self.cached_raid = current_raid
                
                except ClashAPIError as exc:
                    self.api_error = True

                except asyncio.CancelledError:
                    await self.stop()

                finally:
                    if not self.loop_active:
                        return                
                    et = pendulum.now()

                    try:
                        api_time = et.int_timestamp-work_start.int_timestamp
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

    async def _setup_raid_reminder(self,current_raid:aRaidWeekend,reminder:db_ClanEventReminder):
        try:
            time_remaining = current_raid.end_time.int_timestamp - pendulum.now().int_timestamp

            if len(reminder.interval_tracker) > 0:
                next_reminder = max(reminder.interval_tracker)

                if time_remaining < (next_reminder * 3600):
                    channel = bot_client.bot.get_channel(reminder.channel_id)

                    if channel:
                        event_reminder = EventReminders(channel_id=reminder.channel_id)
                        remind_members = [m for m in current_raid.members if m.attack_count < 6]

                        await asyncio.gather(*(event_reminder.add_account(m.tag) for m in remind_members))
                        await event_reminder.send_raid_reminders(self.clan,current_raid)

                        raid_reminder_tracking = reminder.interval_tracker.copy()
                        raid_reminder_tracking.remove(next_reminder)
                        reminder.interval_tracker = raid_reminder_tracking
                        reminder.save()
                
            if len(reminder.reminder_interval) > 0:
                if len(reminder.interval_tracker) != len(reminder.reminder_interval):
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