import coc
import asyncio
import pendulum
import random
import copy
import aiohttp

from redbot.core.utils import AsyncIter

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
    _loops = {}

    _clan_events = [ClanTasks.clan_donation_change]
    _member_join_events = [ClanTasks.clan_member_join]
    _member_leave_events = [ClanTasks.clan_member_leave]

    @classmethod
    async def _dispatch_events(old_clan:aClan,new_clan:aClan):
        [asyncio.create_task(event(old_clan,new_clan)) for event in ClanLoop._clan_events]

        old_member_iter = AsyncIter(old_clan.members)
        async for member in old_member_iter:
            if member.tag not in [m.tag for m in new_clan.members]:
                [asyncio.create_task(event(member,new_clan)) for event in ClanLoop._member_leave_events]

        new_member_iter = AsyncIter(new_clan.members)
        async for member in new_member_iter:
            if member.tag not in [m.tag for m in old_clan.members]:
                [asyncio.create_task(event(member,new_clan)) for event in ClanLoop._member_join_events]

    def __new__(cls,tag:str):
        if tag not in cls._loops:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._loops[tag] = instance
        return cls._loops[tag]

    def __init__(self,tag:str):
        if self._is_new:
            self.tag = tag
            self.lock = asyncio.Lock()
            self.cached = None
            super().__init__()
            self._is_new = False
    
    async def delay_multiplier(self,clan:Optional[aClan]=None) -> int:
        if not clan:
            return 1
        if clan.is_alliance_clan:
            return 1
        if clan.is_active_league_clan:
            return 1
        if clan.is_registered_clan:
            return 1
        return 10
    
    async def defer(self) -> bool:
        if self.task_lock.locked():
            if not self.cached:
                return False
            if self.cached.is_alliance_clan:
                return False
            if self.cached.is_active_league_clan:
                return False
            if self.cached.is_registered_clan:
                return False
            if pendulum.now().int_timestamp - self.cached.timestamp.int_timestamp >= 3600:
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

                if self.lock.locked():
                    await asyncio.sleep(10)
                    continue

                await self.lock.acquire()
                asyncio.create_task(self._run_single_loop())

                await asyncio.sleep(30)
                continue
        
        except asyncio.CancelledError:
            return
        
        except Exception as exc:
            if self.loop_active:
                await self.stop()
                bot_client.coc_main_log.exception(
                    f"{self.tag}: FATAL CLAN LOOP ERROR. Attempting restart. {exc}"
                    )
                await TaskLoop.report_fatal_error(
                    message=f"{self.tag}: FATAL CLAN LOOP ERROR",
                    error=exc,
                    )                    
                await asyncio.sleep(60)
                await self.start()

    async def _run_single_loop(self):
        try:
            if await self.defer():
                return self.loop.call_later(10,self.unlock,self.lock)
            
            st = pendulum.now()
            self._running = True

            async with self.api_semaphore:                
                new_clan = None
                try:
                    new_clan = await self.coc_client.fetch_clan(self.tag)
                except InvalidTag:
                    return self.loop.call_later(3600,self.unlock,self.lock)
                except ClashAPIError:
                    return self.loop.call_later(10,self.unlock,self.lock)
            
            await new_clan._sync_cache()                
            wait = int(min(getattr(new_clan,'_response_retry',default_sleep) * await self.delay_multiplier(new_clan),600))
            self.loop.call_later(wait,self.unlock,self.lock)                
            
            if self.cached:
                if new_clan.timestamp.int_timestamp > getattr(self.cached,'timestamp',pendulum.now()).int_timestamp:
                    asyncio.create_task(ClanLoop._dispatch_events(self.cached,new_clan))
                    self.cached = new_clan
            else:
                self.cached = new_clan
                    
        except Exception as exc:
            if self.loop_active:
                bot_client.coc_main_log.exception(
                    f"CLAN LOOP ERROR: {self.tag}"
                    )
                await TaskLoop.report_fatal_error(
                    message=f"CLAN LOOP ERROR: {self.tag}",
                    error=exc,
                    )
            return self.unlock(self.lock)

        finally:
            et = pendulum.now()
            try:
                runtime = et - st
                self.run_time.append(runtime.total_seconds())
            except:
                pass
    
    