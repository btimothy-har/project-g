import asyncio
import pendulum

from redbot.core.utils import AsyncIter

from ..api_client import BotClashClient as client
from ..exceptions import InvalidTag, ClashAPIError
from ..utils.constants.coc_constants import WarResult, ClanWarType

from .default import TaskLoop

from ..coc_objects.clans.clan import db_ClanEventReminder
from ..coc_objects.events.clan_war import aClanWar
from ..discord.feeds.reminders import EventReminders

bot_client = client()

class ClanWarLoop(TaskLoop):
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
            self.cached_war = None
            self.cached_state = None
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

                    if self.task_lock.locked():
                        async with self.task_lock:
                            await asyncio.sleep(0)
                    
                    if not self.loop_active:
                        raise asyncio.CancelledError
                    
                    work_start = pendulum.now()
                    try:
                        self.clan = await self.coc_client.fetch_clan(tag=self.tag)
                    except InvalidTag:
                        raise asyncio.CancelledError
                    
                    if not self.clan.public_war_log:
                        continue

                    if self.clan.is_active_league_clan:
                        if self.clan.league_clan_channel:
                            war_league_reminder = [r for r in self.clan.clan_war_reminders if r.channel_id == self.clan.league_clan_channel.id]
                            if len(war_league_reminder) == 0:
                                await self.clan.create_clan_war_reminder(
                                    channel=self.clan.league_clan_channel,
                                    war_types=['cwl'],
                                    interval=[12,8,6,4,3,2,1],
                                    )
                        
                    current_war = await self.coc_client.get_clan_war(clan=self.clan)
                    if not current_war or current_war.state == 'notInWar':
                        if bot_client.current_season.cwl_start <= pendulum.now() <= bot_client.current_season.cwl_end.add(days=1):
                            league_group = await self.coc_client.get_league_group(clan=self.clan)

                            if league_group:
                                league_clan = league_group.get_clan(self.tag)
                                current_war = league_clan.current_war
                    
                    if not current_war:
                        continue
                    
                    if current_war.do_i_save:
                        current_war.save_to_database()

                    #Current War Management
                    if current_war.state in ['inWar','warEnded']:
                        #new attacks
                        if self.cached_war:
                            new_attacks = [a for a in current_war.attacks if a.order not in [ca.order for ca in self.cached_war.attacks]]
                        
                        await asyncio.gather(*(self._setup_war_reminder(current_war,r) for r in self.clan.clan_war_reminders))
                    
                    if current_war.state in ['inWar']:
                        time_remaining = current_war.end_time.int_timestamp - pendulum.now().int_timestamp

                        if self.clan.is_registered_clan and len(self.clan.abbreviation) > 0 and time_remaining > 3600:
                            await bot_client.update_bot_status(
                                cooldown=360,
                                text=f"{self.clan.abbreviation} {WarResult.ongoing(current_war.get_clan(self.clan.tag).result)} in war!"
                                )
                        
                    #War State Changes
                    if self.cached_state and current_war.state != self.cached_state:

                        #War State Changes - new war spin
                        if current_war.state in ['preparation'] and current_war.preparation_start_time != self.cached_war.preparation_start_time:
                            async for m in AsyncIter(current_war.members):
                                bot_client.player_cache.add_to_queue(m.tag)
                    
                        #War State Changes - war started
                        if current_war.state in ['inWar']:
                            if self.clan.is_registered_clan and len(self.clan.abbreviation) > 0:
                                await bot_client.update_bot_status(
                                    cooldown=60,
                                    text=f"{self.clan.abbreviation} declare war!"
                                    )
                        
                        #War Ended
                        if current_war.state in ['warEnded']:                            
                            if self.clan.is_registered_clan and len(self.clan.abbreviation) > 0:
                                if current_war.get_clan(self.clan.tag).result in ['winning','won']:
                                    if current_war.type == ClanWarType.RANDOM:
                                        if self.clan.war_win_streak >= 3:
                                            await bot_client.update_bot_status(
                                                cooldown=60,
                                                text=f"{self.clan.abbreviation} on a {self.clan.war_win_streak} streak!"
                                                )
                                        else:
                                            await bot_client.update_bot_status(
                                                cooldown=60,
                                                text=f"{self.clan.abbreviation} with {self.clan.war_wins} War Wins."
                                                )
                                    elif current_war.type == ClanWarType.CWL:
                                        await bot_client.update_bot_status(
                                            cooldown=60,
                                            text=f"{self.clan.abbreviation} with the CWL Win!"
                                            )
                                            
                            if self.clan.is_alliance_clan and current_war.type == ClanWarType.RANDOM:
                                war_clan = current_war.get_clan(self.tag)
                                bank_cog = bot_client.bot.get_cog("Bank")
                                if bank_cog:
                                    await asyncio.gather(*(bank_cog.war_bank_rewards(m) for m in war_clan.members))
                    
                    self.cached_state = current_war.state
                    self.cached_war = current_war
                
                except ClashAPIError as exc:
                    self.api_error = True

                except asyncio.CancelledError:
                    await self.stop()

                finally:
                    if not self.loop_active:
                        return                
                    et = pendulum.now()
                    try:
                        work_time = et.int_timestamp - work_start.int_timestamp
                        self.work_time.append(work_time)
                    except:
                        pass
                    try:
                        run_time = et.int_timestamp - st.int_timestamp
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
                    channel = bot_client.bot.get_channel(reminder.channel_id)
                    reminder_clan = current_war.get_clan(self.clan.tag)
                    
                    if channel and reminder_clan:        
                        event_reminder = EventReminders(channel_id=reminder.channel_id)

                        remind_members = [m for m in reminder_clan.members if m.unused_attacks > 0]
                        
                        await asyncio.gather(*(event_reminder.add_account(m.tag) for m in remind_members))                        
                        await event_reminder.send_war_reminders(self.clan,current_war)

                        war_reminder_tracking = reminder.interval_tracker.copy()
                        war_reminder_tracking.remove(next_reminder)
                        reminder.interval_tracker = war_reminder_tracking
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
                f"{self.tag}: Clan War Reminder Error - {exc}"
                )
    
    @property
    def sleep_time(self):
        if not self.clan.public_war_log:
            return 1800 #30mins
        if self.api_error:
            self.api_error = False
            return 1200
        return 600