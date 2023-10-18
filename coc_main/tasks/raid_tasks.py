import asyncio
import pendulum

from redbot.core.utils import AsyncIter

from ..api_client import BotClashClient as client
from ..exceptions import InvalidTag, ClashAPIError

from .default import TaskLoop

from ..coc_objects.clans.clan import db_ClanEventReminder
from ..coc_objects.events.raid_weekend import aRaidWeekend
from ..discord.feeds.reminders import EventReminders
from ..discord.feeds.raid_results import RaidResultsFeed

bot_client = client()

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
            self.cached_state = None
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
    def task_lock(self) -> asyncio.Lock:
        cog = bot_client.bot.get_cog('ClashOfClansTasks')
        return cog._master_task_lock
    
    ##################################################
    ### PRIMARY TASK LOOP
    ##################################################
    async def _loop_task(self):
        try:
            while self.loop_active:
                st = None
                et = None
                try:
                    if not self.loop_active:
                        raise asyncio.CancelledError
                    
                    if self.task_lock.locked():
                        async with self.task_lock:
                            await asyncio.sleep(0)
                    
                    if self.clan and st.day_of_week not in [5,6,7,1]:
                        continue
                    
                    if not self.loop_active:
                        raise asyncio.CancelledError
                    
                    async with self.task_semaphore:
                        st = pendulum.now()
                        try:
                            self.clan = await self.coc_client.fetch_clan(tag=self.tag)
                        except InvalidTag:
                            raise asyncio.CancelledError

                        current_raid = await self.coc_client.get_raid_weekend(clan=self.clan)
                        if not current_raid:
                            continue
                        if current_raid.do_i_save:
                            current_raid.save_to_database()
                    
                        #Current Raid Management
                        if current_raid.state in ['ongoing']:
                            await asyncio.gather(*(self._setup_raid_reminder(current_raid,r) for r in self.clan.capital_raid_reminders))
                                
                        #Raid State Changes
                        if self.cached_state and current_raid.state != self.cached_state:
                            
                            #Raid Started
                            if current_raid.state in ['ongoing'] and current_raid.start_time != self.cached_raid.start_time:
                                current_raid.starting_trophies = self.clan.capital_points
                                current_raid.save_to_database()
                            
                            #Raid Ended
                            if current_raid.state in ['ended']:
                                self.clan = await self.coc_client.fetch_clan(tag=self.tag,no_cache=True)

                                current_raid.ending_trophies = self.clan.capital_points
                                current_raid.save_to_database()

                                if current_raid.attack_count > 0:
                                    await RaidResultsFeed.send_results(self.clan,current_raid)
                                
                                if self.clan.is_alliance_clan:
                                    bank_cog = bot_client.bot.get_cog("Bank")
                                    if bank_cog:
                                        await asyncio.gather(*(bank_cog.raid_bank_rewards(m) for m in current_raid.members))

                        self.cached_state = current_raid.state
                        self.cached_raid = current_raid
                
                except ClashAPIError as exc:
                    self.api_error = True

                except asyncio.CancelledError:
                    await self.stop()

                finally:
                    if not self.loop_active:
                        raise asyncio.CancelledError  
                    
                    et = pendulum.now()
                    try:
                        run_time = et - st
                        self.run_time.append(run_time.total_seconds())
                    except:
                        pass
                    else:
                        self.data_log.debug(
                            f"{self.tag}: Raid State for {self.clan} updated. Runtime: {run_time.total_seconds()} seconds."
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

    @property
    def sleep_time(self):
        if not self.clan:
            return 30
        
        if pendulum.now().day_of_week not in [5,6,7,1]:
            return 3600
        
        if self.api_error:
            self.api_error = False
            return 900 #15mins
        
        #Friday and Monday
        if pendulum.now().day_of_week in [5,1] and getattr(self.cached_raid,'state',None) == 'ongoing':
            return 300 #5mins
        
        return 600 #10mins