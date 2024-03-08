import coc
import discord
import asyncio
import pendulum
import random
import logging
import motor.motor_asyncio

from typing import *

from collections import defaultdict
from async_property import AwaitLoader
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter

from ...client.db_client import MotorClient

from ...utils.constants.coc_emojis import EmojisTownHall
from ...utils.utils import check_rtl

DATA_LOG = logging.getLogger("coc.main")

class BasicClan(AwaitLoader):
    
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
    @property
    def database(self) -> motor.motor_asyncio.AsyncIOMotorDatabase:
        return self._attributes.database
    @property
    def bot(self) -> Red:
        return self._attributes.bot
    
    async def load(self):
        await self._attributes.load()
    
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
    
    @property
    def _create_snapshot(self) -> bool:
        if random.randint(1,50) == random.randint(1,50):
            return True
    
    ##################################################
    #####
    ##### CACHED CLAN ATTRIBUTES
    #####
    ##################################################
    @property
    def name(self) -> str:
        return self._attributes.name
    
    @property
    def badge(self) -> str:
        return self._attributes.badge
    
    @property
    def level(self) -> int:
        return self._attributes.level
    
    @property
    def capital_hall(self) -> int:
        return self._attributes.capital_hall
    
    @property
    def war_league_name(self) -> str:
        return self._attributes.war_league_name
    
    ##################################################
    #####
    ##### REGISTERED CLAN
    #####
    ##################################################    
    @property
    def is_registered_clan(self) -> bool:
        return True if len(self.emoji) > 0 else False
    
    @property
    def abbreviation(self) -> str:
        return self._attributes.abbreviation

    @property
    def emoji(self) -> str:
        return self._attributes.emoji
    
    @property
    def unicode_emoji(self) -> str:
        return self._attributes.unicode_emoji
    
    ##################################################
    #####
    ##### ALLIANCE CLAN
    #####
    ##################################################
    @property
    def is_alliance_clan(self) -> bool:
        return self._attributes.is_alliance_clan
    
    @property
    def recruitment_level(self) -> List[int]:
        return self._attributes.recruitment_level        
    @property
    def max_recruitment_level(self) -> int:
        return max(self.recruitment_level) if len(self.recruitment_level) > 0 else 0    
    @property
    def recruitment_level_emojis(self) -> str:
        return " ".join([EmojisTownHall.get(th_level) for th_level in self.recruitment_level])

    @property
    def recruitment_info(self) -> str:
        return self._attributes.recruitment_info
    
    @property
    def description(self) -> str:
        return self._attributes.description
    
    @property
    def leader(self) -> int:
        return self._attributes.leader
    
    @property
    def coleaders(self) -> List[int]:
        return self._attributes.coleaders
    
    @property
    def elders(self) -> List[int]:
        return self._attributes.elders

    @property
    def alliance_members(self) -> List[str]:
        if len(self._attributes.alliance_members) == 0:
            return []
        return list(set(self._attributes.alliance_members))
    
    @property
    def alliance_member_count(self) -> int:
        return len(self.alliance_members)
    
    ##################################################
    #####
    ##### WAR LEAGUE CLAN
    #####
    ##################################################
    @property
    def is_active_league_clan(self) -> bool:
        return self._attributes.is_active_league_clan
    
    ##################################################
    #####
    ##### CLAN FUNCTIONS
    #####
    ##################################################
    async def new_member(self,player_tag:str):
        async with self._attributes._lock:
            if player_tag not in self._attributes.alliance_members:
                self._attributes.alliance_members.append(player_tag)
    
    async def remove_member(self,player_tag:str):
        async with self._attributes._lock:
            if player_tag in self._attributes.alliance_members:
                self._attributes.alliance_members.remove(player_tag)

    async def register(self,abbreviation:str,emoji:str,unicode_emoji:str):
        async with self._attributes._lock:    
            self._attributes.abbreviation = abbreviation.upper()
            self._attributes.emoji = emoji
            self._attributes.unicode_emoji = unicode_emoji

            await self.database.db__clan.update_one(
                {'_id':self.tag},
                {'$set':{
                    'abbreviation':self.abbreviation,
                    'emoji':self.emoji,
                    'unicode_emoji':self.unicode_emoji
                    }
                },
                upsert=True)
            
            DATA_LOG.info(
                f"{self}: Clan Registered!"
                + f"\n\tAbbreviation: {self.abbreviation}"
                + f"\n\tEmoji: {self.emoji}"
                + f"\n\tUnicode Emoji: {self.unicode_emoji}"
                )
    
    async def unregister(self):
        async with self._attributes._lock:    
            self._attributes.abbreviation = ""
            self._attributes.emoji = ""
            self._attributes.unicode_emoji = ""

            await self.database.db__clan.update_one(
                {'_id':self.tag},
                {'$unset':{
                    'abbreviation':'',
                    'emoji':'',
                    'unicode_emoji':''
                    }
                },
                upsert=True)
            
            if self.is_alliance_clan:
                await self.database.db__alliance_clan.delete_one({'_id':self.tag})
                self._attributes.is_alliance_clan = False
            
            DATA_LOG.info(
                f"{self}: Clan Unregistered!"
                + f"\n\tAbbreviation: {self.abbreviation}"
                + f"\n\tEmoji: {self.emoji}"
                + f"\n\tUnicode Emoji: {self.unicode_emoji}"
                )
    
    async def add_to_war_league(self):
        async with self._attributes._lock:
            self._attributes.is_active_league_clan = True

            await self.database.db__war_league_clan_setup.update_one(
                {'_id':self.tag},
                {'$set':{'is_active':self.is_active_league_clan}
                },
                upsert=True)
            DATA_LOG.info(f"{self}: Registered as CWL Clan.")
    
    async def remove_from_war_league(self):        
        async with self._attributes._lock:
            self._attributes.is_active_league_clan = False

            await self.database.db__war_league_clan_setup.update_one(
                {'_id':self.tag},
                {'$set':{'is_active':self.is_active_league_clan}
                },
                upsert=True)
            DATA_LOG.info(f"{self}: Removed as CWL Clan.")

    async def new_leader(self,new_leader:int):
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
            
            await self.database.db__alliance_clan.update_one(
                {'_id':self.tag},
                {'$set':{
                    'leader':self.leader,
                    'coleaders':self.coleaders,
                    'elders':self.elders
                    }
                },
                upsert=True)
            self._attributes.is_alliance_clan = True
            DATA_LOG.info(f"{self}: leader is now {new_leader}.")
    
    async def new_coleader(self,new_coleader:int):
        if new_coleader == self.leader:
            return
               
        async with self._attributes._lock:
            if new_coleader not in self.coleaders:
                self._attributes.coleaders.append(new_coleader)
            
            if new_coleader in self.elders:
                self._attributes.elders.remove(new_coleader)

            await self.database.db__alliance_clan.update_one(
                {'_id':self.tag},
                {'$set':{
                    'coleaders':self.coleaders,
                    'elders':self.elders
                    }
                },
                upsert=True)
            DATA_LOG.info(f"{self}: new coleader {new_coleader} added.")
    
    async def remove_coleader(self,coleader:int):
        async with self._attributes._lock:
            if coleader in self.coleaders:
                self._attributes.coleaders.remove(coleader)
            
            await self.database.db__alliance_clan.update_one(
                {'_id':self.tag},
                {'$set':{
                    'coleaders':self.coleaders
                    }
                },
                upsert=True)
            DATA_LOG.info(f"{self}: coleader {coleader} removed.")                
    
    async def new_elder(self,new_elder:int):
        if new_elder == self.leader:
            return
        
        async with self._attributes._lock:
            if new_elder not in self._attributes.elders:
                self._attributes.elders.append(new_elder)

            if new_elder in self.coleaders:
                self._attributes.coleaders.remove(new_elder)
            
            await self.database.db__alliance_clan.update_one(
                {'_id':self.tag},
                {'$set':{
                    'coleaders':self.coleaders,
                    'elders':self.elders
                    }
                },
                upsert=True)
            DATA_LOG.info(f"{self}: new elder {new_elder} added.")
            
    async def remove_elder(self,elder:int):
        async with self._attributes._lock:
            if elder in self.elders:
                self._attributes.elders.remove(elder)
            
            await self.database.db__alliance_clan.update_one(
                {'_id':self.tag},
                {'$set':{
                    'elders':self.elders
                    }
                },
                upsert=True)
            DATA_LOG.info(f"{self}: elder {elder} removed.")
        
    ##################################################
    #####
    ##### DATABASE INTERACTIONS
    #####
    ##################################################
    async def clean_elders(self):
        e_iter = AsyncIter(self.elders)
        async for elder in e_iter:
            q_doc = {
                'discord_user':elder,
                'home_clan':self.tag,
                'is_member':True
                }
            player_accounts = await self.database.db__player.find(q_doc,{'_id':1}).to_list(None)
            if len(player_accounts) == 0:
                await self.remove_elder(elder)
    
    async def clean_coleaders(self):
        c_iter = AsyncIter(self.coleaders)
        async for coleader in c_iter:
            q_doc = {
                'discord_user':coleader,
                'home_clan':self.tag,
                'is_member':True
                }
            player_accounts = await self.database.db__player.find(q_doc,{'_id':1}).to_list(None)
            if len(player_accounts) == 0:
                await self.remove_coleader(coleader)

    async def set_name(self,new_name:str):        
        async with self._attributes._lock:
            self._attributes.name = new_name
            await self.database.db__clan.update_one(
                {'_id':self.tag},
                {'$set':{'name':self.name}},
                upsert=True
                )
            DATA_LOG.debug(f"{self}: name changed to {self.name}.")

    async def set_badge(self,new_badge:str):        
        async with self._attributes._lock:
            self._attributes.badge = new_badge
            await self.database.db__clan.update_one(
                {'_id':self.tag},
                {'$set':{'badge':self.badge}},
                upsert=True
                )
            DATA_LOG.debug(f"{self}: badge changed to {self.badge}.")
    
    async def set_level(self,new_level:int):        
        async with self._attributes._lock:
            self._attributes.level = new_level
            await self.database.db__clan.update_one(
                {'_id':self.tag},
                {'$set':{'level':self.level}},
                upsert=True
                )
            DATA_LOG.debug(f"{self}: level changed to {self.level}.")
    
    async def set_capital_hall(self,new_capital_hall:int):        
        async with self._attributes._lock:
            self._attributes.capital_hall = new_capital_hall
            await self.database.db__clan.update_one(
                {'_id':self.tag},
                {'$set':{'capital_hall':self.capital_hall}},
                upsert=True
                )
            DATA_LOG.debug(f"{self}: capital_hall changed to {self.capital_hall}.")
    
    async def set_war_league(self,new_war_league:str):
        async with self._attributes._lock:
            self._attributes.war_league_name = new_war_league
            await self.database.db__clan.update_one(
                {'_id':self.tag},
                {'$set':{'war_league':self.war_league_name}},
                upsert=True
                )
            DATA_LOG.debug(f"{self}: war_league changed to {self.war_league_name}.")
        
    async def set_description(self,description:str):
        async with self._attributes._lock:
            self._attributes.description = description
            await self.database.db__alliance_clan.update_one(
                {'_id':self.tag},
                {'$set':{
                    'description':self.description
                    }
                },
                upsert=True)
            DATA_LOG.info(f"{self}: description changed to {self.description}.")
    
    async def set_recruitment_level(self,recruitment_levels:list[int]):
        async with self._attributes._lock:
            self._attributes.recruitment_level = sorted(list(set(recruitment_levels)))
            await self.database.db__alliance_clan.update_one(
                {'_id':self.tag},
                {'$set':{
                    'recruitment_level':self.recruitment_level
                    }
                },
                upsert=True)
            DATA_LOG.info(f"{self}: recruitment_level changed to {sorted(self.recruitment_level)}.")
    
    async def set_recruitment_info(self,new_recruitment_info:str):        
        async with self._attributes._lock:
            self._attributes.recruitment_info = new_recruitment_info
            await self.database.db__alliance_clan.update_one(
                {'_id':self.tag},
                {'$set':{
                    'recruitment_info':self.recruitment_info
                    }
                },
                upsert=True)
            DATA_LOG.info(f"{self}: recruitment info changed to {self.recruitment_info}.")
    
    async def update_last_sync(self,timestamp:pendulum.DateTime):
        async with self._attributes._lock:
            self._attributes._last_sync = timestamp
            await self.database.db__clan.update_one(
                {'_id':self.tag},
                {'$set':{'last_sync':timestamp.int_timestamp}},
                upsert=True
                )

