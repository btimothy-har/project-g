import coc
import asyncio
import pendulum
import random

from redbot.core.utils import AsyncIter

from ..api_client import BotClashClient as client
from ..exceptions import InvalidTag, ClashAPIError

from .default import TaskLoop

from ..coc_objects.players.player import aPlayer
from ..coc_objects.clans.clan import aClan

from ..discord.feeds.clan_feed import ClanDataFeed
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
    _loops = {}
    _clan_events = [ClanTasks.clan_donation_change]
    _member_join_events = [ClanTasks.clan_member_join]
    _member_leave_events = [ClanTasks.clan_member_leave]

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
            self._lock = asyncio.Lock()
            self.cached_clan = None
            self.feed_count = 0
        
        self._is_new = False
    
    async def start(self):
        i = await super().start()
        if i:
            bot_client.coc_main_log.debug(f"{self.tag}: Clan Loop started.")
    
    async def stop(self):
        await super().stop()
        self.unlock(self._lock)
        try:
            bot_client.coc_main_log.debug(f"{self.tag}: Clan Loop stopped.")
        except:
            pass

    @property
    def delay_multiplier(self) -> float:
        if not self.cached_clan:
            return 1
        if self.feed_count > 0:
            return 1
        if self.cached_clan.is_alliance_clan:
            return 1
        if self.cached_clan.is_active_league_clan:
            return 1        
        if self.cached_clan.is_registered_clan:
            return 2
        return 5
    
    ############################################################
    ### PRIMARY TASK LOOP
    ############################################################
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
                f"{self.tag}: FATAL CLAN LOOP ERROR. Attempting restart. {exc}"
                )
            await TaskLoop.report_fatal_error(
                message="FATAL CLAN LOOP ERROR",
                error=exc,
                )
            await self.stop()
            return await self.start()
    
    async def _run_single_loop(self):
        if self._lock.locked():
            return
        
        await self._lock.acquire()
        
        if self.task_lock.locked():
            if self.to_defer:
                self.defer_count += 1
                self.deferred = True
                return self.unlock(self._lock)
            else:
                async with self.task_lock:
                    await asyncio.sleep(0)
            
        async with self.task_semaphore:            
            self.deferred = False
            self.defer_count = 0
            st = pendulum.now()

            new_clan = None
            try:
                new_clan = await self.coc_client.fetch_clan(self.tag,no_cache=True,enforce_lock=True)
            except InvalidTag as exc:
                raise asyncio.CancelledError from exc
            except ClashAPIError as exc:
                return
            finally:
                wait = int(min(getattr(new_clan,'_response_retry',default_sleep) * self.delay_multiplier,600))
                self.loop.call_later(wait,self.unlock,self._lock)

            if self.cached_clan:
                self.feed_count = len(await ClanDataFeed.feeds_for_clan(self.cached_clan))
                old_clan = self.cached_clan
                await self._dispatch_events(old_clan,new_clan)
            
            self.cached_clan = new_clan
            asyncio.create_task(new_clan._sync_cache())

            et = pendulum.now()
            runtime = et-st
            self.run_time.append(runtime.total_seconds())
    
    async def _dispatch_events(self,old_clan:aClan,new_clan:aClan):
        for event in ClanLoop._clan_events:
            asyncio.create_task(event(old_clan,new_clan))

        members_joined = [m for m in new_clan.members if m.tag not in [n.tag for n in old_clan.members]]
        members_left = [m for m in old_clan.members if m.tag not in [n.tag for n in new_clan.members]]

        old_member_iter = AsyncIter(members_left)
        async for member in old_member_iter:            
            for event in ClanLoop._member_leave_events:
                asyncio.create_task(event(member,new_clan))

        new_member_iter = AsyncIter(members_joined)
        async for member in new_member_iter:
            for event in ClanLoop._member_join_events:
                asyncio.create_task(event(member,new_clan))