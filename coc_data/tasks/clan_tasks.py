import asyncio
import pendulum
import random

from redbot.core.utils import AsyncIter

from .default import TaskLoop
from ..objects.clans.clan import aClan
from ..feeds.donations import ClanDonationFeed
from ..feeds.member_movement import ClanMemberFeed
from ..exceptions import *

class ClanLoop(TaskLoop):
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
    
    @property
    def sleep_time(self):
        if not self.cached_clan:
            sleep = 300
        elif self.api_error:
            sleep = 600
            self.api_error = False
        elif self.cached_clan.is_alliance_clan:
            sleep = 60 # 1 minute
        elif self.cached_clan.is_registered_clan or self.cached_clan.cwl_config.is_cwl_clan:
            sleep = 180 # 3 minutes
        else:
            sleep = 300 # 5 minutes
        return sleep

    ##################################################
    ### PRIMARY TASK LOOP
    ##################################################
    async def _loop_task(self):
        try:
            await self._single_loop()

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
        
    async def _single_loop(self):
        while self.loop_active:
            try:
                st = pendulum.now()
                if not self.loop_active:
                    raise asyncio.CancelledError
                
                if self.clash_task_lock.locked():
                    async with self.clash_task_lock:
                        await asyncio.sleep(0)
                
                async with self.clash_semaphore:
                    st = pendulum.now()
                    try:
                        clan = await aClan.create(self.tag,no_cache=True,bot=self.bot)
                    except InvalidTag as exc:
                        raise asyncio.CancelledError from exc

                    api_end = pendulum.now()

                    if clan.is_alliance_clan or clan.is_registered_clan or clan.cwl_config.is_cwl_clan or len(clan.member_feed) > 0:
                        if not self.cached_clan:
                            self.client.cog.player_cache.queue.extend([m.tag for m in clan.members])
                                    
                        else:
                            members_joined = [m for m in clan.members if m.tag not in [n.tag for n in self.cached_clan.members]]
                            members_left = [m for m in self.cached_clan.members if m.tag not in [n.tag for n in clan.members]]

                            if len(members_joined) > 0:
                                [asyncio.create_task(ClanMemberFeed.member_join(clan,m.tag)) for m in members_joined]
                            if len(members_left) > 0:
                                [asyncio.create_task(ClanMemberFeed.member_join(clan,m.tag)) for m in members_left]
                    
                            await ClanDonationFeed.start_feed(clan,self.cached_clan)
                    self.cached_clan = clan
                    
            except ClashAPIError as exc:                
                self.api_error = True

            except asyncio.CancelledError:
                await self.stop()

            finally:
                if not self.loop_active:
                    return                
                et = pendulum.now()

                try:
                    api_time = api_end.int_timestamp-st.int_timestamp
                    self.api_time.append(api_time)
                except:
                    pass

                try:
                    run_time = et.int_timestamp-st.int_timestamp
                    self.run_time.append(run_time)
                except:
                    pass

                self.main_log.debug(
                    f"{self.tag}: Clan {self.cached_clan} updated. Runtime: {run_time} seconds."
                    )
                await asyncio.sleep(self.sleep_time)