import asyncio
import pendulum
import copy
import coc

from typing import *
from redbot.core.utils import AsyncIter, bounded_gather

from .default import TaskLoop

from ..api_client import BotClashClient as client
from ..cog_coc_client import ClashOfClansClient
from ..exceptions import InvalidTag, ClashAPIError

from ..coc_objects.players.player import aPlayer
from ..coc_objects.clans.clan import aClan
from ..discord.member import aMember
from ..discord.feeds.donations import ClanDonationFeed
from ..discord.feeds.member_movement import ClanMemberFeed
from ..discord.clan_link import ClanGuildLink

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
    def _get_client() -> ClashOfClansClient:
        return bot_client.bot.get_cog('ClashOfClansClient')
    
    @staticmethod
    async def member_join_visitor_role(player:coc.ClanMember,clan:aClan):
        client = ClanTasks._get_client()
        n_player = await client.fetch_player(player.tag)

        if n_player.discord_user:
            clan_links = await ClanGuildLink.get_links_for_clan(clan.tag)

            if clan_links and len(clan_links) > 0:
                link_iter = AsyncIter(clan_links)
                async for link in link_iter:
                    if not link.guild:
                        continue
                    if not link.visitor_role:
                        continue
                    
                    discord_user = link.guild.get_member(n_player.discord_user)
                    if not discord_user:
                        continue

                    member = await aMember(discord_user.id,link.guild.id)
                    await member.load()

                    if clan.tag not in [c.tag for c in member.home_clans]:
                        await discord_user.add_roles(
                            link.visitor_role,
                            reason=f"Joined {clan.name}: {n_player.name} ({n_player.tag})"
                            )

    @staticmethod
    async def clan_member_join(player:coc.ClanMember,clan:aClan):    
        await ClanMemberFeed.member_join(clan,player)

    @staticmethod
    async def member_leave_visitor_role(player:coc.ClanMember,clan:aClan):
        client = ClanTasks._get_client()
        n_player = await client.fetch_player(player.tag)

        if n_player.discord_user:
            member = await aMember(n_player.discord_user)
            await member.load()

            member_accounts = await client.fetch_many_players(member.account_tags)            
            clan_links = await ClanGuildLink.get_links_for_clan(clan.tag)
            
            if clan_links and len(clan_links) > 0:
                link_iter = AsyncIter(clan_links)
                async for link in link_iter:
                    if not link.guild:
                        continue
                    if not link.visitor_role:
                        continue

                    discord_user = link.guild.get_member(n_player.discord_user)
                    if not discord_user:
                        continue
                    
                    all_clans = [a.clan for a in member_accounts if a.clan]
                    if clan.tag not in [c.tag for c in all_clans] and link.visitor_role in discord_user.roles:                    
                        await discord_user.remove_roles(
                            link.visitor_role,
                            reason=f"Left {clan.name}: {n_player.name} ({n_player.tag})"
                            )
    
    @staticmethod
    async def clan_member_leave(player:coc.ClanMember,clan:aClan):       
        await ClanMemberFeed.member_leave(clan,player)
    
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
    _instance = None

    _clan_events = [
        ClanTasks.clan_donation_change
        ]
    _member_join_events = [
        ClanTasks.clan_member_join,
        ClanTasks.member_join_visitor_role
        ]
    _member_leave_events = [
        ClanTasks.clan_member_leave,
        ClanTasks.member_leave_visitor_role
        ]

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
        bot_client.coc_main_log.info(f"Clan Loop started.")
        await super().start()
        
    async def stop(self):
        try:
            bot_client.coc_main_log.info(f"Clan Loop stopped.")
        except:
            pass
        await super().stop()
    
    async def _reload_tags(self):
        tags = []
        client = ClanTasks._get_client()

        tags.extend([clan.tag for clan in await client.get_registered_clans()])
        tags.extend([clan.tag for clan in await client.get_alliance_clans()])
        tags.extend([clan.tag for clan in await client.get_war_league_clans()])

        guild_iter = AsyncIter(bot_client.bot.guilds)
        async for guild in guild_iter:
            links = await ClanGuildLink.get_for_guild(guild.id)
            tags.extend([link.tag for link in links])

        self._tags = set(tags)
        self._last_db_update = pendulum.now()
    
    ############################################################
    ### PRIMARY TASK LOOP
    ############################################################    
    async def _loop_task(self):        
        try:
            while self.loop_active:
                if self.api_maintenance:
                    await asyncio.sleep(10)
                    continue

                if (pendulum.now() - self._last_db_update).total_seconds() > 300:
                    await self._reload_tags()

                if len(self._tags) == 0:
                    await asyncio.sleep(10)
                    continue

                c_tags = copy.copy(self._tags)
                tags = list(set(c_tags))

                st = pendulum.now()
                self._running = True
                a_iter = AsyncIter(tags)

                tasks = [self._run_single_loop(tag) async for tag in a_iter]
                await bounded_gather(*tasks,semaphore=self._loop_semaphore)

                self.last_loop = pendulum.now()
                self._running = False
                try:
                    runtime = self.last_loop - st
                    self.dispatch_time.append(runtime.total_seconds())
                except:
                    pass

                await asyncio.sleep(10)
                continue

        except Exception as exc:
            if self.loop_active:
                bot_client.coc_main_log.exception(
                    f"FATAL CLAN LOOP ERROR. Attempting restart. {exc}"
                    )
                await TaskLoop.report_fatal_error(
                    message=f"FATAL CLAN LOOP ERROR",
                    error=exc,
                    )                    
                await asyncio.sleep(60)
                await self.start()
    
    async def _run_single_loop(self,tag:str):
        try:
            finished = False
            
            lock = self._locks[tag]
            if lock.locked():
                return
            await lock.acquire()
            cached = self._cached.get(tag)       
            
            st = pendulum.now()

            async with self.api_limiter:
                new_clan = None
                try:
                    new_clan = await self.coc_client.fetch_clan(tag)
                except InvalidTag:
                    return self.loop.call_later(3600,self.unlock,lock)
                except ClashAPIError:
                    return self.loop.call_later(10,self.unlock,lock)
                            
            wait = getattr(new_clan,'_response_retry',default_sleep)
            self.loop.call_later(wait,self.unlock,lock)                
            
            self._cached[tag] = new_clan

            if cached:
                if new_clan.timestamp.int_timestamp > getattr(cached,'timestamp',pendulum.now()).int_timestamp:
                    asyncio.create_task(self._dispatch_events(cached,new_clan))
            
            finished = True
        
        except asyncio.CancelledError:
            return
                    
        except Exception as exc:
            if self.loop_active:
                bot_client.coc_main_log.exception(
                    f"CLAN LOOP ERROR: {tag}"
                    )
                await TaskLoop.report_fatal_error(
                    message=f"CLAN LOOP ERROR: {tag}",
                    error=exc,
                    )
            return self.unlock(lock)

        finally:
            if finished:
                et = pendulum.now()
                try:
                    runtime = et - st
                    self.run_time.append(runtime.total_seconds())
                except:
                    pass
    
    async def _dispatch_events(self,old_clan:aClan,new_clan:aClan):
        tasks = []
        tasks.extend([event(old_clan,new_clan) for event in ClanLoop._clan_events])

        old_member_iter = AsyncIter(old_clan.members)
        async for member in old_member_iter:
            if member.tag not in [m.tag for m in new_clan.members]:
                e_iter = AsyncIter(ClanLoop._member_leave_events)
                tasks.extend([event(member,new_clan) async for event in e_iter])

        new_member_iter = AsyncIter(new_clan.members)
        async for member in new_member_iter:
            if member.tag not in [m.tag for m in old_clan.members]:
                e_iter = AsyncIter(ClanLoop._member_join_events)
                tasks.extend([event(member,new_clan) async for event in e_iter])

        lock = self._locks['dispatch']
        async with lock:
            sem = self._task_semaphore
            while True:
                if not sem._waiters: 
                    break
                if sem._waiters and len(sem._waiters) < len(tasks):
                    break
                await asyncio.sleep(0.1)
        await bounded_gather(*tasks,semaphore=sem)