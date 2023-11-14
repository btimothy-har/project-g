import coc
import asyncio
import pendulum

from typing import *

from redbot.core.utils import AsyncIter

from ..api_client import BotClashClient as client
from ..exceptions import InvalidTag, ClashAPIError
from ..cog_coc_client import ClashOfClansClient
from ..utils.constants.coc_constants import WarResult, ClanWarType

from .default import TaskLoop

from ..coc_objects.clans.clan import aClan
from ..coc_objects.events.clan_war import aClanWar
from ..discord.feeds.reminders import EventReminders, db_ClanEventReminder

bot_client = client()
default_sleep = 60

############################################################
############################################################
#####
##### DEFAULT WAR TASKS
#####
############################################################
############################################################
class DefaultWarTasks():        

    @staticmethod
    async def _war_found(clan:aClan,war:aClanWar):
        try:
            await bot_client.player_cache.add_many_to_queue([m.tag for m in war.members])
        except Exception:
            bot_client.coc_main_log.exception(f"Error in New War task.")

    @staticmethod
    async def _war_start(clan:aClan,war:aClanWar):
        try:
            await bot_client.player_cache.add_many_to_queue([m.tag for m in war.members])
            if clan.is_registered_clan and len(clan.abbreviation) > 0:
                await bot_client.update_bot_status(
                    cooldown=60,
                    text=f"{clan.abbreviation} declare war!"
                    )
        except Exception:
            bot_client.coc_main_log.exception(f"Error in War Start task.")
    
    @staticmethod
    async def _war_ended(clan:aClan,war:aClanWar):
        def _get_client() -> ClashOfClansClient:
            return bot_client.bot.get_cog('ClashOfClansClient')
        try:
            await asyncio.sleep(120)
            coc_client = _get_client()            
            new_clan = await coc_client.fetch_clan(clan.tag)

            if new_clan.is_registered_clan and len(new_clan.abbreviation) > 0:
                if war.get_clan(new_clan.tag).result in ['winning','won']:                
                    if war.type == ClanWarType.RANDOM:
                        if new_clan.war_win_streak >= 3:
                            await bot_client.update_bot_status(
                                cooldown=60,
                                text=f"{new_clan.abbreviation} on a {new_clan.war_win_streak} streak!"
                                )
                        else:
                            await bot_client.update_bot_status(
                                cooldown=60,
                                text=f"{new_clan.abbreviation} with {new_clan.war_wins} War Wins."
                                )
                    elif war.type == ClanWarType.CWL:
                        await bot_client.update_bot_status(
                            cooldown=60,
                            text=f"{new_clan.abbreviation} winning in CWL!"
                            )
                          
        except Exception:
            bot_client.coc_main_log.exception(f"Error in War Ended task.")
    
    @staticmethod
    async def _ongoing_war(clan:aClan,war:aClanWar):
        try:
            if war.state != 'inWar':
                return
            
            time_remaining = war.end_time.int_timestamp - pendulum.now().int_timestamp
            if clan.is_registered_clan and len(clan.abbreviation) > 0 and time_remaining > 3600:
                war_clan = war.get_clan(clan.tag)
                if war_clan.attacks_used > 0:
                    await bot_client.update_bot_status(
                        cooldown=360,
                        text=f"{clan.abbreviation} {WarResult.ongoing(war.get_clan(clan.tag).result)} in war!"
                        )
        except Exception:
            bot_client.coc_main_log.exception(f"Error in Ongoing War task.")
    
    @staticmethod
    async def _new_attack(war:aClanWar,attack_order:int):
        return

