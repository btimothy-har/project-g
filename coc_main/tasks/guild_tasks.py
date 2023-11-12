import asyncio

from ..api_client import BotClashClient as client

from .default import TaskLoop
from redbot.core.utils import AsyncIter

from ..discord.guild import aGuild
from ..discord.recruiting_reminder import RecruitingReminder
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
            self._member_lock = asyncio.Lock()
            self._cache_lock = asyncio.Lock()
            self._clock_lock = asyncio.Lock()
            self._clan_panel_lock = asyncio.Lock()
            self._application_panel_lock = asyncio.Lock()
            self._recruit_reminder_lock = asyncio.Lock()        
        self._is_new = False
    
    async def start(self):
        await super().start()
        bot_client.coc_main_log.debug(f"{self.guild_id}: Guild Loop started.")
    
    async def stop(self):
        await super().stop()
        try:
            bot_client.coc_main_log.debug(f"{self.guild_id}: Guild Loop stopped.")
        except:
            pass

    ##################################################
    ### PRIMARY TASK LOOP
    ##################################################
    @property
    def guild(self):
        return bot_client.bot.get_guild(self.guild_id)
    
    @property
    def start_recruiting(self) -> bool:
        cog = bot_client.bot.get_cog('ClashOfClansTasks')
        return cog.recruiting_loop_started

    async def _loop_task(self):
        try:
            while self.loop_active:
                await asyncio.sleep(10)

                tasks = [
                    asyncio.create_task(self._refresh_member_cache()),
                    asyncio.create_task(self._save_member_roles()),
                    asyncio.create_task(self._update_clocks()),
                    asyncio.create_task(self._update_clan_panels()),
                    asyncio.create_task(self._update_application_panels()),
                    asyncio.create_task(self._update_recruiting_reminder())
                    ]
                await asyncio.gather(*tasks)

        except asyncio.CancelledError:
            await self.stop()

        except Exception as exc:            
            bot_client.coc_main_log.exception(
                f"{self.guild_id}: FATAL GUILD LOOP ERROR. Attempting Restart after 600 seconds. {exc}"
                )
            await self.report_fatal_error(
                message="FATAL GUILD LOOP ERROR",
                error=exc,
                )
            await self.stop()
            return await self.start()
    
    async def _refresh_member_cache(self):
        if not self.guild:
            return
        if self._cache_lock.locked():
            return
        
        await self._cache_lock.acquire()
        self.loop.call_later(30,self.unlock,self._cache_lock)
        
        try:
            await asyncio.gather(*(aMember(member.id,self.guild_id).refresh_clash_link()
                for member in self.guild.members if not member.bot
                ))            
                
        except Exception as exc:
            bot_client.coc_main_log.exception(
                f"{self.guild_id}: Error refreshing Member Cache."
                )
    
    async def _save_member_roles(self):
        if not self.guild:
            return
        if self._member_lock.locked():
            return
        
        await self._member_lock.acquire()
        self.loop.call_later(300,self.unlock,self._member_lock)
        
        try:
            await asyncio.gather(*(aMember.save_user_roles(member.id,self.guild_id)
                for member in self.guild.members if not member.bot
                ))
        except Exception as exc:
            bot_client.coc_main_log.exception(
                f"{self.guild_id}: Error saving Member roles."
                )
    
    async def _update_clocks(self):
        if not self.guild:
            return
        if self._clock_lock.locked():
            return
        
        await self._clock_lock.acquire()
        self.loop.call_later(300,self.unlock,self._clock_lock)
        
        try:
            guild = aGuild(self.guild_id)
            await guild.update_clocks()

        except Exception as exc:
            bot_client.coc_main_log.exception(
                f"{self.guild_id}: Error updating Guild Clocks."
                )
    
    async def _update_clan_panels(self):
        if not self.guild:
            return
        if self._clan_panel_lock.locked():
            return
        
        await self._clan_panel_lock.acquire()
        self.loop.call_later(1800,self.unlock,self._clan_panel_lock)

        try:
            guild = aGuild(self.guild_id)
            await guild.update_clan_panels()

        except Exception as exc:
            bot_client.coc_main_log.exception(
                f"{self.guild_id}: Error updating Guild Clan Panels."
                )
    
    async def _update_application_panels(self):
        if not self.guild:
            return
        if self._application_panel_lock.locked():
            return
        
        await self._application_panel_lock.acquire()
        self.loop.call_later(1800,self.unlock,self._application_panel_lock)
        
        try:       
            guild = aGuild(self.guild_id)
            await guild.update_apply_panels()

        except Exception as exc:
            bot_client.coc_main_log.exception(
                f"{self.guild_id}: Error updating Guild Application Panels."
                )
    
    async def _update_recruiting_reminder(self):
        if not self.guild:
            return
        if not self.start_recruiting:
            return
        if self._recruit_reminder_lock.locked():
            return
        
        await self._recruit_reminder_lock.acquire()
        self.loop.call_later(60,self.unlock,self._recruit_reminder_lock)
        
        try:
            async with self._recruit_reminder_lock:
                posts = await RecruitingReminder.get_for_guild(self.guild_id)
                await asyncio.gather(*(post.send_reminder() for post in posts))

        except Exception:
            bot_client.coc_main_log.exception(
                f"{self.guild_id}: Error updating Recruiting Reminders."
                )