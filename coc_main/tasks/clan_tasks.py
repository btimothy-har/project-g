import coc
import asyncio
import pendulum
import random
import copy
import aiohttp

from redbot.core.utils import AsyncIter, bounded_gather

from typing import *
from collections import defaultdict
from ..api_client import BotClashClient as client
from ..exceptions import InvalidTag, ClashAPIError

from .default import TaskLoop

from ..coc_objects.players.player import aPlayer
from ..coc_objects.clans.clan import aClan

from ..discord.feeds.donations import ClanDonationFeed
from ..discord.feeds.member_movement import ClanMemberFeed
from ..exceptions import CacheNotReady

from ..utils.utils import chunks

bot_client = client()
default_sleep = 60

############################################################
############################################################
#####
##### DEFAULT CLAN TASKS
#####
############################################################
############################################################
class ClanTasks():
    
    @staticmethod
    async def clan_member_join(member:aPlayer,clan:aClan):
        await ClanMemberFeed.member_join(clan,member)

    @staticmethod
    async def clan_member_leave(member:aPlayer,clan:aClan):
        await ClanMemberFeed.member_leave(clan,member)
    
    @staticmethod
    async def clan_donation_change(old_clan:aClan,new_clan:aClan):
        await ClanDonationFeed.start_feed(new_clan,old_clan)

############################################################
############################################################
#####
##### CLAN TASK LOOP
#####
############################################################
############################################################
class ClanLoop(TaskLoop):
    _instance = None
    _cached = {}
    _locks = defaultdict(asyncio.Lock)
    _task_lock = asyncio.Lock()
    _task_semaphore = asyncio.Semaphore(10)

    _clan_events = [ClanTasks.clan_donation_change]
    _member_join_events = [ClanTasks.clan_member_join]
    _member_leave_events = [ClanTasks.clan_member_leave]

    @classmethod
    async def _dispatch_events(cls,old_clan:aClan,new_clan:aClan):
        tasks = []
        tasks.append(new_clan._sync_cache())
        tasks.extend([event(old_clan,new_clan) for event in cls._clan_events])

        old_member_iter = AsyncIter(old_clan.members)
        async for member in old_member_iter:
            if member.tag not in [m.tag for m in new_clan.members]:
                e_iter = AsyncIter(cls._member_leave_events)
                tasks.extend([event(member,new_clan) async for event in e_iter])

        new_member_iter = AsyncIter(new_clan.members)
        async for member in new_member_iter:
            if member.tag not in [m.tag for m in old_clan.members]:
                e_iter = AsyncIter(cls._member_join_events)
                tasks.extend([event(member,new_clan) async for event in e_iter])

        async with cls._task_lock:
            while True:
                sem = cls._task_semaphore
                if not sem._waiters: 
                    break
                if sem._waiters and len(sem._waiters) < len(tasks):
                    break
                await asyncio.sleep(0.1)
                continue
        await bounded_gather(*tasks,semaphore=sem)

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
        bot_client.coc_main_log.info(f"Clan Loop started.")
        await super().start()
    
    async def stop(self):
        try:
            bot_client.coc_main_log.info(f"Clan Loop stopped.")
        except:
            pass
        await super().stop()
    
    async def delay_multiplier(self,clan:Optional[aClan]=None) -> int:
        if not clan:
            return 1
        if clan.is_alliance_clan:
            return 1
        if clan.is_active_league_clan:
            return 1
        if clan.is_registered_clan:
            return 1
        return random.randint(3,10)
    
    def is_priority(self,clan:aClan) -> bool:
        if clan.is_alliance_clan:
            return True
        if clan.is_active_league_clan:
            return True
        if clan.is_registered_clan:
            return True
        return False
    
    ############################################################
    ### PRIMARY TASK LOOP
    ############################################################
    def _get_sample_tags(self) -> list:
        c_tags = copy.copy(self._tags)
        tags = random.sample(list(c_tags),min(len(c_tags),1000))
        if len(self._priority_tags) > 0:
            tags.extend(list(self._priority_tags))
        return list(set(tags)) if len(tags) > 0 else []
    
    async def _loop_task(self):        
        try:
            while self.loop_active:
                if self.api_maintenance:
                    await asyncio.sleep(10)
                    continue

                tags = await bot_client.run_in_thread(self._get_sample_tags)
                if len(tags) == 0:
                    await asyncio.sleep(10)
                    continue

                st = pendulum.now()
                self._running = True
                a_iter = AsyncIter(tags)

                tasks = [self._launch_single_loop(tag) async for tag in a_iter]
                await bounded_gather(*tasks,semaphore=self._loop_semaphore)

                self.last_loop = pendulum.now()
                self._running = False
                try:
                    runtime = self.last_loop - st
                    self.dispatch_time.append(runtime.total_seconds())
                except:
                    pass

                await asyncio.sleep(10)
                continue

        except Exception as exc:
            if self.loop_active:
                bot_client.coc_main_log.exception(
                    f"FATAL CLAN LOOP ERROR. Attempting restart. {exc}"
                    )
                await TaskLoop.report_fatal_error(
                    message=f"FATAL CLAN LOOP ERROR",
                    error=exc,
                    )                    
                await asyncio.sleep(60)
                await self.start()
    
    async def _launch_single_loop(self,tag:str):
        lock = self._locks[tag]
        if lock.locked():
            return
        await lock.acquire()

        cached = self._cached.get(tag)                
        await self._run_single_loop(tag,lock,cached)

    async def _run_single_loop(self,tag:str,lock:asyncio.Lock,cached:Optional[aClan]=None):
        try:            
            finished = False            
            async with self.task_limiter:
                st = pendulum.now()

                async with self.api_limiter:
                    new_clan = None
                    try:
                        new_clan = await self.coc_client.fetch_clan(tag)
                    except InvalidTag:
                        return self.loop.call_later(3600,self.unlock,lock)
                    except ClashAPIError:
                        return self.loop.call_later(10,self.unlock,lock)
                             
                wait = int(min(getattr(new_clan,'_response_retry',default_sleep) * await self.delay_multiplier(new_clan),600))
                self.loop.call_later(wait,self.unlock,lock)                
                
                self._cached[tag] = new_clan

                if cached:
                    if new_clan.timestamp.int_timestamp > getattr(cached,'timestamp',pendulum.now()).int_timestamp:
                        asyncio.create_task(ClanLoop._dispatch_events(cached,new_clan))
                
                if self.is_priority(new_clan):
                    self._priority_tags.add(tag)
                else:
                    self._priority_tags.discard(tag)
                
                finished = True
        
        except asyncio.CancelledError:
            return
                    
        except Exception as exc:
            if self.loop_active:
                bot_client.coc_main_log.exception(
                    f"CLAN LOOP ERROR: {tag}"
                    )
                await TaskLoop.report_fatal_error(
                    message=f"CLAN LOOP ERROR: {tag}",
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
    
    