############################################################
############################################################
#####
##### WAR TASK LOOP
#####
############################################################
############################################################
class ClanWarLoop(TaskLoop):
    _loops = {}
    _new_war_events = [DefaultWarTasks._war_found]
    _war_start_events = [DefaultWarTasks._war_start]
    _war_ended_events = [DefaultWarTasks._war_ended]
    _ongoing_war_events = [DefaultWarTasks._ongoing_war]
    _new_attack_events = []

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
            self._remind_lock = asyncio.Lock()
            self.cached_war = None
            self.cached_events = {}
    
    async def start(self):
        i = await super().start()
        if i:
            bot_client.coc_main_log.debug(f"{self.tag}: War Loop started.")
    
    async def stop(self):
        await super().stop()
        self.unlock(self._lock)
        try:
            bot_client.coc_main_log.debug(f"{self.tag}: War Loop stopped.")
        except:
            pass
    
    @classmethod
    def add_war_end_event(cls,event):
        if event.__name__ not in [e.__name__ for e in cls._war_ended_events]:
            cls._war_ended_events.append(event)
            bot_client.coc_main_log.info(f"Registered {event.__name__} {event} to War Ended Events.")
    
    @classmethod
    def remove_war_end_event(cls,event):        
        if event.__name__ in [e.__name__ for e in cls._war_ended_events]:
            event = [e for e in cls._war_ended_events if e.__name__ == event.__name__][0]
            cls._war_ended_events.remove(event)
            bot_client.coc_main_log.info(f"Removed {event.__name__} {event} from War Ended Events.")

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
                f"{self.tag}: FATAL WAR LOOP ERROR. Attempting restart. {exc}"
                )
            await TaskLoop.report_fatal_error(
                message="FATAL WAR LOOP ERROR",
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

            if not clan.public_war_log:
                return self.unlock(self._lock)
            
            current_war = None
            try:
                current_war = await bot_client.coc.get_current_war(self.tag)
            except (coc.NotFound,coc.Maintenance,coc.GatewayError):
                return
            finally:
                self.loop.call_later(
                    getattr(current_war,'_response_retry',default_sleep),
                    self.unlock,
                    self._lock
                    )
            
            if getattr(current_war,'is_cwl',False) and pendulum.now().day in range(1,16):
                await self._update_league_group(clan)
                #update previous round
                previous_round = await bot_client.coc.get_current_war(self.tag,cwl_round=coc.WarRound.previous_war)
                if previous_round:
                    cached_round = self.cached_events.get(previous_round.preparation_start_time.raw_time,None)
                    if cached_round:
                        await self._dispatch_events(clan,cached_round,previous_round,is_current=False)
                    self.cached_events[previous_round.preparation_start_time.raw_time] = previous_round
            
            if self.cached_war and current_war:
                old_war = self.cached_war
                await self._dispatch_events(clan,old_war,current_war,is_current=True)
            
            self.cached_war = current_war

            if current_war.state != 'notInWar':
                self.cached_events[current_war.preparation_start_time.raw_time] = current_war

            et = pendulum.now()
            runtime = et - st
            self.run_time.append(runtime.total_seconds())

    async def _dispatch_events(self,clan:aClan,cached_war:coc.ClanWar,new_war:coc.ClanWar,is_current:bool=False):
        if new_war.state == 'notInWar':
            return
        
        current_war = await aClanWar.create_from_api(new_war)

        if getattr(cached_war,'state',None) != 'preparation' and new_war.state == 'preparation':
            for event in ClanWarLoop._new_war_events:
                asyncio.create_task(event(clan,current_war))  
            
        #War Started
        elif getattr(cached_war,'state',None) == 'preparation' and new_war.state == 'inWar':
            for event in ClanWarLoop._war_start_events:
                asyncio.create_task(event(clan,current_war))

        #War Ended
        elif getattr(cached_war,'state',None) == 'inWar' and new_war.state == 'warEnded':
            for event in ClanWarLoop._war_ended_events:
                asyncio.create_task(event(clan,current_war))
               
        else:
            for event in ClanWarLoop._ongoing_war_events:
                asyncio.create_task(event(clan,current_war))
        
            new_attacks = [a for a in new_war.attacks if a.order not in [ca.order for ca in getattr(cached_war,'attacks',[])]]
            for event in ClanWarLoop._new_attack_events:
                for a in new_attacks:
                    asyncio.create_task(event(current_war,a.order))

        if is_current:
            war_reminders = await EventReminders.war_reminders_for_clan(clan)
            for r in war_reminders:
                asyncio.create_task(self._setup_war_reminder(clan,current_war, r))
        
    async def _update_league_group(self,clan:aClan):
        war_reminders = await EventReminders.war_reminders_for_clan(clan)

        await self.coc_client.get_league_group(clan)

        if clan.is_active_league_clan and clan.league_clan_channel:
            war_league_reminder = [r for r in war_reminders if r.channel_id == clan.league_clan_channel.id]
            if len(war_league_reminder) == 0:
                await EventReminders.create_war_reminder(
                    clan=clan,
                    channel=clan.league_clan_channel,
                    war_types=['cwl'],
                    interval=[12,8,6,4,3,2,1],
                    )
    
    ##################################################
    ### WAR EVENTS
    ##################################################
    async def _setup_war_reminder(self,clan:aClan,current_war:aClanWar,reminder:db_ClanEventReminder):
        def _update_reminder(new_tracking:List[int]=[]):
            reminder.interval_tracker = new_tracking
            reminder.save()

        if self._remind_lock.locked():
            return
        
        async with self._remind_lock:
            try:
                time_remaining = current_war.end_time.int_timestamp - pendulum.now().int_timestamp

                if len(reminder.interval_tracker) > 0:
                    next_reminder = max(reminder.interval_tracker)

                    #Reminder is overdue
                    if next_reminder > (time_remaining / 3600):
                        channel = bot_client.bot.get_channel(reminder.channel_id)
                        reminder_clan = current_war.get_clan(clan.tag)
                        
                        if channel and reminder_clan:        
                            event_reminder = EventReminders(channel_id=reminder.channel_id)

                            remind_members = [m for m in reminder_clan.members if m.unused_attacks > 0]
                            
                            await asyncio.gather(*(event_reminder.add_account(m.tag) for m in remind_members))                        
                            await event_reminder.send_war_reminders(clan,current_war)

                if len(reminder.reminder_interval) > 0:
                    track = []
                    for remind in reminder.reminder_interval:
                        if remind < (time_remaining / 3600):
                            track.append(remind)
                        
                    await bot_client.run_in_thread(_update_reminder,track)
                            
            except Exception:
                bot_client.coc_main_log.exception(f"Error in War Reminder task.")