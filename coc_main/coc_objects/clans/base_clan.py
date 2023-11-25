import coc
import discord
import asyncio
import pendulum

from typing import *
from mongoengine import *

from functools import cached_property
from async_property import AwaitLoader, AwaitableOnly, async_property, async_cached_property
from redbot.core.utils import AsyncIter
from ...api_client import BotClashClient as client
from .mongo_clan import db_Clan, db_AllianceClan, db_WarLeagueClanSetup
from ..players.mongo_player import db_Player

from ...discord.mongo_discord import db_ClanGuildLink

from ...utils.constants.coc_emojis import EmojisTownHall
from ...utils.utils import check_rtl
from ...exceptions import CacheNotReady

bot_client = client()

class BasicClan(AwaitLoader):

    @classmethod
    async def load_all(cls) -> List['BasicClan']:
        def _get_from_db():
            return [db.tag for db in db_Clan.objects.only('tag')]
        
        clan_tags = await bot_client.run_in_read_thread(_get_from_db)        
        a_iter = AsyncIter(clan_tags[:10000])
        async for tag in a_iter:
            await bot_client.clan_queue.put(tag)
            await asyncio.sleep(0.1)
    
    @classmethod
    def clear_cache(cls):
        _ClanAttributes._cache = {}
    
    """
    The BasicClan class provides a consolidated interface for inheriting clan objects.

    Access to database attributes are provided through the _ClanAttributes class.
    """
    def __init__(self,tag:str):
        self.tag = coc.utils.correct_tag(tag)
        self._attributes = _ClanAttributes(self.tag)
        # if not self._attributes._cache_loaded:
        #     def schedule_coroutine():
        #         asyncio.create_task(self.load())
        #     loop = asyncio.get_running_loop()       
        #     loop.call_soon_threadsafe(schedule_coroutine)

    def __str__(self):
        return f"Clan {self.tag}"
    
    def __hash__(self):
        return hash(self.tag)
    
    ##################################################
    #####
    ##### FORMATTERS
    #####
    ##################################################
    @property
    def title(self) -> str:
        return f"{self.emoji} {self.clean_name} ({self.tag})" if self.emoji else f"{self.clean_name} ({self.tag})"

    @property
    def clean_name(self) -> str:
        if check_rtl(self.name):
            return '\u200F' + self.name + '\u200E'
        return self.name    
    
    @property
    def share_link(self) -> Optional[str]:
        if self.tag:
            return f"https://link.clashofclans.com/en?action=OpenClanProfile&tag=%23{self.tag.strip('#')}"
        return None
    
    ##################################################
    #####
    ##### CACHED CLAN ATTRIBUTES
    #####
    ##################################################
    @async_cached_property
    async def name(self) -> str:
        return await self._attributes.name
    
    @async_cached_property
    async def badge(self) -> str:
        return await self._attributes.badge
    
    @async_cached_property
    async def level(self) -> int:
        return await self._attributes.level
    
    @async_cached_property
    async def capital_hall(self) -> int:
        return await self._attributes.capital_hall
    
    @async_cached_property
    async def war_league_name(self) -> str:
        return await self._attributes.war_league_name
    
    ##################################################
    #####
    ##### REGISTERED CLAN
    #####
    ##################################################    
    @async_cached_property
    async def is_registered_clan(self) -> bool:
        return True if len(await self.emoji) > 0 else False
    
    @async_cached_property
    async def abbreviation(self) -> str:
        return await self._attributes.abbreviation

    @async_cached_property
    async def emoji(self) -> str:
        return await self._attributes.emoji
    
    @async_cached_property
    async def unicode_emoji(self) -> str:
        return await self._attributes.unicode_emoji
    
    ##################################################
    #####
    ##### ALLIANCE CLAN
    #####
    ##################################################
    @async_cached_property
    async def is_alliance_clan(self) -> bool:
        return await self._attributes.is_alliance_clan
    
    @async_cached_property
    async def recruitment_level(self) -> List[int]:
        return await self._attributes.recruitment_level
        
    @async_cached_property
    async def max_recruitment_level(self) -> int:
        return max(await self.recruitment_level) if len(await self.recruitment_level) > 0 else 0
    
    @async_cached_property
    async def recruitment_level_emojis(self) -> str:
        return " ".join([EmojisTownHall.get(th_level) for th_level in await self.recruitment_level])

    @async_cached_property
    async def recruitment_info(self) -> str:
        return await self._attributes.recruitment_info
    
    @async_cached_property
    async def description(self) -> str:
        return await self._attributes.description
    
    @async_cached_property
    async def leader(self) -> int:
        return await self._attributes.leader
    
    @async_cached_property
    async def coleaders(self) -> List[int]:
        return await self._attributes.coleaders
    
    @async_cached_property
    async def elders(self) -> List[int]:
        return await self._attributes.elders

    @async_cached_property
    async def alliance_members(self) -> List[str]:
        return await self._attributes.alliance_members
    
    @async_cached_property
    async def alliance_member_count(self) -> int:
        return len(await self.alliance_members)
    
    ##################################################
    #####
    ##### WAR LEAGUE CLAN
    #####
    ##################################################
    @async_cached_property
    async def is_active_league_clan(self) -> bool:
        return await self._attributes.is_active_league_clan
        
    @async_property
    async def league_clan_channel(self) -> Optional[Union[discord.TextChannel,discord.Thread]]:
        if not await self.is_active_league_clan:
            return None
        channel = bot_client.bot.get_channel(await self._attributes.league_clan_channel_id)
        if isinstance(channel,(discord.TextChannel,discord.Thread)):
            return channel
        return None
    
    @async_property
    async def league_clan_role_id(self) -> Optional[discord.Role]:
        if not await self.is_active_league_clan:
            return None
        role_id = await self._attributes.league_clan_role_id
        for guild in bot_client.bot.guilds:
            role = guild.get_role(role_id)
            if isinstance(role,discord.Role):
                return role
        return None
    
    ##################################################
    #####
    ##### CLAN FUNCTIONS
    #####
    ##################################################
    async def new_member(self,player_tag:str):
        async with self._attributes._lock:
            if player_tag not in self.alliance_members:
                self._attributes.alliance_members.append(player_tag)
    
    async def remove_member(self,player_tag:str):
        async with self._attributes._lock:
            if player_tag in self.alliance_members:
                self._attributes.alliance_members.remove(player_tag)

    async def register(self,abbreviation:str,emoji:str,unicode_emoji:str):
        def _update_in_db():
            db_Clan.objects(tag=self.tag).update_one(
                set__abbreviation=self.abbreviation,
                upsert=True
                )
            db_Clan.objects(tag=self.tag).update_one(
                set__emoji=self.emoji,
                upsert=True
                )
            db_Clan.objects(tag=self.tag).update_one(
                set__unicode_emoji=self.unicode_emoji,
                upsert=True
                )

            bot_client.coc_data_log.info(
                f"{self}: Clan Registered!"
                + f"\n\tAbbreviation: {self.abbreviation}"
                + f"\n\tEmoji: {self.emoji}"
                + f"\n\tUnicode Emoji: {self.unicode_emoji}"
                )
        
        async with self._attributes._lock:    
            self._attributes.abbreviation = abbreviation.upper()
            self._attributes.emoji = emoji
            self._attributes.unicode_emoji = unicode_emoji
            await bot_client.run_in_write_thread(_update_in_db)
    
    async def add_to_war_league(self,channel:Union[discord.TextChannel,discord.Thread],role:discord.Role):
        def _update_in_db():
            db_WarLeagueClanSetup.objects(tag=self.tag).update_one(
                set__channel=getattr(self.league_clan_channel,'id',0),
                upsert=True
                )
            db_WarLeagueClanSetup.objects(tag=self.tag).update_one(
                set__role=getattr(self.league_clan_role,'id',0),
                upsert=True
                )
            db_WarLeagueClanSetup.objects(tag=self.tag).update_one(
                set__is_active=self.is_active_league_clan,
                upsert=True
                )
            
            ch_guild = self.league_clan_channel.guild if self.league_clan_channel else None
            rl_guild = self.league_clan_role.guild if self.league_clan_role else None

            bot_client.coc_data_log.info(
                f"{self}: Registered as CWL Clan."
                + f"\n\tChannel: {getattr(ch_guild,'name',None)} {getattr(self.league_clan_channel,'name',None)} ({self._attributes.league_clan_channel_id})"
                + f"\n\tRole: {getattr(rl_guild,'name',None)} {getattr(self.league_clan_role,'name',None)} ({self._attributes.league_clan_role_id})"
                )
        
        async with self._attributes._lock:
            self._attributes.league_clan_channel_id = channel.id
            self._attributes.league_clan_role_id = role.id
            self._attributes.is_active_league_clan = True
            await bot_client.run_in_write_thread(_update_in_db)
    
    async def remove_from_war_league(self):
        def _update_in_db():
            db_WarLeagueClanSetup.objects(tag=self.tag).update_one(
                set__is_active=self.is_active_league_clan,
                upsert=True
                )
            bot_client.coc_data_log.info(f"{self}: Removed as CWL Clan.")
        
        async with self._attributes._lock:
            self._attributes.league_clan_channel_id = 0
            self._attributes.league_clan_role_id = 0
            self._attributes.is_active_league_clan = False
            await bot_client.run_in_write_thread(_update_in_db)

    async def new_leader(self,new_leader:int):
        def _update_in_db():
            db_AllianceClan.objects(tag=self.tag).update_one(
                set__leader=self.leader,
                set__coleaders=self.coleaders,
                set__elders=self.elders,
                upsert=True
                )
            bot_client.coc_data_log.info(f"{self}: leader is now {new_leader}.")

        if new_leader == self.leader:
            return
        
        async with self._attributes._lock:
            #demote current Leader to Co-Leader
            if self.leader not in self.coleaders:
                self._attributes.coleaders.append(self.leader)

            self._attributes.leader = new_leader

            if new_leader in self.coleaders:
                self._attributes.coleaders.remove(new_leader)

            if new_leader in self.elders:
                self._attributes.elders.remove(new_leader)

            await bot_client.run_in_write_thread(_update_in_db)
    
    async def new_coleader(self,new_coleader:int):
        def _update_in_db():
            db_AllianceClan.objects(tag=self.tag).update_one(
                set__coleaders=self.coleaders,
                set__elders=self.elders,
                upsert=False
                )
            bot_client.coc_data_log.info(f"{self}: new coleader {new_coleader} added.")

        if new_coleader == self.leader:
            return
        
        async with self._attributes._lock:
            if new_coleader not in self.coleaders:
                self._attributes.coleaders.append(new_coleader)
            
            if new_coleader in self.elders:
                self._attributes.elders.remove(new_coleader)

            await bot_client.run_in_write_thread(_update_in_db)
    
    async def remove_coleader(self,coleader:int):
        def _update_in_db():
            db_AllianceClan.objects(tag=self.tag).update_one(
                set__coleaders=self.coleaders,
                upsert=False
                )
            bot_client.coc_data_log.info(f"{self}: coleader {coleader} removed.")

        async with self._attributes._lock:
            if coleader in self.coleaders:
                self._attributes.coleaders.remove(coleader)
                await bot_client.run_in_write_thread(_update_in_db)
    
    async def new_elder(self,new_elder:int):
        def _update_in_db():
            db_AllianceClan.objects(tag=self.tag).update_one(
                set__coleaders=self.coleaders,
                set__elders=self.elders,
                upsert=False
                )
            bot_client.coc_data_log.info(f"{self}: new elder {new_elder} added.")

        if new_elder == self.leader:
            return
        
        async with self._attributes._lock:
            if new_elder not in self.elders:
                self._attributes.elders.append(new_elder)

            if new_elder in self.coleaders:
                self._attributes.coleaders.remove(new_elder)
            
            await bot_client.run_in_write_thread(_update_in_db)

    async def remove_elder(self,elder:int):
        def _update_in_db():
            db_AllianceClan.objects(tag=self.tag).update_one(
                set__elders=self.elders,
                upsert=False
                )
            bot_client.coc_data_log.info(f"{self}: elder {elder} removed.")

        async with self._attributes._lock:
            if elder in self.elders:
                self._attributes.elders.remove(elder)
                await bot_client.run_in_write_thread(_update_in_db)
        
    ##################################################
    #####
    ##### DATABASE INTERACTIONS
    #####
    ##################################################
    async def set_name(self,new_name:str):
        # def _update_in_db():
        #     db_Clan.objects(tag=self.tag).update_one(
        #         set__name=self.name,
        #         upsert=True
        #         )
        #     bot_client.coc_data_log.debug(f"{self}: name changed to {self.name}.")
        
        async with self._attributes._lock:
            self.name = self._attributes.name = new_name
            await bot_client.coc_db.db__clan.update_one(
                {'_id':self.tag},
                {'$set':{'name':await self.name}},
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: name changed to {self.name}.")

    async def set_badge(self,new_badge:str):
        # def _update_in_db():
        #     db_Clan.objects(tag=self.tag).update_one(
        #         set__badge=self.badge,
        #         upsert=True
        #         )
        #     bot_client.coc_data_log.debug(f"{self}: badge changed to {self.badge}.")
        
        async with self._attributes._lock:
            self.badge = self._attributes.badge = new_badge
            await bot_client.coc_db.db__clan.update_one(
                {'_id':self.tag},
                {'$set':{'badge':await self.badge}},
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: badge changed to {self.badge}.")
    
    async def set_level(self,new_level:int):
        # def _update_in_db():
        #     db_Clan.objects(tag=self.tag).update_one(
        #         set__level=self.level,
        #         upsert=True
        #         )
        #     bot_client.coc_data_log.debug(f"{self}: level changed to {self.level}.")
        
        async with self._attributes._lock:
            self.level = self._attributes.level = new_level
            await bot_client.coc_db.db__clan.update_one(
                {'_id':self.tag},
                {'$set':{'level':await self.level}},
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: level changed to {self.level}.")
    
    async def set_capital_hall(self,new_capital_hall:int):
        # def _update_in_db():
        #     db_Clan.objects(tag=self.tag).update_one(
        #         set__capital_hall=self.capital_hall,
        #         upsert=True
        #         )
        #     bot_client.coc_data_log.debug(f"{self}: capital_hall changed to {self.capital_hall}.")
        
        async with self._attributes._lock:
            self.capital_hall = self._attributes.capital_hall = new_capital_hall
            await bot_client.coc_db.db__clan.update_one(
                {'_id':self.tag},
                {'$set':{'capital_hall':await self.capital_hall}},
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: capital_hall changed to {self.capital_hall}.")
    
    async def set_war_league(self,new_war_league:str):
        # def _update_in_db():
        #     db_Clan.objects(tag=self.tag).update_one(
        #         set__war_league=self.war_league_name,
        #         upsert=True
        #         )
        #     bot_client.coc_data_log.debug(f"{self}: war_league changed to {self.war_league_name}.")
        
        async with self._attributes._lock:
            self.war_league = self._attributes.war_league_name = new_war_league
            await bot_client.coc_db.db__clan.update_one(
                {'_id':self.tag},
                {'$set':{'war_league':await self.war_league}},
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: war_league changed to {self.war_league_name}.")
        
    async def set_description(self,description:str):
        def _update_in_db():
            db_AllianceClan.objects(tag=self.tag).update_one(
                set__description=self.description,
                upsert=False
                )
            bot_client.coc_data_log.info(f"{self}: description changed to {self.description}.")
        
        async with self._attributes._lock:
            self._attributes.description = description
            await bot_client.run_in_write_thread(_update_in_db)
    
    async def set_recruitment_level(self,recruitment_levels:list[int]):
        def _update_in_db():
            db_AllianceClan.objects(tag=self.tag).update_one(
                set__recruitment_level=self.recruitment_level,
                upsert=False
                )
            bot_client.coc_data_log.info(f"{self}: recruitment_level changed to {sorted(self.recruitment_level)}.")

        async with self._attributes._lock:
            self._attributes.recruitment_level = sorted(list(set(recruitment_levels)))
            await bot_client.run_in_write_thread(_update_in_db)
    
    async def set_recruitment_info(self,new_recruitment_info:str):
        def _update_in_db():
            db_AllianceClan.objects(tag=self.tag).update_one(
                set__recruitment_info=self.recruitment_info,
                upsert=False
                )
            bot_client.coc_data_log.info(f"{self}: recruitment info changed to {self.recruitment_info}.")
        
        async with self._attributes._lock:
            self._attributes.recruitment_info = new_recruitment_info
            await bot_client.run_in_write_thread(_update_in_db)
    
    ##################################################
    #####
    ##### DISCORD FEEDS
    #####
    ##################################################
    @property
    def linked_servers(self) -> List[discord.Guild]:
        return [bot_client.bot.get_guild(db.guild_id) for db in db_ClanGuildLink.objects(tag=self.tag)]

class _ClanAttributes():
    """
    This class enforces a singleton pattern that caches database responses.

    This class DOES NOT handle database updates - those are handled within the BasicClan class.
    """
    _cache = {}

    def __new__(cls,tag:str):
        n_tag = coc.utils.correct_tag(tag)
        if n_tag not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[n_tag] = instance
        return cls._cache[n_tag]
    
    def __init__(self,tag:str):
        if self._is_new:
            self.tag = coc.utils.correct_tag(tag)
            self._lock = asyncio.Lock()
            self._cache_loaded = False            
            self._cached_db = None
            self._last_db_query = None

            bot_client.clan_queue.add(self.tag)
            
        self._is_new = False

    ##################################################
    #####
    ##### DATABASES
    #####
    ##################################################
    @async_property
    async def _database(self) -> Optional[dict]:
        if not self.tag:
            return None
        def _get_from_db():
            try:
                return db_Clan.objects.get(tag=self.tag)
            except DoesNotExist:
                return None
        if not self._cached_db or (pendulum.now() - self._last_db_query).total_seconds() > 60:
            self._cached_db = await bot_client.coc_db.db__clan.find_one({'_id':self.tag})
            self._last_db_query = pendulum.now()
        return self._cached_db
        
    @async_property
    async def _db_alliance(self) -> Optional[dict]:
        if not self.tag:
            return None
        def _get_from_db():
            try:
                return db_AllianceClan.objects.get(tag=self.tag)
            except DoesNotExist:
                return None
        return await bot_client.coc_db.db__allianceclan.find_one({'_id':self.tag})
    
    @async_property
    async def _league_clan(self) -> Optional[dict]:
        if not self.tag:
            return None
        def _get_from_db():
            try:
                return db_WarLeagueClanSetup.objects.get(tag=self.tag)
            except DoesNotExist:
                return None
        return await bot_client.coc_db.db__warleagueclansetup.find_one({'_id':self.tag})
    
    ##################################################
    #####
    ##### CLAN ATTRIBUTES
    #####
    ##################################################
    @async_cached_property
    async def name(self) -> str:
        db = await self._database
        return db.get('name','') if db else ''
    
    @async_cached_property
    async def badge(self) -> str:
        db = await self._database
        return db.get('badge','') if db else ''
    
    @async_cached_property
    async def level(self) -> int:
        db = await self._database
        return db.get('level',0) if db else 0
    
    @async_cached_property
    async def capital_hall(self) -> int:
        db = await self._database
        return db.get('capital_hall',0) if db else 0
    
    @async_cached_property
    async def war_league_name(self) -> str:
        db = await self._database
        return db.get('war_league','') if db else ''
    
    ##################################################
    #####
    ##### REGISTERED CLAN
    #####
    ##################################################
    @async_cached_property
    async def abbreviation(self) -> str:
        db = await self._database
        return db.get('abbreviation','') if db else ''

    @async_cached_property
    async def emoji(self) -> str:
        db = await self._database
        return db.get('emoji','') if db else ''
    
    @async_cached_property
    async def unicode_emoji(self) -> str:
        db = await self._database
        return db.get('unicode_emoji','') if db else ''
    
    ##################################################
    #####
    ##### ALLIANCE CLAN
    #####
    ##################################################
    @async_cached_property
    async def is_alliance_clan(self) -> bool:
        db = await self._db_alliance
        if db:
            return True
        return False
    
    @async_cached_property
    async def recruitment_level(self) -> List[int]:
        db = await self._db_alliance
        i = db.get('recruitment_level',[]) if db else []
        return sorted(i)

    @async_cached_property
    async def recruitment_info(self) -> str:
        db = await self._db_alliance
        return db.get('recruitment_info','') if db else ''
    
    @async_cached_property
    async def description(self) -> str:
        db = await self._db_alliance
        return db.get('description','') if db else ''
    
    @async_cached_property
    async def leader(self) -> int:
        db = await self._db_alliance
        return db.get('leader',0) if db else 0
    
    @async_cached_property
    async def coleaders(self) -> List[int]:
        db = await self._db_alliance
        i = db.get('coleaders',[]) if db else []
        return list(set(i))
    
    @async_cached_property
    async def elders(self) -> List[int]:
        db = await self._db_alliance
        i = db.get('elders',[]) if db else []
        return list(set(i))

    @async_cached_property
    async def alliance_members(self) -> List[str]:
        def _get_from_db():
            return [p.tag for p in db_Player.objects(is_member=True,home_clan=self.tag)]
        query = bot_client.coc_db.db__clan.find({'is_member':True,'home_clan':self.tag},{'_id':1})
        return [p['_id'] async for p in query]
    
    ##################################################
    #####
    ##### WAR LEAGUE CLAN
    #####
    ##################################################
    @async_cached_property
    async def is_active_league_clan(self) -> bool:
        db = await self._league_clan
        return db.get('is_active',False) if db else False
    
    @async_cached_property
    async def league_clan_channel_id(self) -> int:
        if not await self.is_active_league_clan:
            return 0
        db = await self._league_clan
        return db.get('channel',0) if db else 0
    
    @async_cached_property
    async def league_clan_role_id(self) -> int:
        if not await self.is_active_league_clan:
            return 0
        db = await self._league_clan
        return db.get('role',0) if db else 0