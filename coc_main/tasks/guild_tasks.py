import asyncio
import discord
import pendulum

from ..api_client import BotClashClient as client

from .default import TaskLoop
from redbot.core.utils import AsyncIter

from ..discord.guild import aGuild
from ..discord.recruiting_reminder import RecruitingReminder
from ..discord.member import aMember

bot_client = client()

class DiscordGuildLoop(TaskLoop):
    _instance = None
    _locks = {}

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
        bot_client.coc_main_log.info(f"Guild Loop started.")
        self._active = True
        await self._loop_task()
    
    def stop(self):
        self._active = False
        try:
            bot_client.coc_main_log.info(f"Guild Loop stopped.")
        except:
            pass

    @property
    def start_recruiting(self) -> bool:
        cog = bot_client.bot.get_cog('ClashOfClansTasks')
        return cog.recruiting_loop_started

    ##################################################
    ### PRIMARY TASK LOOP
    ##################################################
    @property
    def guild(self):
        return bot_client.bot.get_guild(self.guild_id)

    async def _loop_task(self):
        try:
            while self.loop_active:
                await bot_client.bot.wait_until_red_ready()

                num_guilds = len(bot_client.bot.guilds)
                sleep = (1/num_guilds)

                for guild in bot_client.bot.guilds:
                    await asyncio.sleep(sleep)
                    asyncio.create_task(self._run_single_loop(guild))

                await asyncio.sleep(10)

        except Exception as exc:
            if self.loop_active:
                bot_client.coc_main_log.exception(
                    f"{self.guild_id}: FATAL GUILD LOOP ERROR. Attempting restart. {exc}"
                    )
                await self.report_fatal_error(
                    message="FATAL GUILD LOOP ERROR",
                    error=exc,
                    )
                await self.start()
    
    async def _run_single_loop(self,guild:discord.Guild):
        try:
            locks = self._locks[guild.id]
        except KeyError:
            self._locks[guild.id] = locks = {}

        st = pendulum.now()

        tasks = [
            asyncio.create_task(self._refresh_member_cache(guild,locks)),
            asyncio.create_task(self._save_member_roles(guild,locks)),
            asyncio.create_task(self._update_clocks(guild,locks)),
            asyncio.create_task(self._update_clan_panels(guild,locks)),
            asyncio.create_task(self._update_application_panels(guild,locks)),
            asyncio.create_task(self._update_recruiting_reminder(guild,locks))
            ]
        await asyncio.gather(*tasks)

        et = pendulum.now()
        try:
            runtime = et-st
            self.run_time.append(runtime.total_seconds())
        except:
            pass
    
    async def _refresh_member_cache(self,guild:discord.Guild,locks:dict):
        try:
            lock = locks['member_cache']
        except KeyError:
            self._locks[guild.id]['member_cache'] = lock = asyncio.Lock()
        
        if lock.locked():
            return
        await lock.acquire()
        self.loop.call_later(30,self.unlock,lock)
        
        try:
            num_members = len(guild.members)
            sleep = (15/num_members)
            
            for member in guild.members:
                if member.bot:
                    continue
                await aMember(member.id,guild.id).refresh_clash_link()
                await asyncio.sleep(sleep)      
                
        except Exception as exc:
            bot_client.coc_main_log.exception(
                f"{guild.id} {guild.name}: Error refreshing Member Cache."
                )
    
    async def _save_member_roles(self,guild:discord.Guild,locks:dict):
        try:
            lock = locks['member_roles']
        except KeyError:
            self._locks[guild.id]['member_roles'] = lock = asyncio.Lock()
        
        if lock.locked():
            return
        await lock.acquire()
        self.loop.call_later(300,self.unlock,lock)
        
        try:
            num_members = len(guild.members)
            sleep = (15/num_members)
            for member in guild.members:
                if member.bot:
                    continue
                await aMember(member.id,guild.id).save_user_roles(member.id,guild.id)
                await asyncio.sleep(sleep)
                
        except Exception as exc:
            bot_client.coc_main_log.exception(
                f"{guild.id} {guild.name}: Error saving Member roles."
                )
    
    async def _update_clocks(self,guild:discord.Guild,locks:dict):
        try:
            lock = locks['clocks']
        except KeyError:
            self._locks[guild.id]['clocks'] = lock = asyncio.Lock()

        if lock.locked():
            return
        await lock.acquire()
        self.loop.call_later(300,self.unlock,lock)
        
        try:
            m_guild = aGuild(guild.id)
            await m_guild.update_clocks()

        except Exception as exc:
            bot_client.coc_main_log.exception(
                f"{guild.id} {guild.name}: Error updating Guild Clocks."
                )
    
    async def _update_clan_panels(self,guild:discord.Guild,locks:dict):
        try:
            lock = locks['clan_panels']
        except KeyError:
            self._locks[guild.id]['clan_panels'] = lock = asyncio.Lock()
        
        if lock.locked():
            return
        await lock.acquire()
        self.loop.call_later(1800,self.unlock,lock)

        try:
            m_guild = aGuild(guild.id)
            await m_guild.update_clan_panels()

        except Exception as exc:
            bot_client.coc_main_log.exception(
                f"{guild.id} {guild.name}: Error updating Guild Clan Panels."
                )
    
    async def _update_application_panels(self,guild:discord.Guild,locks:dict):
        try:
            lock = locks['application_panels']
        except KeyError:
            self._locks[guild.id]['application_panels'] = lock = asyncio.Lock()

        if lock.locked():
            return
        await lock.acquire()
        self.loop.call_later(1800,self.unlock,lock)

        try:
            m_guild = aGuild(guild.id)
            await m_guild.update_apply_panels()

        except Exception as exc:
            bot_client.coc_main_log.exception(
                f"{guild.id} {guild.name}: Error updating Guild Application Panels."
                )
    
    async def _update_recruiting_reminder(self,guild:discord.Guild,locks:dict):
        if not self.start_recruiting:
            return
        
        try:
            lock = locks['recruitment_reminders']
        except KeyError:
            self._locks[guild.id]['recruitment_reminders'] = lock = asyncio.Lock()
        
        if lock.locked():
            return
        await lock.acquire()
        self.loop.call_later(60,self.unlock,lock)
        
        try:
            posts = await RecruitingReminder.get_for_guild(guild.id)
            await asyncio.gather(*(post.send_reminder() for post in posts))

        except Exception:
            bot_client.coc_main_log.exception(
                f"{guild.id} {guild.name}: Error updating Recruiting Reminders."
                )