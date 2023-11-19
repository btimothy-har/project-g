import coc
import discord
import asyncio

from typing import *
from mongoengine import *

from functools import cached_property
from ...api_client import BotClashClient as client
from .mongo_clan import db_Clan, db_AllianceClan, db_WarLeagueClanSetup
from ..players.mongo_player import db_Player

from ...discord.mongo_discord import db_ClanGuildLink

from ...utils.constants.coc_emojis import EmojisTownHall
from ...utils.utils import check_rtl

bot_client = client()

class BasicClan():

    @classmethod
    async def load_all(cls) -> List['BasicClan']:
        def _get_from_db():
            return [db.tag for db in db_Clan.objects.only('tag')]
        
        clan_tags = await bot_client.run_in_thread(_get_from_db)
        clans = [cls(tag=tag) for tag in clan_tags]
        await asyncio.gather(*(clan._load_attributes() for clan in clans))
        
        return clans
    
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
        return f"Clan {self.name} ({self.tag})"
    
    def __hash__(self):
        return hash(self.tag)
    
    async def _load_attributes(self):
        await self._attributes._load_attributes()
    
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
        return self._attributes.alliance_members
    
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
    
    @property
    def league_clan_channel(self) -> Optional[Union[discord.TextChannel,discord.Thread]]:
        channel = bot_client.bot.get_channel(self._attributes.league_clan_channel_id)
        if isinstance(channel,(discord.TextChannel,discord.Thread)):
            return channel
        return None
    
    @property
    def league_clan_role(self) -> Optional[discord.Role]:
        for guild in bot_client.bot.guilds:
            role = guild.get_role(self._attributes.league_clan_role_id)
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
            await bot_client.run_in_thread(_update_in_db)
    
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
            await bot_client.run_in_thread(_update_in_db)
    
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
            await bot_client.run_in_thread(_update_in_db)

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

            await bot_client.run_in_thread(_update_in_db)
    
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

            await bot_client.run_in_thread(_update_in_db)
    
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
                await bot_client.run_in_thread(_update_in_db)
    
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
            
            await bot_client.run_in_thread(_update_in_db)

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
                await bot_client.run_in_thread(_update_in_db)
        
    ##################################################
    #####
    ##### DATABASE INTERACTIONS
    #####
    ##################################################
    async def set_name(self,new_name:str):
        def _update_in_db():
            db_Clan.objects(tag=self.tag).update_one(
                set__name=self.name,
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: name changed to {self.name}.")
        
        async with self._attributes._lock:
            self._attributes.name = new_name
            await bot_client.run_in_thread(_update_in_db)
    
    async def set_badge(self,new_badge:str):
        def _update_in_db():
            db_Clan.objects(tag=self.tag).update_one(
                set__badge=self.badge,
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: badge changed to {self.badge}.")
        
        async with self._attributes._lock:
            self._attributes.badge = new_badge
            await bot_client.run_in_thread(_update_in_db)
    
    async def set_level(self,new_level:int):
        def _update_in_db():
            db_Clan.objects(tag=self.tag).update_one(
                set__level=self.level,
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: level changed to {self.level}.")
        
        async with self._attributes._lock:
            self._attributes.level = new_level
            await bot_client.run_in_thread(_update_in_db)
    
    async def set_capital_hall(self,new_capital_hall:int):
        def _update_in_db():
            db_Clan.objects(tag=self.tag).update_one(
                set__capital_hall=self.capital_hall,
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: capital_hall changed to {self.capital_hall}.")
        
        async with self._attributes._lock:
            self._attributes.capital_hall = new_capital_hall
            await bot_client.run_in_thread(_update_in_db)
    
    async def set_war_league(self,new_war_league:str):
        def _update_in_db():
            db_Clan.objects(tag=self.tag).update_one(
                set__war_league=self.war_league_name,
                upsert=True
                )
            bot_client.coc_data_log.debug(f"{self}: war_league changed to {self.war_league_name}.")
        
        async with self._attributes._lock:
            self._attributes.war_league_name = new_war_league
            await bot_client.run_in_thread(_update_in_db)
        
    async def set_description(self,description:str):
        def _update_in_db():
            db_AllianceClan.objects(tag=self.tag).update_one(
                set__description=self.description,
                upsert=False
                )
            bot_client.coc_data_log.info(f"{self}: description changed to {self.description}.")
        
        async with self._attributes._lock:
            self._attributes.description = description
            await bot_client.run_in_thread(_update_in_db)
    
    async def set_recruitment_level(self,recruitment_levels:list[int]):
        def _update_in_db():
            db_AllianceClan.objects(tag=self.tag).update_one(
                set__recruitment_level=self.recruitment_level,
                upsert=False
                )
            bot_client.coc_data_log.info(f"{self}: recruitment_level changed to {sorted(self.recruitment_level)}.")

        async with self._attributes._lock:
            self._attributes.recruitment_level = sorted(list(set(recruitment_levels)))
            await bot_client.run_in_thread(_update_in_db)
    
    async def set_recruitment_info(self,new_recruitment_info:str):
        def _update_in_db():
            db_AllianceClan.objects(tag=self.tag).update_one(
                set__recruitment_info=self.recruitment_info,
                upsert=False
                )
            bot_client.coc_data_log.info(f"{self}: recruitment info changed to {self.recruitment_info}.")
        
        async with self._attributes._lock:
            self._attributes.recruitment_info = new_recruitment_info
            await bot_client.run_in_thread(_update_in_db)
    
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
            bot_client.clan_queue.add(self.tag)
            
        self._is_new = False

    async def _load_attributes(self):
        def _primary_db() -> db_Clan:
            try:
                return db_Clan.objects.get(tag=self.tag)
            except DoesNotExist:
                return None
        
        def _alliance_db() -> db_AllianceClan:
            try:
                return db_AllianceClan.objects.get(tag=self.tag)
            except DoesNotExist:
                return None
            
        pdb = await bot_client.run_in_thread(_primary_db)
        if pdb:
            self.name = pdb.name
            self.badge = pdb.badge
            self.level = pdb.level
            self.capital_hall = pdb.capital_hall
            self.war_league_name = pdb.war_league
            self.abbreviation = pdb.abbreviation
            self.emoji = pdb.emoji
            self.unicode_emoji = pdb.unicode_emoji

        adb = await bot_client.run_in_thread(_alliance_db)
        if adb:
            self.is_alliance_clan = True
            self.recruitment_level = adb.recruitment_level
            self.recruitment_info = adb.recruitment_info
            self.description = adb.description
            self.leader = adb.leader
            self.coleaders = list(set(adb.coleaders))
            self.elders = list(set(adb.elders))
            
    ##################################################
    #####
    ##### DATABASES
    #####
    ##################################################
    @property
    def _database(self) -> Optional[db_Clan]:
        if not self.tag:
            return None
        try:
            return db_Clan.objects.get(tag=self.tag)
        except DoesNotExist:
            return None
        
    @property
    def _db_alliance(self) -> Optional[db_AllianceClan]:
        if not self.tag:
            return None
        try:
            return db_AllianceClan.objects.get(tag=self.tag)
        except DoesNotExist:
            return None
    
    @property
    def _league_clan(self) -> Optional[db_WarLeagueClanSetup]:
        if not self.tag:
            return None
        try:
            return db_WarLeagueClanSetup.objects.get(tag=self.tag)
        except DoesNotExist:
            return None
    
    ##################################################
    #####
    ##### CLAN ATTRIBUTES
    #####
    ##################################################
    @cached_property
    def name(self) -> str:
        return getattr(self._database,'name','')
    
    @cached_property
    def badge(self) -> str:
        return getattr(self._database,'badge','')
    
    @cached_property
    def level(self) -> int:
        return getattr(self._database,'level',0)    
    
    @cached_property
    def capital_hall(self) -> int:
        return getattr(self._database,'capital_hall',0)
    
    @cached_property
    def war_league_name(self) -> str:
        return getattr(self._database,'war_league','')
    
    ##################################################
    #####
    ##### REGISTERED CLAN
    #####
    ##################################################
    @cached_property
    def abbreviation(self) -> str:
        return getattr(self._database,'abbreviation','')

    @cached_property
    def emoji(self) -> str:
        return getattr(self._database,'emoji','')
    
    @cached_property
    def unicode_emoji(self) -> str:
        return getattr(self._database,'unicode_emoji','')
    
    ##################################################
    #####
    ##### ALLIANCE CLAN
    #####
    ##################################################
    @cached_property
    def is_alliance_clan(self) -> bool:
        return True if self._db_alliance else False
    
    @cached_property
    def recruitment_level(self) -> List[int]:
        i = getattr(self._db_alliance,'recruitment_level',[])
        return sorted(i)

    @cached_property
    def recruitment_info(self) -> str:
        return getattr(self._db_alliance,'recruitment_info','')
    
    @cached_property
    def description(self) -> str:
        return getattr(self._db_alliance,'description','')
    
    @cached_property
    def leader(self) -> int:
        return getattr(self._db_alliance,'leader',0)
    
    @cached_property
    def coleaders(self) -> List[int]:
        i = getattr(self._db_alliance,'coleaders',[])
        return list(set(i))
    
    @cached_property
    def elders(self) -> List[int]:
        i = getattr(self._db_alliance,'elders',[])
        return list(set(i))

    @cached_property
    def alliance_members(self) -> List[str]:
        return list(set([p.tag for p in db_Player.objects(is_member=True,home_clan=self.tag)]))
    
    ##################################################
    #####
    ##### WAR LEAGUE CLAN
    #####
    ##################################################
    @cached_property
    def is_active_league_clan(self) -> bool:
        return getattr(self._league_clan,'is_active',False)
    
    @cached_property
    def league_clan_channel_id(self) -> int:
        if not self.is_active_league_clan:
            return 0
        return getattr(self._league_clan,'channel',0)    
    
    @cached_property
    def league_clan_role_id(self) -> int:
        if not self.is_active_league_clan:
            return 0
        return getattr(self._league_clan,'role',0)