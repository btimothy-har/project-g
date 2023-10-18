import asyncio
import pendulum
import random

from redbot.core.utils import AsyncIter

from ..api_client import BotClashClient as client
from ..exceptions import InvalidTag, ClashAPIError

from .default import TaskLoop

from ..discord.feeds.donations import ClanDonationFeed
from ..discord.feeds.member_movement import ClanMemberFeed

bot_client = client()

class ClanLoop(TaskLoop):
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
            self.cached_clan = None
            self._is_new = False
    
    async def start(self):
        await super().start()
        self.main_log.debug(f"{self.tag}: Clan Loop started.")
    
    async def stop(self):
        await super().stop()
        try:
            self.main_log.debug(f"{self.tag}: Clan Loop stopped.")
        except:
            pass    

    ##################################################
    ### PRIMARY TASK LOOP
    ##################################################
    async def _loop_task(self):
        try:
            while self.loop_active:
                self.completed = False
                st = None
                et = None

                try:
                    if not self.loop_active:
                        raise asyncio.CancelledError
                    
                    if self.task_lock.locked():
                        if self.to_defer:
                            self.defer_count += 1
                            self.deferred = True
                            continue
                        else:
                            async with self.task_lock:
                                await asyncio.sleep(0)

                    async with self.task_semaphore:
                        self.deferred = False
                        self.defer_count = 0
                        st = pendulum.now()
                        try:
                            async with self.api_semaphore:
                                t1 = pendulum.now()
                                clan = await self.coc_client.fetch_clan(self.tag,no_cache=True,enforce_lock=True)
                                diff = pendulum.now() - t1
                                self.api_time.append(diff.total_seconds())
                        except InvalidTag as exc:
                            raise asyncio.CancelledError from exc

                        t1 = pendulum.now()
                        if clan.is_alliance_clan or clan.is_registered_clan or clan.is_active_league_clan or len(clan.discord_feeds) > 0:
                            if not self.cached_clan:
                                await bot_client.player_cache.add_many_to_queue([m.tag for m in clan.members])
                                        
                            else:
                                members_joined = [m for m in clan.members if m.tag not in [n.tag for n in self.cached_clan.members]]
                                members_left = [m for m in self.cached_clan.members if m.tag not in [n.tag for n in clan.members]]

                                await asyncio.gather(
                                    *(ClanMemberFeed.member_join(clan,m.tag) for m in members_joined),
                                    *(ClanMemberFeed.member_leave(clan,m.tag) for m in members_left),
                                    ClanDonationFeed.start_feed(clan,self.cached_clan)
                                    )
                        self.cached_clan = clan
                        diff = pendulum.now() - t1
                        self.work_time.append(diff.total_seconds())

                        self.completed = True
                        
                except ClashAPIError as exc:                
                    self.api_error = True

                except asyncio.CancelledError:
                    await self.stop()

                finally:
                    if not self.loop_active:
                        raise asyncio.CancelledError
                    
                    if self.completed:
                        et = pendulum.now()                    
                        run_time = et - st

                        self.run_time.append(run_time.total_seconds())
                        self.main_log.debug(
                            f"{self.tag}: Clan {self.cached_clan} updated. Runtime: {run_time.total_seconds()} seconds."
                            )
                        
                    await asyncio.sleep(self.sleep_time)

        except asyncio.CancelledError:
            await self.stop()

        except Exception as exc:
            self.main_log.exception(
                f"{self.tag}: FATAL CLAN LOOP ERROR. Attempting Restart after 300 seconds. {exc}"
                )
            await self.report_fatal_error(
                message="FATAL CLAN LOOP ERROR",
                error=exc,
                )
            self.error_loops += 1
            await self.stop()
            await asyncio.sleep(300)
            await self.start()
    
    @property
    def sleep_time(self):
        if self.deferred:
            return random.randint(30,90)
        
        if self.api_error:
            self.api_error = False
            return 600
        
        if not self.cached_clan:
            return 10
        
        if self.cached_clan.is_alliance_clan or len(self.cached_clan.discord_feeds) > 0:
            return random.randint(120,300) #2-3min
        
        if self.cached_clan.is_registered_clan or self.cached_clan.is_active_league_clan:
            return random.randint(180,300) #3-5min
        
        return random.randint(300,900) #5-15min