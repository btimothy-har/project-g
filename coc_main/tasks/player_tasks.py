import asyncio
import pendulum
import random

from ..api_client import BotClashClient as client
from ..exceptions import InvalidTag, ClashAPIError

from .default import TaskLoop

from ..coc_objects.players.player import db_Player, db_PlayerStats
from ..coc_objects.events.clan_war_leagues import db_WarLeaguePlayer

bot_client = client()

class PlayerLoop(TaskLoop):
    _loops = {}

    def __new__(cls,player_tag:str):
        if player_tag not in cls._loops:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._loops[player_tag] = instance
        return cls._loops[player_tag]

    def __init__(self,player_tag:str):
        self.tag = player_tag
        
        if self._is_new:
            super().__init__()
            self._is_new = False
            self.cached_player = None

    async def start(self):
        await super().start()
        self.main_log.debug(f"{self.tag}: Player Loop started.")
    
    async def stop(self):
        await super().stop()
        try:
            self.main_log.debug(f"{self.tag}: Player Loop stopped.")
        except:
            pass
    
    ##################################################
    ### PRIMARY TASK LOOP
    ##################################################
    async def _loop_task(self):
        try:
            while self.loop_active:
                try:
                    if not self.loop_active:
                        raise asyncio.CancelledError
                    
                    if self.task_lock.locked():
                        if self.defer_count > 20:
                            async with self.task_lock:
                                await asyncio.sleep(0)
                        else:
                            self.defer_count += 1
                            self.deferred = True
                            continue
                    
                    async with self.task_semaphore:
                        self.deferred = False
                        self.defer_count = 0
                        st = pendulum.now()
                        try:
                            async with self.api_semaphore:
                                self.cached_player = await self.coc_client.fetch_player(self.tag,no_cache=True,enforce_lock=True)
                        except InvalidTag as exc:
                            db_Player.objects(tag=self.tag).delete()
                            db_PlayerStats.objects(tag=self.tag).delete()
                            db_WarLeaguePlayer.objects(tag=self.tag).delete()
                            raise asyncio.CancelledError from exc

                        await self.cached_player.stat_update()
                        
                except ClashAPIError as exc:
                    self.api_error = True

                except asyncio.CancelledError:
                    await self.stop()

                finally:
                    if not self.loop_active:
                        raise asyncio.CancelledError
                    
                    et = pendulum.now()
                    try:
                        run_time = et - st
                        self.run_time.append(run_time.total_seconds())
                    except:
                        pass
                    else:
                        self.main_log.debug(
                            f"{self.tag}: Player {self.cached_player} updated. Runtime: {run_time.total_seconds()} seconds."
                            )
                    await asyncio.sleep(self.sleep_time)

        except asyncio.CancelledError:
            await self.stop()

        except Exception as exc:
            self.main_log.exception(
                f"{self.tag}: FATAL PLAYER LOOP ERROR. Attempting Restart after 300 seconds. {exc}"
                )
            await self.report_fatal_error(
                message="FATAL PLAYER LOOP ERROR",
                error=exc,
                )
            self.error_loops += 1
            await self.stop()
            await asyncio.sleep(300)
            await self.start()
    
    ##################################################
    ### LOOP METRICS
    ##################################################
    @property
    def sleep_time(self):
        if self.deferred:
            if self.defer_count < 3:
                return 90
            if self.defer_count < 11:
                return 60
            if self.defer_count >= 11:
                return 20
        
        if self.api_error:
            self.api_error = False
            return 600
        
        if not self.cached_player:
            return 10
        
        if self.cached_player.is_member:
            return random.randint(60,120) #1-2min

        if self.cached_player.clan.is_alliance_clan or self.cached_player.clan.is_registered_clan or self.cached_player.clan.is_active_league_clan:
            return random.randint(60,180) #1-3min
        
        if self.cached_player.discord_user in [u.id for u in bot_client.bot.users]:
            return random.randint(180,300) #3-5min
        
        return random.randint(300,900) #5-15min