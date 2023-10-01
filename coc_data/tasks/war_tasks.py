import asyncio
import pendulum

from redbot.core.utils import AsyncIter

from .default import TaskLoop

from ..feeds.reminders import EventReminders
from ..objects.clans.clan import aClan, db_ClanEventReminder
from ..objects.events.clan_war import aClanWar

from ..constants.coc_constants import *
from ..exceptions import *

class ClanWarLoop(TaskLoop):
    _loops = {}

    def __new__(cls,bot,clan_tag:str):
        if clan_tag not in cls._loops:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._loops[clan_tag] = instance
        return cls._loops[clan_tag]

    def __init__(self,bot,clan_tag:str):
        self.tag = clan_tag
        
        if self._is_new:
            super().__init__(bot=bot)
            self.clan = None
            self.cached_war = None
            self._is_new = False
    
    async def start(self):
        await super().start()
        self.main_log.debug(f"{self.tag}: War Loop started.")
    
    async def stop(self):
        await super().stop()
        try:
            self.main_log.debug(f"{self.tag}: War Loop stopped.")
        except:
            pass
    
    @property
    def sleep_time(self):
        if not self.clan.public_war_log:
            return 1800 #30mins
        if self.api_error:
            self.api_error = False
            return 1200
        #return 600 if getattr(self.cached_war,'type',None) == 'cwl' else 600 #10mins
        return 600
    
    ##################################################
    ### PRIMARY TASK LOOP
    ##################################################
    async def _loop_task(self):
        try:
            while self.loop_active:
                try:
                    reminder_tasks = None
                    reward_tasks = None

                    st = pendulum.now()
                    if not self.loop_active:
                        raise asyncio.CancelledError

                    if self.clash_task_lock.locked():
                        async with self.clash_task_lock:
                            await asyncio.sleep(0)
                    
                    if not self.loop_active:
                        return
                    
                    work_start = pendulum.now()
                    try:
                        self.clan = await aClan.create(self.tag,no_cache=False,bot=self.bot)
                    except CacheNotReady:
                        return
                    
                    if not self.clan.public_war_log:
                        return
                        
                    current_war = await self.clan.get_current_war()
                    if not current_war:
                        return            
                    if current_war.do_i_save:
                        current_war.save_war_to_db()

                    #Current War Management
                    if current_war.state in ['inWar','warEnded'] and pendulum.now() < current_war.end_time.add(hours=2):
                        #new attacks
                        if self.cached_war:
                            new_attacks = [a for a in current_war.attacks if a.order not in [ca.order for ca in self.cached_war.attacks]]

                        #reminders
                        if current_war.state in ['inWar']:
                            reminder_tasks = [asyncio.create_task(self._setup_war_reminder(current_war,r)) for r in self.clan.war_reminders]
                        
                    #War State Changes
                    if self.cached_war and current_war.state != self.cached_war.state:
                        #War State Changes - new war spin
                        if current_war.state in ['preparation'] and current_war.preparation_start_time != self.cached_war.preparation_start_time:
                            async for m in AsyncIter(current_war.members):
                                self.client.cog.player_cache.add_to_queue(m.tag)
                    
                        #War State Changes - war started
                        if current_war.state in ['inWar']:
                            pass
                        
                        #War Ended
                        if current_war.state in ['warEnded']:
                            reward_task = None
                            if self.clan.is_alliance_clan and current_war.type == ClanWarType.RANDOM:
                                war_clan = current_war.get_clan(self.tag)
                                bank_cog = self.bot.get_cog("Bank")
                                reward_tasks = [asyncio.create_task(bank_cog.war_bank_rewards(m)) for m in war_clan.members]

                    self.cached_war = current_war

                    if reminder_tasks:
                        await asyncio.gather(*reminder_tasks)            
                    if reward_tasks:
                        await asyncio.gather(*reward_task)
                
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

                    self.main_log.debug(
                        f"{self.tag}: War State for {self.clan} updated. Runtime: {run_time} seconds."
                        )
                    await asyncio.sleep(self.sleep_time)

        except asyncio.CancelledError:
            await self.stop()

        except Exception as exc:
            self.main_log.exception(
                f"{self.tag}: FATAL WAR LOOP ERROR. Attempting Restart after 300 seconds. {exc}"
                )
            await self.report_fatal_error(
                message="FATAL WAR LOOP ERROR",
                error=exc,
                )
            self.error_loops += 1
            await self.stop()
            await asyncio.sleep(300)
            await self.start()
    
    ##################################################
    ### SUPPORTING FUNCTIONS
    ##################################################
    async def _setup_war_reminder(self,current_war:aClanWar,reminder:db_ClanEventReminder):
        try:
            time_remaining = current_war.end_time.int_timestamp - pendulum.now().int_timestamp

            if len(reminder.interval_tracker) > 0:
                next_reminder = max(reminder.interval_tracker)

                if time_remaining < (next_reminder * 3600):
                    channel = self.bot.get_channel(reminder.channel_id)
                    reminder_clan = current_war.get_clan(self.clan.tag)
                    
                    if channel and reminder_clan:        
                        event_reminder = EventReminders(channel_id=reminder.channel_id)

                        remind_members = [m for m in reminder_clan.members if m.unused_attacks > 0]
                        
                        create_reminder_task = [asyncio.create_task(event_reminder.add_account(m.tag)) for m in remind_members]
                        await asyncio.gather(*create_reminder_task,return_exceptions=True)
                        
                        await event_reminder.send_war_reminders(self.clan,current_war)

                        war_reminder_tracking = reminder.interval_tracker.copy()
                        war_reminder_tracking.remove(next_reminder)
                        reminder.interval_tracker = war_reminder_tracking
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
                f"{self.tag}: Clan War Reminder Error - {exc}"
                )