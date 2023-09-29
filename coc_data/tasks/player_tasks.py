import coc
import asyncio
import pendulum
import random

from .default import TaskLoop
from ..exceptions import *

from ..objects.players.player_attributes import db_Player
from ..objects.players.player_season import db_PlayerStats
from ..objects.events.clan_war_leagues import db_WarLeaguePlayer

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
            await self._single_loop()

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

                    if not self.loop_active:
                        return

                    try:
                        self.cached_player = await self.client.cog.fetch_player(self.tag,no_cache=True)
                    except InvalidTag as exc:
                        db_Player.objects(tag=self.tag).delete()
                        db_PlayerStats.objects(tag=self.tag).delete()
                        db_WarLeaguePlayer.objects(tag=self.tag).delete()
                        raise asyncio.CancelledError from exc

                    api_end = pendulum.now()
                    
                    await self.cached_player.stat_update()
                    
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
                    f"{self.tag}: Player {self.cached_player} updated. Runtime: {run_time} seconds."
                    )
                await asyncio.sleep(self.sleep_time)
    
    ##################################################
    ### LOOP METRICS
    ##################################################
    @property
    def sleep_time(self):
        if not self.cached_player:
            sleep = 300
        elif self.api_error:
            sleep = 600
            self.api_error = False
        elif self.cached_player.is_member:
            sleep = 60
        elif self.cached_player.clan.is_alliance_clan or self.cached_player.clan.is_registered_clan or self.cached_player.clan.cwl_config.is_cwl_clan:
            sleep = 60
        elif self.cached_player.discord_user in [u.id for u in self.bot.users]:
            sleep = 120
        else:
            sleep = 180
        return sleep