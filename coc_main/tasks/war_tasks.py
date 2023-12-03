import coc
import asyncio
import pendulum
import copy

from typing import *

from collections import defaultdict
from redbot.core.utils import AsyncIter, bounded_gather

from ..api_client import BotClashClient as client
from ..exceptions import InvalidTag, ClashAPIError
from ..cog_coc_client import ClashOfClansClient
from ..utils.constants.coc_constants import WarResult, ClanWarType

from .default import TaskLoop

from ..coc_objects.clans.clan import aClan
from ..coc_objects.events.clan_war import aClanWar
from ..discord.feeds.reminders import EventReminder

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
    def _get_client() -> ClashOfClansClient:
        return bot_client.bot.get_cog('ClashOfClansClient')

    @staticmethod
    async def _war_found(clan:aClan,war:aClanWar):
        try:
            await bot_client.player_queue.add_many([m.tag for m in war.members])
        except asyncio.CancelledError:
            return
        except Exception:
            bot_client.coc_main_log.exception(f"Error in New War task.")

    @staticmethod
    async def _war_start(clan:aClan,war:aClanWar):
        try:
            await bot_client.player_queue.add_many([m.tag for m in war.members])
            if clan.is_registered_clan and len(clan.abbreviation) > 0:
                await bot_client.update_bot_status(
                    cooldown=60,
                    text=f"{clan.abbreviation} declare war!"
                    )
        except asyncio.CancelledError:
            return
        except Exception:
            bot_client.coc_main_log.exception(f"Error in War Start task.")
    
    @staticmethod
    async def _war_ended(clan:aClan,war:aClanWar):
        try:
            await asyncio.sleep(120)
            client = DefaultWarTasks._get_client()

            new_clan = await client.fetch_clan(clan.tag)
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
        except asyncio.CancelledError:
            return
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
        except asyncio.CancelledError:
            return
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
    _instance = None

    _new_war_events = [DefaultWarTasks._war_found]
    _war_start_events = [DefaultWarTasks._war_start]
    _war_ended_events = [DefaultWarTasks._war_ended]
    _ongoing_war_events = [DefaultWarTasks._ongoing_war]
    _new_attack_events = []
    
    @classmethod
    async def _setup_war_reminder(cls,clan:aClan,current_war:aClanWar,reminder:EventReminder):
        reminder_clan = current_war.get_clan(clan.tag)
        remind_members = [m for m in reminder_clan.members if m.unused_attacks > 0]
        await reminder.send_reminder(current_war,*remind_members)

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
        await super().start()
        bot_client.coc_main_log.info(f"War Loop started.")
    
    async def stop(self):
        await super().stop()
        try:
            bot_client.coc_main_log.info(f"War Loop stopped.")
        except:
            pass

    async def reload_tags(self):
        tags = []
        client = DefaultWarTasks._get_client()

        tags.extend([clan.tag for clan in await client.get_registered_clans()])
        tags.extend([clan.tag for clan in await client.get_alliance_clans()])
        tags.extend([clan.tag for clan in await client.get_war_league_clans()])
        self._tags = set(tags)
        self._last_db_update = pendulum.now()

    ##################################################
    ### PRIMARY TASK LOOP
    ##################################################
    async def _loop_task(self):
        try:
            while self.loop_active:
                if self.api_maintenance:
                    await asyncio.sleep(10)
                    continue

                if (pendulum.now() - self._last_db_update).total_seconds() > 300:
                    await self.reload_tags()
                
                if len(self._tags) == 0:
                    await asyncio.sleep(10)
                    continue

                c_tags = copy.copy(self._tags)
                tags = list(set(c_tags))

                st = pendulum.now()
                self._running = True
                a_iter = AsyncIter(tags)

                tasks = [self._run_single_loop(tag) async for tag in a_iter]
                await bounded_gather(*tasks,semaphore=self._loop_semaphore)

                self.last_loop = pendulum.now()
                self._running = False
                try:
                    runtime = self.last_loop-st
                    self.dispatch_time.append(runtime.total_seconds())
                except:
                    pass

                await asyncio.sleep(10)
                continue
            
        except Exception as exc:
            if self.loop_active:
                bot_client.coc_main_log.exception(
                    f"FATAL WAR LOOP ERROR. Attempting restart. {exc}"
                    )
                await TaskLoop.report_fatal_error(
                    message="FATAL WAR LOOP ERROR",
                    error=exc,
                    )
                await self.start()
    
    async def fetch_current_war(self,clan_tag:str):
        current_war = await bot_client.coc.get_current_war(clan_tag)
        if not current_war and pendulum.now().day in range(1,3):
            current_war = await bot_client.coc.get_current_war(
                clan_tag=clan_tag,
                cwl_round=coc.WarRound.current_preparation
                )
        return current_war
    
    async def _run_single_loop(self,tag:str):
        try:
            finished = False
            lock = self._locks[tag]
            if lock.locked():
                return
            await lock.acquire()

            try:
                cached_events = self._cached[tag]
            except KeyError:
                self._cached[tag] = cached_events = {}
            
            st = pendulum.now()

            cached_war = cached_events.get('current_war',None)
            async with self.api_limiter:
                try:
                    clan = await self.coc_client.fetch_clan(tag)
                except InvalidTag:
                    return self.loop.call_later(3600,self.unlock,lock)
                except ClashAPIError:
                    return self.loop.call_later(10,self.unlock,lock)
            
            if not getattr(clan,'public_war_log',False):
                return self.loop.call_later(10,self.unlock,lock)
            
            current_war = None
            count = 0
            while True:
                try:
                    count += 1
                    current_war = await self.fetch%_current_war(tag)
                    break
                except (coc.NotFound,coc.PrivateWarLog,coc.Maintenance,coc.GatewayError):
                    return self.loop.call_later(10,self.unlock,lock)
                except:
                    if count > 5:
                        return self.loop.call_later(10,self.unlock,lock)
                    await asyncio.sleep(0.5)
            
            wait = getattr(current_war,'_response_retry',default_sleep)
            self.loop.call_later(wait,self.unlock,lock)

            self._cached[tag]['current_war'] = current_war
                    
            if getattr(current_war,'is_cwl',False) and pendulum.now().day in range(1,16):
                await self._update_league_group(clan)
                previous_round = None
                async with self.api_limiter:
                    try:
                        previous_round = await bot_client.coc.get_current_war(
                            clan_tag=clan.tag,
                            cwl_round=coc.WarRound.previous_war
                            )
                    except coc.ClashOfClansException:
                        pass

                if previous_round:
                    cached_round = cached_events.get(previous_round.preparation_start_time.raw_time,None)
                    if cached_round:
                        asyncio.create_task(
                            self._dispatch_events(clan,cached_round,previous_round,is_current=False)
                            )
                    self._cached[tag][previous_round.preparation_start_time.raw_time] = previous_round
            
            if cached_war and current_war:
                asyncio.create_task(
                    self._dispatch_events(clan,cached_war,current_war,is_current=True)
                    )
            finished = True

        except asyncio.CancelledError:
            return
        
        except Exception as exc:
            if self.loop_active:
                bot_client.coc_main_log.exception(
                    f"FATAL CLAN WAR LOOP ERROR: {tag}"
                    )
                await TaskLoop.report_fatal_error(
                    message=f"FATAL CLAN WAR LOOP ERROR: {tag}",
                    error=exc,
                    )
            return self.unlock(lock)

        finally:
            if finished:
                et = pendulum.now()
                try:
                    runtime = et - st
                    self.run_time.append(runtime.total_seconds())
                except:
                    pass
        
    async def _update_league_group(self,clan:aClan):
        war_reminders = await EventReminder.war_reminders_for_clan(clan)

        await self.coc_client.get_league_group(clan)

        if clan.is_active_league_clan and clan.league_clan_channel:
            war_league_reminder = [r for r in war_reminders if r.channel_id == clan.league_clan_channel.id]
            if len(war_league_reminder) == 0:
                await EventReminder.create_war_reminder(
                    clan=clan,
                    channel=clan.league_clan_channel,
                    war_types=['cwl'],
                    interval=[12,8,6,4,3,2,1],
                    )
    
    async def _dispatch_events(self,clan:aClan,cached_war:coc.ClanWar,new_war:coc.ClanWar,is_current:bool=False):
        if new_war.state == 'notInWar':
            return
        current_war = await aClanWar.create_from_api(new_war)

        tasks = []
        if getattr(cached_war,'state',None) != 'preparation' and new_war.state == 'preparation':
            a_iter = AsyncIter(ClanWarLoop._new_war_events)
            tasks.extend([event(clan,current_war) async for event in a_iter])
            
        #War Started
        elif getattr(cached_war,'state',None) == 'preparation' and new_war.state == 'inWar':
            a_iter = AsyncIter(ClanWarLoop._war_start_events)
            tasks.extend([event(clan,current_war) async for event in a_iter])

        #War Ended
        elif getattr(cached_war,'state',None) == 'inWar' and new_war.state == 'warEnded':
            a_iter = AsyncIter(ClanWarLoop._war_ended_events)
            tasks.extend([event(clan,current_war) async for event in a_iter])
               
        else:
            a_iter = AsyncIter(ClanWarLoop._ongoing_war_events)
            tasks.extend([event(clan,current_war) async for event in a_iter])
        
            new_attacks = [a for a in new_war.attacks if a.order not in [ca.order for ca in getattr(cached_war,'attacks',[])]]
            a_iter = AsyncIter(new_attacks)
            async for a in a_iter:
                event_iter = AsyncIter(ClanWarLoop._new_attack_events)
                tasks.extend([event(current_war,a.order) async for event in event_iter])

        if is_current:
            war_reminders = await EventReminder.war_reminders_for_clan(clan)
            a_iter = AsyncIter(war_reminders)
            tasks.extend([ClanWarLoop._setup_war_reminder(clan,current_war,reminder) async for reminder in a_iter])
        
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