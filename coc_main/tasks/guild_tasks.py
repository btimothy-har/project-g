import asyncio

from ..api_client import BotClashClient as client

from .default import TaskLoop

from ..discord.guild import aGuild
from ..discord.member import aMember

bot_client = client()

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
                
                guild = aGuild(self.guild_id)
                await guild.update_clocks()
            
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
                
                guild = aGuild(self.guild_id)
                await guild.update_clan_panels()
            
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
                
                guild = aGuild(self.guild_id)
                await guild.update_apply_panels()
            
            except asyncio.CancelledError:
                await self.stop()

            finally:
                if not self.loop_active:
                    return               
                self.main_log.debug(
                    f"{self.guild_id}: Application Panels in {self.guild.name} updated."
                    )                
                await asyncio.sleep(1800) #30minutes