class _ClanAttributes(MotorClient):
    """
    This class enforces a singleton pattern that caches database responses.

    This class DOES NOT handle database updates - those are handled within the BasicClan class.
    """
    _cache = {}
    _locks = defaultdict(asyncio.Lock)
    _sync_locks = defaultdict(asyncio.Lock)

    __slots__ = [
        '_new',
        '_loaded',
        '_last_sync',
        'tag',
        'name',
        'badge',
        'level',
        'capital_hall',
        'war_league_name',
        'abbreviation',
        'emoji',
        'unicode_emoji',
        'is_alliance_clan',
        'recruitment_level',
        'recruitment_info',
        'description',
        'leader',
        'coleaders',
        'elders',
        'alliance_members',
        'is_active_league_clan'
        ]

    def __new__(cls,tag:str):
        n_tag = coc.utils.correct_tag(tag)
        if n_tag not in cls._cache:
            instance = super().__new__(cls)
            instance._new = True
            instance._loaded = False
            cls._cache[n_tag] = instance
        return cls._cache[n_tag]
    
    def __init__(self,tag:str):
        if self._new:
            self.tag = coc.utils.correct_tag(tag)
            self.name = None
            self.badge = None
            self.level = None
            self.capital_hall = None
            self.war_league_name = None
            self.abbreviation = None
            self.emoji = None
            self.unicode_emoji = None
            self.is_alliance_clan = None
            self.recruitment_level = None
            self.recruitment_info = None
            self.description = None
            self.leader = None
            self.coleaders = None
            self.elders = None
            self.alliance_members = None
            self.is_active_league_clan = None

            self._last_sync = None
            
        self._new = False
    
    @property
    def _lock(self):
        return self._locks[self.tag]
    @property
    def _sync_lock(self):
        return self._sync_locks[self.tag]

    async def load(self):
        if not self._loaded:
            await self.load_data()
    
    async def load_data(self):
        clan_db = await self.database.db__clan.find_one({'_id':self.tag})
        self.name = clan_db.get('name','') if clan_db else ''
        self.badge = clan_db.get('badge','') if clan_db else ''
        self.level = clan_db.get('level',0) if clan_db else 0
        self.capital_hall = clan_db.get('capital_hall',0) if clan_db else 0
        self.war_league_name = clan_db.get('war_league','') if clan_db else ''
        self.abbreviation = clan_db.get('abbreviation','') if clan_db else ''
        self.emoji = clan_db.get('emoji','') if clan_db else ''
        self.unicode_emoji = clan_db.get('unicode_emoji','') if clan_db else ''

        ls = clan_db.get('last_sync',0) if clan_db else 0
        self._last_sync = pendulum.from_timestamp(ls) if ls else None

        alliance_db = await self.database.db__alliance_clan.find_one({'_id':self.tag})
        self.is_alliance_clan = True if alliance_db else False
        self.recruitment_level = sorted(alliance_db.get('recruitment_level',[]) if alliance_db else [])
        self.recruitment_info = alliance_db.get('recruitment_info','') if alliance_db else ''
        self.description = alliance_db.get('description','') if alliance_db else ''
        self.leader = alliance_db.get('leader',0) if alliance_db else 0
        self.coleaders = alliance_db.get('coleaders',[]) if alliance_db else []
        self.elders = alliance_db.get('elders',[]) if alliance_db else []

        if self.is_alliance_clan:
            mem_query = self.database.db__player.find({'is_member':True,'home_clan':self.tag},{'_id':1})
            self.alliance_members = [p['_id'] async for p in mem_query]
        else:
            self.alliance_members = []

        league_db = await self.database.db__war_league_clan_setup.find_one({'_id':self.tag})
        self.is_active_league_clan = league_db.get('is_active',False) if league_db else False
        
        self._loaded = True