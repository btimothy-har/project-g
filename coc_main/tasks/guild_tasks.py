import asyncio
import discord
import pendulum

from ..api_client import BotClashClient as client

from .default import TaskLoop
from redbot.core.utils import AsyncIter,bounded_gather

from ..discord.guild import aGuild
from ..discord.recruiting_reminder import RecruitingReminder
from ..discord.member import aMember

bot_client = client()

class DiscordGuildLoop(TaskLoop):
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._is_new = True
        return cls._instance

    def __init__(self):        
        if self._is_new:
            super().__init__()
            self._is_new = False
            self._locks = {}
    
    async def start(self):
        bot_client.coc_main_log.info(f"Guild Loop started.")
        await super().start()
    
    async def stop(self):
        try:
            bot_client.coc_main_log.info(f"Guild Loop stopped.")
        except:
            pass
        await super().stop()

    @property
    def start_recruiting(self) -> bool:
        try:
            cog = bot_client.bot.get_cog('ClashOfClansTasks')
            return cog.recruiting_loop_started
        except:
            return False

    ##################################################
    ### PRIMARY TASK LOOP
    ##################################################
    async def _loop_task(self):
        try:
            while self.loop_active:
                await bot_client.bot.wait_until_red_ready()

                st = pendulum.now()
                self._running = True
                a_iter = AsyncIter(bot_client.bot.guilds)

                tasks = [self._run_single_loop(guild) async for guild in a_iter]
                await asyncio.gather(*tasks)
                                     
                self.last_loop = pendulum.now()
                self._running = False
                
                try:
                    runtime = self.last_loop-st
                    self.dispatch_time.append(runtime.total_seconds())
                except:
                    pass

                await asyncio.sleep(10)
                continue

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
        
        tasks = [
            self._save_member_roles(guild,locks),
            self._update_clocks(guild,locks),
            self._update_clan_panels(guild,locks),
            self._update_application_panels(guild,locks),
            self._update_recruiting_reminder(guild,locks)
            ]
        await bounded_gather(*tasks,semaphore=self._loop_semaphore)
    
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
            a_iter = AsyncIter(guild.members)
            tasks = [aMember.save_user_roles(member.id,guild.id) async for member in a_iter if not member.bot]
            await bounded_gather(*tasks,semaphore=self._task_semaphore)
                
        except Exception:
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

        except Exception:
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

        except Exception:
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

        except Exception:
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
            
            a_iter = AsyncIter(posts)
            tasks = [post.send_reminder() async for post in a_iter]
            await bounded_gather(*tasks,semaphore=self._task_semaphore) 

        except Exception:
            bot_client.coc_main_log.exception(
                f"{guild.id} {guild.name}: Error updating Recruiting Reminders."
                )