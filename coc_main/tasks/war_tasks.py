import coc
import asyncio
import pendulum
import aiohttp

from typing import *


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
    _instance = None
    _cached = {}
    _locks = {}
    _reminder_locks = {}

    _new_war_events = [DefaultWarTasks._war_found]
    _war_start_events = [DefaultWarTasks._war_start]
    _war_ended_events = [DefaultWarTasks._war_ended]
    _ongoing_war_events = [DefaultWarTasks._ongoing_war]
    _new_attack_events = []

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
            self._tags = []
            self._is_new = False            
    
    async def start(self):
        bot_client.coc_main_log.info(f"War Loop started.")
        await super().start()
    
    async def stop(self):
        try:
            bot_client.coc_main_log.info(f"War Loop stopped.")
        except:
            pass
        await super().stop()
    
    def add_to_loop(self,tag:str):
        n_tag = coc.utils.correct_tag(tag)
        if n_tag not in self._tags:
            self._tags.append(n_tag)
            bot_client.coc_main_log.info(f"Added {n_tag} to War Loop.")
    
    def remove_to_loop(self,tag:str):
        n_tag = coc.utils.correct_tag(tag)
        if n_tag in self._tags:
            self._tags.remove(n_tag)
            bot_client.coc_main_log.info(f"Removed {n_tag} from War Loop.")

    ##################################################
    ### PRIMARY TASK LOOP
    ##################################################
    async def _loop_task(self):
        try:
            while self.loop_active:
                if self.api_maintenance:
                    await asyncio.sleep(30)
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
                    f"FATAL WAR LOOP ERROR. Attempting restart. {exc}"
                    )
                await TaskLoop.report_fatal_error(
                    message="FATAL WAR LOOP ERROR",
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
                            bot_client.coc_main_log.exception(f"WAR TASK ERROR: {exc}")
                            await TaskLoop.report_fatal_error(
                                message="WAR TASK ERROR",
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

                cached_events = self._cached.get(tag,None)
                if not cached_events:
                    self._cached[tag] = cached_events = {}

                cached_war = cached_events.get('current_war',None)
                
                st = pendulum.now()
                try:
                    clan = await bot_client.coc.get_clan(tag,cls=aClan)
                except (coc.ClashOfClansException,RuntimeError,aiohttp.ServerDisconnectedError) as exc:
                    return self.unlock(lock)
                
                if not getattr(clan,'public_war_log',False):
                    return self.unlock(lock)
                
                current_war = None
                try:
                    current_war = await bot_client.coc.get_current_war(tag)
                except (coc.ClashOfClansException,RuntimeError,aiohttp.ServerDisconnectedError) as exc:
                    return self.unlock(lock)
                finally:
                    self._cached[tag]['current_war'] = current_war
                    wait = getattr(current_war,'_response_retry',default_sleep)
                    self.loop.call_later(wait,self.unlock,lock)
                        
                if getattr(current_war,'is_cwl',False) and pendulum.now().day in range(1,16):
                    await self._update_league_group(clan)
                    #update previous round
                    try:
                        previous_round = await bot_client.coc.get_current_war(tag,cwl_round=coc.WarRound.previous_war)
                    except (coc.ClashOfClansException,RuntimeError,aiohttp.ServerDisconnectedError) as exc:
                        pass
                    else:
                        if previous_round:
                            cached_round = cached_events.get(previous_round.preparation_start_time.raw_time,None)
                            if cached_round:
                                await self._dispatch_events(clan,cached_round,previous_round,is_current=False)
                            self._cached[tag][previous_round.preparation_start_time.raw_time] = previous_round
                
                if cached_war and current_war:
                    await self._dispatch_events(clan,cached_war,current_war,is_current=True)
        
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
            et = pendulum.now()
            try:
                runtime = et - st
                self.run_time.append(runtime.total_seconds())
            except:
                pass

    async def _dispatch_events(self,clan:aClan,cached_war:coc.ClanWar,new_war:coc.ClanWar,is_current:bool=False):
        if new_war.state == 'notInWar':
            return
        
        current_war = await aClanWar.create_from_api(new_war)

        if getattr(cached_war,'state',None) != 'preparation' and new_war.state == 'preparation':
            for event in ClanWarLoop._new_war_events:
                task = asyncio.create_task(event(clan,current_war))
                await self._queue.put(task)
            
        #War Started
        elif getattr(cached_war,'state',None) == 'preparation' and new_war.state == 'inWar':
            for event in ClanWarLoop._war_start_events:
                task = asyncio.create_task(event(clan,current_war))
                await self._queue.put(task)

        #War Ended
        elif getattr(cached_war,'state',None) == 'inWar' and new_war.state == 'warEnded':
            for event in ClanWarLoop._war_ended_events:
                task = asyncio.create_task(event(clan,current_war))
                await self._queue.put(task)
               
        else:
            for event in ClanWarLoop._ongoing_war_events:
                task = asyncio.create_task(event(clan,current_war))
                await self._queue.put(task)
        
            new_attacks = [a for a in new_war.attacks if a.order not in [ca.order for ca in getattr(cached_war,'attacks',[])]]
            for event in ClanWarLoop._new_attack_events:
                for a in new_attacks:
                    task = asyncio.create_task(event(current_war,a.order))
                    await self._queue.put(task)

        if is_current:
            war_reminders = await EventReminders.war_reminders_for_clan(clan)
            for r in war_reminders:
                task = asyncio.create_task(self._setup_war_reminder(clan,current_war, r))
                await self._queue.put(task)
        
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

        try:
            lock = self._reminder_locks[str(reminder.id)]
        except KeyError:
            self._reminder_locks[str(reminder.id)] = lock = asyncio.Lock()

        if lock.locked():
            return
        
        async with lock:
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