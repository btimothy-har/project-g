import asyncio
import pendulum

from .default import TaskLoop
from ..objects.discord.member import aMember
from ..objects.discord.guild import aGuild

from coc_client.api_client import BotClashClient

from ..utilities.utils import *
from ..utilities.components import *
from ..constants.coc_emojis import *

bot_client = BotClashClient()

class DiscordGuildLoop(TaskLoop):
    _loops = {}

    def __new__(cls,guild_id:int):
        if guild_id not in cls._loops:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._loops[guild_id] = instance
        return cls._loops[guild_id]

    def __init__(self,guild_id:int):
        self.guild_id = guild_id
        
        if self._is_new:
            super().__init__()
            self._is_new = False
    
    async def start(self):
        await super().start()
        self.main_log.debug(f"{self.guild_id}: Guild Loop started.")
    
    async def stop(self):
        await super().stop()
        try:
            self.main_log.debug(f"{self.guild_id}: Guild Loop stopped.")
        except:
            pass

    ##################################################
    ### PRIMARY TASK LOOP
    ##################################################
    @property
    def guild(self):
        return bot_client.bot.get_guild(self.guild_id)

    async def _loop_task(self):
        try:
            tasks = []
            tasks.append(asyncio.create_task(self._save_member_roles()))
            tasks.append(asyncio.create_task(self._update_clocks()))
            tasks.append(asyncio.create_task(self._update_clan_panels()))
            tasks.append(asyncio.create_task(self._update_application_panels()))

            await asyncio.gather(*tasks)

        except asyncio.CancelledError:
            await self.stop()

        except Exception as exc:
            self.main_log.exception(
                f"{self.guild_id}: FATAL GUILD LOOP ERROR. Attempting Restart after 600 seconds. {exc}"
                )
            await self.report_fatal_error(
                message="FATAL GUILD LOOP ERROR",
                error=exc,
                )
            self.error_loops += 1
            await self.stop()
            await asyncio.sleep(600)
            await self.start()
    
    async def _save_member_roles(self):
        while self.loop_active:
            try:
                if not self.loop_active:
                    raise asyncio.CancelledError                
                if not self.guild:
                    raise asyncio.CancelledError
                
                await asyncio.gather(*(aMember.save_user_roles(member.id,self.guild_id)
                    for member in self.guild.members if not member.bot
                    ))
            
            except asyncio.CancelledError:
                await self.stop()

            finally:
                if not self.loop_active:
                    return
                self.main_log.debug(
                    f"{self.guild_id}: Member Roles in {self.guild.name} saved."
                    )
                await asyncio.sleep(300)
    
    async def _update_clocks(self):
        while self.loop_active:
            try:
                if not self.loop_active:
                    raise asyncio.CancelledError
                
                if not self.guild:
                    raise asyncio.CancelledError
                
                await aGuild.update_clocks(self.guild_id)
            
            except asyncio.CancelledError:
                await self.stop()

            finally:
                if not self.loop_active:
                    return               
                self.main_log.debug(
                    f"{self.guild_id}: Clocks in {self.guild.name} updated."
                    )
                await asyncio.sleep(400)
    
    async def _update_clan_panels(self):
        while self.loop_active:
            try:
                if not self.loop_active:
                    raise asyncio.CancelledError                
                if not self.guild:
                    raise asyncio.CancelledError
                
                await aGuild.update_clan_panels(self.guild_id)
            
            except asyncio.CancelledError:
                await self.stop()

            finally:
                if not self.loop_active:
                    return               
                self.main_log.debug(
                    f"{self.guild_id}: Clan Panels in {self.guild.name} updated."
                    )                
                await asyncio.sleep(1800) #30minutes
    
    async def _update_application_panels(self):
        while self.loop_active:
            try:
                if not self.loop_active:
                    raise asyncio.CancelledError                
                if not self.guild:
                    raise asyncio.CancelledError
                
                await aGuild.update_apply_panels(self.guild_id)
            
            except asyncio.CancelledError:
                await self.stop()

            finally:
                if not self.loop_active:
                    return               
                self.main_log.debug(
                    f"{self.guild_id}: Application Panels in {self.guild.name} updated."
                    )                
                await asyncio.sleep(1800) #30minutes
    
    @property
    def is_degraded(self):
        if not self.loop_active:
            return False
        try:
            if sum(self.run_time) / len(self.run_time) >= 60:
                return True
            if len([i for i in self.run_time if i >= 60]) / len(self.run_time) > 0.05:
                return True
        except ZeroDivisionError:
            pass
        return False