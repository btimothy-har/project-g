import coc
import asyncio
import pendulum
import random
import copy
import aiohttp

from redbot.core.utils import AsyncIter

from typing import *
from ..api_client import BotClashClient as client
from ..exceptions import InvalidTag, ClashAPIError

from .default import TaskLoop

from ..coc_objects.players.player import aPlayer
from ..coc_objects.clans.clan import aClan

from ..discord.feeds.donations import ClanDonationFeed
from ..discord.feeds.member_movement import ClanMemberFeed

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
    _locks = {}

    _clan_events = [ClanTasks.clan_donation_change]
    _member_join_events = [ClanTasks.clan_member_join]
    _member_leave_events = [ClanTasks.clan_member_leave]

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
    
    def add_to_loop(self,tag:str):
        add, n_tag = super().add_to_loop(tag)
        if add:
            bot_client.coc_main_log.debug(f"Added {n_tag} to Clan Loop.")
    
    def remove_to_loop(self,tag:str):
        remove, n_tag = super().remove_to_loop(tag)
        if remove:
            bot_client.coc_main_log.debug(f"Removed {n_tag} from Clan Loop.")
    
    def delay_multiplier(self,clan:Optional[aClan]=None) -> int:
        return 1
        if not clan:
            return 1
        if clan.is_alliance_clan:
            return 1
        if clan.is_active_league_clan:
            return 1
        if clan.is_registered_clan:
            return 1
        return 3
    
    def defer(self,clan:Optional[aClan]=None) -> bool:
        if self.task_lock.locked():
            if not clan:
                return False
            if clan.is_alliance_clan:
                return False
            if clan.is_active_league_clan:
                return False
            if clan.is_registered_clan:
                return False
            if pendulum.now().int_timestamp - clan.timestamp.int_timestamp >= (15 * 60):
                return False
            return True
        return False
    
    ############################################################
    ### PRIMARY TASK LOOP
    ############################################################
    async def _loop_task(self):
        try:
            while self.loop_active:

                if self.api_maintenance:
                    await asyncio.sleep(10)
                    continue

                tags = copy.copy(self._tags)
                if len(tags) == 0:
                    await asyncio.sleep(10)
                    continue

                st = pendulum.now()
                self._running = True

                sleep = (10 / len(tags))
                tasks = []
                scope_tags = list(tags)
                for tag in scope_tags[:1000]:
                    await asyncio.sleep(sleep)
                    tasks.append(asyncio.create_task(self._run_single_loop(tag)))
            
                await asyncio.gather(*tasks,return_exceptions=True)

                self._last_loop = pendulum.now()
                self._running = False
                try:
                    runtime = self._last_loop-st
                    self.run_time.append(runtime.total_seconds())
                except:
                    pass
                await asyncio.sleep(10)
        
        except Exception as exc:
            if self.loop_active:
                bot_client.coc_main_log.exception(
                    f"FATAL CLAN LOOP ERROR. Attempting restart. {exc}"
                    )
                await TaskLoop.report_fatal_error(
                    message="FATAL CLAN LOOP ERROR",
                    error=exc,
                    )
                await asyncio.sleep(60)
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
                            bot_client.coc_main_log.exception(f"CLAN TASK ERROR: {exc}")
                            await TaskLoop.report_fatal_error(
                                message="CLAN TASK ERROR",
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

                cached_clan = self._cached.get(tag,None)
                if self.defer(cached_clan):
                    return self.loop.call_later(10,self.unlock,lock)

                async with self.api_semaphore: 
                    new_clan = None
                    try:
                        new_clan = await self.coc_client.fetch_clan(tag)
                    except InvalidTag:
                        return self.loop.call_later(3600,self.unlock,lock)
                    except ClashAPIError:
                        return self.loop.call_later(10,self.unlock,lock)
                    
                    wait = int(min(getattr(new_clan,'_response_retry',default_sleep) * self.delay_multiplier(new_clan),600))
                    #wait = getattr(new_clan,'_response_retry',default_sleep)
                    self.loop.call_later(wait,self.unlock,lock)
                
                await new_clan._sync_cache()
                if cached_clan:
                    if new_clan.timestamp.int_timestamp > getattr(cached_clan,'timestamp',pendulum.now()).int_timestamp:
                        self._cached[tag] = new_clan
                        await self._dispatch_events(cached_clan,new_clan)
                else:
                    self._cached[tag] = new_clan
                    
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
    
    async def _dispatch_events(self,old_clan:aClan,new_clan:aClan):
        for event in ClanLoop._clan_events:
            task = asyncio.create_task(event(old_clan,new_clan))
            await self._queue.put(task)

        old_member_iter = AsyncIter(old_clan.members)
        async for member in old_member_iter:
            if member.tag not in [m.tag for m in new_clan.members]:
                for event in ClanLoop._member_leave_events:
                    task = asyncio.create_task(event(member,new_clan))
                    await self._queue.put(task)

        new_member_iter = AsyncIter(new_clan.members)
        async for member in new_member_iter:
            if member.tag not in [m.tag for m in old_clan.members]:
                for event in ClanLoop._member_join_events:
                    task = asyncio.create_task(event(member,new_clan))
                    await self._queue.put(task)