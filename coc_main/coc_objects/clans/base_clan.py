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
        query = bot_client.coc_db.db__clan.find({},{'_id':1})
        async for c in query:
            clan = await cls(c['_id'])
            await bot_client.clan_queue.put(clan.tag)
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
    async def league_clan_role(self) -> Optional[discord.Role]:
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
            members = await self.alliance_members
            if player_tag not in members:
                members.append(player_tag)
                self.alliance_members = self._attributes.alliance_members = members
    
    async def remove_member(self,player_tag:str):
        async with self._attributes._lock:
            if player_tag in self.alliance_members:
                self._attributes.alliance_members.remove(player_tag)

    async def register(self,abbreviation:str,emoji:str,unicode_emoji:str):
        async with self._attributes._lock:    
            self.abbreviation = self._attributes.abbreviation = abbreviation.upper()
            self.emoji = self._attributes.emoji = emoji
            self.unicode_emoji = self._attributes.unicode_emoji = unicode_emoji

            await bot_client.coc_db.db__clan.update_one(
                {'_id':self.tag},
                {'$set':{
                    'abbreviation':await self.abbreviation,
                    'emoji':await self.emoji,
                    'unicode_emoji':await self.unicode_emoji
                    }
                },
                upsert=True)
            
            bot_client.coc_data_log.info(
                f"{self}: Clan Registered!"
                + f"\n\tAbbreviation: {await self.abbreviation}"
                + f"\n\tEmoji: {await self.emoji}"
                + f"\n\tUnicode Emoji: {await self.unicode_emoji}"
                )
    
    async def add_to_war_league(self,channel:Union[discord.TextChannel,discord.Thread],role:discord.Role):        
        async with self._attributes._lock:
            self._attributes.league_clan_channel_id = channel.id
            self._attributes.league_clan_role_id = role.id
            self.is_active_league_clan = self._attributes.is_active_league_clan = True

            await bot_client.coc_db.db__war_league_clan_setup.update_one(
                {'_id':self.tag},
                {'$set':{
                    'channel':getattr(await self.league_clan_channel,'id',None),
                    'role':getattr(await self.league_clan_role,'id',None),
                    'is_active':await self.is_active_league_clan
                    }
                },
                upsert=True)
            bot_client.coc_data_log.info(
                f"{self}: Registered as CWL Clan."
                + f"\n\tChannel: {getattr(await self.league_clan_channel,'id',None)}"
                + f"\n\tRole: {getattr(await self.league_clan_role,'id',None)}"
                )
    
    async def remove_from_war_league(self):        
        async with self._attributes._lock:
            self._attributes.league_clan_channel_id = 0
            self._attributes.league_clan_role_id = 0
            self.is_active_league_clan = self._attributes.is_active_league_clan = False

            await bot_client.coc_db.db__war_league_clan_setup.update_one(
                {'_id':self.tag},
                {'$set':{
                    'is_active':await self.is_active_league_clan
                    }
                },
                upsert=True)

    async def new_leader(self,new_leader:int):
        leader = await self.leader
        if new_leader == leader:
            return
        
        async with self._attributes._lock:
            coleaders = await self.coleaders
            elders = await self.elders
            
            #demote current Leader to Co-Leader
            if leader not in coleaders:
                coleaders.append(leader)
                self.coleaders = self._attributes.coleaders = coleaders

            self.leader = self._attributes.leader = new_leader

            if new_leader in coleaders:
                coleaders.remove(new_leader)
                self.coleaders = self._attributes.coleaders = coleaders

            if new_leader in elders:
                elders.remove(new_leader)
                self.elders = self._attributes.elders = elders
            
            await bot_client.coc_db.db__alliance_clan.update_one(
                {'_id':self.tag},
                {'$set':{
                    'leader':await self.leader,
                    'coleaders':await self.coleaders,
                    'elders':await self.elders
                    }
                },
                upsert=True)
            bot_client.coc_data_log.info(f"{self}: leader is now {new_leader}.")
    
    async def new_coleader(self,new_coleader:int):
        leader = await self.leader
        if new_coleader == leader:
            return
               
        async with self._attributes._lock:
            coleaders = await self.coleaders 
            elders = await self.elders

            if new_coleader not in coleaders:
                coleaders.append(new_coleader)
                self.coleaders = self._attributes.coleaders = coleaders
            
            if new_coleader in elders:
                elders.remove(new_coleader)
                self.elders = self._attributes.elders = elders

            await bot_client.coc_db.db__alliance_clan.update_one(
                {'_id':self.tag},
                {'$set':{
                    'coleaders':await self.coleaders,
                    'elders':await self.elders
                    }
                },
                upsert=True)
            bot_client.coc_data_log.info(f"{self}: new coleader {new_coleader} added.")
    
    async def remove_coleader(self,coleader:int):
        async with self._attributes._lock:
            coleaders = await self.coleaders

            if coleader in coleaders:
                coleaders.remove(coleader)
                self.coleaders = self._attributes.coleaders = coleaders
            
            await bot_client.coc_db.db__alliance_clan.update_one(
                {'_id':self.tag},
                {'$set':{
                    'coleaders':await self.coleaders
                    }
                },
                upsert=True)
            bot_client.coc_data_log.info(f"{self}: coleader {coleader} removed.")                
    
    async def new_elder(self,new_elder:int):
        leader = await self.leader
        if new_elder == leader:
            return
        
        async with self._attributes._lock:
            coleaders = await self.coleaders
            elders = await self.elders

            if new_elder not in elders:
                elders.append(new_elder)
                self.elders = self._attributes.elders = elders

            if new_elder in coleaders:
                coleaders.remove(new_elder)
                self.coleaders = self._attributes.coleaders = coleaders
            
            await bot_client.coc_db.db__alliance_clan.update_one(
                {'_id':self.tag},
                {'$set':{
                    'coleaders':await self.coleaders,
                    'elders':await self.coleaders
                    }
                },
                upsert=True)
            bot_client.coc_data_log.info(f"{self}: new elder {new_elder} added.")
            
    async def remove_elder(self,elder:int):
        async with self._attributes._lock:
            elders = await self.elders

            if elder in elders:
                elders.remove(elder)
                self.elders = self._attributes.elders = elders
            
            await bot_client.coc_db.db__alliance_clan.update_one(
                {'_id':self.tag},
                {'$set':{
                    'elders':await self.coleaders
                    }
                },
                upsert=True)
            bot_client.coc_data_log.info(f"{self}: elder {elder} removed.")
        
    ##################################################
    #####
    ##### DATABASE INTERACTIONS
    #####
    ##################################################
    async def set_name(self,new_name:str):        
        async with self._attributes._lock:
            self.name = self._attributes.name = new_name
            await bot_client.coc_db.db__clan.update_one(
                {'_id':self.tag},
                {'$set':{'name':await self.name}},
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: name changed to {await self.name}.")

    async def set_badge(self,new_badge:str):        
        async with self._attributes._lock:
            self.badge = self._attributes.badge = new_badge
            await bot_client.coc_db.db__clan.update_one(
                {'_id':self.tag},
                {'$set':{'badge':await self.badge}},
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: badge changed to {await self.badge}.")
    
    async def set_level(self,new_level:int):        
        async with self._attributes._lock:
            self.level = self._attributes.level = new_level
            await bot_client.coc_db.db__clan.update_one(
                {'_id':self.tag},
                {'$set':{'level':await self.level}},
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: level changed to {await self.level}.")
    
    async def set_capital_hall(self,new_capital_hall:int):        
        async with self._attributes._lock:
            self.capital_hall = self._attributes.capital_hall = new_capital_hall
            await bot_client.coc_db.db__clan.update_one(
                {'_id':self.tag},
                {'$set':{'capital_hall':await self.capital_hall}},
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: capital_hall changed to {await self.capital_hall}.")
    
    async def set_war_league(self,new_war_league:str):
        async with self._attributes._lock:
            self.war_league = self._attributes.war_league_name = new_war_league
            await bot_client.coc_db.db__clan.update_one(
                {'_id':self.tag},
                {'$set':{'war_league':await self.war_league}},
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: war_league changed to {await self.war_league_name}.")
        
    async def set_description(self,description:str):
        async with self._attributes._lock:
            self.description = self._attributes.description = description
            await bot_client.coc_db.db__alliance_clan.update_one(
                {'_id':self.tag},
                {'$set':{
                    'description':await self.description
                    }
                },
                upsert=True)
            bot_client.coc_data_log.info(f"{self}: description changed to {await self.description}.")
    
    async def set_recruitment_level(self,recruitment_levels:list[int]):
        async with self._attributes._lock:
            self.recruitment_level = self._attributes.recruitment_level = sorted(list(set(recruitment_levels)))
            await bot_client.coc_db.db__alliance_clan.update_one(
                {'_id':self.tag},
                {'$set':{
                    'recruitment_level':await self.recruitment_level
                    }
                },
                upsert=True)
            bot_client.coc_data_log.info(f"{self}: recruitment_level changed to {sorted(await self.recruitment_level)}.")
    
    async def set_recruitment_info(self,new_recruitment_info:str):        
        async with self._attributes._lock:
            self.recruitment_info = self._attributes.recruitment_info = new_recruitment_info
            await bot_client.coc_db.db__alliance_clan.update_one(
                {'_id':self.tag},
                {'$set':{
                    'recruitment_info':await self.recruitment_info
                    }
                },
                upsert=True)
            bot_client.coc_data_log.info(f"{self}: recruitment info changed to {await self.recruitment_info}.")

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
        if not self._cached_db or (pendulum.now() - self._last_db_query).total_seconds() > 60:
            self._cached_db = await bot_client.coc_db.db__clan.find_one({'_id':self.tag})
            self._last_db_query = pendulum.now()
        return self._cached_db
        
    @async_property
    async def _db_alliance(self) -> Optional[dict]:
        if not self.tag:
            return None
        return await bot_client.coc_db.db__alliance_clan.find_one({'_id':self.tag})
    
    @async_property
    async def _league_clan(self) -> Optional[dict]:
        if not self.tag:
            return None
        return await bot_client.coc_db.db__war_league_clan_setup.find_one({'_id':self.tag})
    
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