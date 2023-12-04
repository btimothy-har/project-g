import discord
import pendulum
import asyncio

from typing import *

from async_property import AwaitLoader
from redbot.core import commands
from redbot.core.utils import chat_formatting as chat
from redbot.core.utils import AsyncIter

from .guild import aGuild, ClanGuildLink

from ..api_client import BotClashClient as client

from ..coc_objects.players.player import BasicPlayer
from ..coc_objects.clans.player_clan import aPlayerClan

from ..exceptions import InvalidUser, InvalidGuild, InvalidTag, CacheNotReady
from ..utils.constants.coc_constants import ClanRanks, MultiplayerLeagues

bot_client = client()

class aMember(AwaitLoader):
    _global = {}
    _local = {}

    __slots__ = [
        '_is_new',
        '_lock',
        'user_id',
        'guild_id',
        'accounts',
        'member_accounts',
        'home_clans',
        'last_payday',
        'last_role_sync'
        ]

    def __new__(cls,user_id,guild_id=None):
        if guild_id:
            i = (guild_id,user_id)
            if (guild_id,user_id) not in cls._local:
                instance = super().__new__(cls)
                instance._is_new = True
                cls._local[i] = instance
            return cls._local[i]
        else:
            if user_id not in cls._global:
                instance = super().__new__(cls)
                instance._is_new = True
                cls._global[user_id] = instance
            return cls._global[user_id]

    def __init__(self,user_id:int,guild_id:Optional[int]=None):
        self.user_id = user_id
        self.guild_id = guild_id
        
        if self._is_new:
            self._lock = asyncio.Lock()

            self.accounts = []
            self.member_accounts = []
            self.home_clans = []            
            self.last_payday = pendulum.now()
            self.last_role_sync = pendulum.now()
        
        self._is_new = False

    def __str__(self):
        return getattr(self.discord_member,'display_name',str(self.user_id))
    
    def __eq__(self,other):
        return isinstance(other,aMember) and self.user_id == other.user_id and self.guild_id == other.guild_id

    @property
    def db_id(self) -> Optional[dict]:
        if not self.guild_id:
            return None
        return {'guild':self.guild_id,'user':self.user_id}

    async def _get_scope_clans(self) -> List[str]:
        if self.guild_id:
            return [link.tag for link in await ClanGuildLink.get_for_guild(self.guild_id)]
        else:
            client_cog = bot_client.bot.get_cog('ClashOfClansClient')
            return [clan.tag for clan in await client_cog.get_alliance_clans()]
        
    async def load(self):
        scope = await self._get_scope_clans()
        query = bot_client.coc_db.db__player.find(
            {
                'discord_user':self.user_id
                },
            {'_id':1,'is_member':1,'home_clan':1}
            )
        #sort by TH, exp level, alliance rank
        self.accounts = sorted(
            [await BasicPlayer(db['_id']) async for db in query],
            key=lambda x: (x.town_hall_level,x.exp_level,x.clean_name),
            reverse=True
            )
        self.member_accounts = sorted(
            [a for a in self.accounts if a.is_member and a.home_clan and a.home_clan.tag in scope],
            key=lambda x: (ClanRanks.get_number(x.alliance_rank),x.town_hall_level,x.exp_level,x.clean_name),
            reverse=True
            )
        
        for a in self.member_accounts:
            if a.home_clan.tag not in [c.tag for c in self.home_clans]:
                self.home_clans.append(a.home_clan)
        self.home_clans.sort(
            key=lambda x:(x.level, MultiplayerLeagues.get_index(x.war_league_name), x.capital_hall),
            reverse=True
            )

        query = await bot_client.coc_db.db__discord_member.find(
            {'_id':self.db_id},
            {'_id':1,'guild_id':1,'last_payday':1,'last_role_sync':1}
            ).to_list(length=None)
        db_lastpayday = [db.get('last_payday',0) for db in query]
        self.last_payday = pendulum.from_timestamp(max(db_lastpayday)) if len(db_lastpayday) > 0 else None
    
    ##################################################
    ### DISCORD MEMBER ATTRIBUTES
    ##################################################
    @property
    def guild(self) -> Optional[aGuild]:
        if not self.guild_id:
            return None
        try:
            return aGuild(self.guild_id)
        except InvalidGuild:
            return None
        
    @property
    def discord_member(self) -> Optional[Union[discord.User,discord.Member]]:
        guild = bot_client.bot.get_guild(self.guild_id) if self.guild_id else None
        if guild:
            return guild.get_member(self.user_id)
        return bot_client.bot.get_user(self.user_id)

    @property
    def mention(self):
        return getattr(self.discord_member,'mention',f"<@{self.user_id}>")
    
    @property
    def display_avatar(self):
        return getattr(self.discord_member,'display_avatar',None)
    
    @property
    def name(self) -> str:
        if not self.discord_member:
            return str(self.user_id)
        discriminator = getattr(self.discord_member,'discriminator','0')
        if discriminator != '0':
            return f"{self.discord_member.name}#{discriminator}"
        else:
            return f"@{self.discord_member.name}"
        
    @property
    def display_name(self) -> str:
        return getattr(self.discord_member,'display_name',str(self.user_id))
    
    @property
    def created_at(self) -> Optional[pendulum.DateTime]:
        if self.discord_member and getattr(self.discord_member,'created_at',None):
            return pendulum.instance(self.discord_member.created_at)
        else:
            return None
        
    @property
    def joined_at(self) -> Optional[pendulum.DateTime]:
        if self.discord_member and getattr(self.discord_member,'joined_at',None):
            return pendulum.instance(self.discord_member.joined_at)
        else:
            return None
    
    ##################################################
    ### CLASH OF CLANS ATTRIBUTES
    ##################################################
    @property
    def account_tags(self) -> List[str]:
        return [a.tag for a in self.accounts]
    @property
    def member_tags(self) -> List[str]:
        return [a.tag for a in self.member_accounts]
    @property
    def leader_clans(self) -> List[aPlayerClan]:
        return [hc for hc in self.home_clans if self.user_id == hc.leader]    
    @property
    def coleader_clans(self) -> List[aPlayerClan]:
        return [hc for hc in self.home_clans if self.user_id in hc.coleaders or self.user_id == hc.leader]    
    @property
    def elder_clans(self) -> List[aPlayerClan]:
        return [hc for hc in self.home_clans if self.user_id in hc.elders or self.user_id in hc.coleaders or self.user_id == hc.leader]
    @property
    def is_member(self) -> bool:
        return len(self.member_accounts) > 0
    @property
    def is_elder(self) -> bool:
        return len(self.elder_clans) > 0
    @property
    def is_coleader(self) -> bool:
        return len(self.coleader_clans) > 0
    @property
    def is_leader(self) -> bool:
        return len(self.leader_clans) > 0

    ##################################################
    ### BANK ATTRIBUTES
    ##################################################    
    async def set_last_payday(self,timestamp:pendulum.DateTime):
        self.last_payday = timestamp
        await bot_client.coc_db.db__discord_member.update_one(
            {'_id':self.db_id},
            {'$set':{
                'user_id':self.user_id,
                'guild_id':self.guild_id,
                'last_payday':getattr(self.last_payday,'int_timestamp',None)
                }
            },
            upsert=True)

    ##################################################
    ### ROLE ATTRIBUTES & METHODS
    ##################################################
    @classmethod
    async def save_user_roles(cls,user_id:int,guild_id:int):
        user = await cls(user_id,guild_id)
        if not user.discord_member:
            raise InvalidUser(user.user_id)
        if not user.guild:
            raise InvalidGuild(user.guild_id)
        
        try:
            await user.sync_clan_roles()
        except CacheNotReady:
            pass
        
        await bot_client.coc_db.db__discord_member.update_one(
            {'_id':user.db_id},
            {'$set':{
                'user_id':user.user_id,
                'guild_id':user.guild_id,
                'roles':[str(r.id) for r in user.discord_member.roles if r.is_assignable()],
                'last_role_save':pendulum.now().int_timestamp
                }
            },
            upsert=True)
     
    async def restore_user_roles(self) -> Tuple[List[Optional[discord.Role]],List[Optional[discord.Role]]]:
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        
        added_roles = []
        failed_roles = []        
        if not self.guild:
            return added_roles, failed_roles
        
        db_saved_roles = await bot_client.coc_db.db__discord_member.find_one({'_id':self.db_id})
        saved_roles = db_saved_roles.get('roles',[]) if db_saved_roles else []

        async for role_id in AsyncIter(saved_roles):
            role = self.guild.guild.get_role(int(role_id))
            if not role:
                continue
            if role.is_assignable():
                try:
                    await self.discord_member.add_roles(role)
                except (discord.Forbidden,discord.NotFound):
                    failed_roles.append(role)
                else:
                    added_roles.append(role)
        return added_roles, failed_roles

    async def sync_clan_roles(self,
        context:Optional[Union[discord.Interaction,commands.Context]]=None,
        force:bool=False) -> Tuple[List[Optional[discord.Role]],List[Optional[discord.Role]]]:

        roles_added = []
        roles_removed = []
 
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        if not self.guild:
            return roles_added, roles_removed
        
        if not force:
            db_last_sync = await bot_client.coc_db.db__discord_member.find_one({'_id':self.db_id})
            ls = db_last_sync.get('last_role_sync',None) if db_last_sync else None
            
            if ls and pendulum.now().int_timestamp - ls < 600:
                return roles_added, roles_removed                
    
        async with self._lock:
            #Assassins guild Member Role
            if self.guild.id == 1132581106571550831:
                global_member = await aMember(self.user_id)
                clan_member_role = self.guild.guild.get_role(1139855695068540979)
                
                if global_member.is_member:                
                    if clan_member_role not in self.discord_member.roles:
                        roles_added.append(clan_member_role)

                if not global_member.is_member:                
                    if clan_member_role in self.discord_member.roles:
                        roles_removed.append(clan_member_role)

            guild_links = await ClanGuildLink.get_for_guild(self.guild.id)
            async for link in AsyncIter(guild_links):
                clan = await link.clan

                if clan.tag in [c.tag for c in self.home_clans]:
                    is_elder = False
                    is_coleader = False

                    if self.user_id == clan.leader or self.user_id in clan.coleaders:
                        is_elder = True
                        is_coleader = True
                    elif self.user_id in clan.elders:
                        is_elder = True
                    
                    if link.member_role:
                        if link.member_role not in self.discord_member.roles:
                            roles_added.append(link.member_role)
                    
                    if link.elder_role:
                        if is_elder:
                            if link.elder_role not in self.discord_member.roles:
                                roles_added.append(link.elder_role)
                        else:
                            if link.elder_role in self.discord_member.roles:
                                roles_removed.append(link.elder_role)
                    
                    if link.coleader_role:
                        if is_coleader:
                            if link.coleader_role not in self.discord_member.roles:
                                roles_added.append(link.coleader_role)
                        else:
                            if link.coleader_role in self.discord_member.roles:
                                roles_removed.append(link.coleader_role)

                else:
                    if link.member_role:
                        if link.member_role in self.discord_member.roles:
                            roles_removed.append(link.member_role)
                    if link.elder_role:
                        if link.elder_role in self.discord_member.roles:
                            roles_removed.append(link.elder_role)
                    if link.coleader_role:
                        if link.coleader_role in self.discord_member.roles:
                            roles_removed.append(link.coleader_role)

            if isinstance(context,commands.Context):
                initiating_user = context.author
                initiating_command = getattr(context.command,'name','Unknown Command')
            elif isinstance(context,discord.Interaction):
                initiating_user = context.user
                initiating_command = context.command.name
            else:
                initiating_user = 'system'
                initiating_command = 'background sync job'
            
            if len(roles_added) > 0:
                try:
                    await self.discord_member.add_roles(*roles_added,reason=f"Clan Role Sync: {initiating_user} from {initiating_command}")
                except discord.Forbidden:
                    bot_client.coc_main_log.exception(f"Error adding roles to {self.discord_member.name} {self.discord_member.id}.")
                else:
                    bot_client.coc_main_log.info(
                        f"[{self.guild.name} {self.guild.id}] [{self.discord_member.name} {self.discord_member.id}] Roles Added: {chat.humanize_list([r.name for r in roles_added])}. "
                        + f"Initiated by {initiating_user} from {initiating_command}."
                        )
                    
            if len(roles_removed) > 0:
                try:
                    await self.discord_member.remove_roles(*roles_removed,reason=f"Clan Role Sync: {initiating_user} from {initiating_command}")
                except discord.Forbidden:
                    bot_client.coc_main_log.exception(f"Error removing roles from {self.discord_member.name} {self.discord_member.id}.")
                else:
                    bot_client.coc_main_log.info(
                        f"[{self.guild.name} {self.guild.id}] [{self.discord_member.name} {self.discord_member.id}] Roles Removed: {chat.humanize_list([r.name for r in roles_removed])}. "
                        + f"Initiated by {initiating_user} from {initiating_command}."
                        )
            
            await bot_client.coc_db.db__discord_member.update_one(
                {'_id':self.db_id},
                {'$set':{
                    'user_id':self.user_id,
                    'guild_id':self.guild_id,
                    'last_role_sync':pendulum.now().int_timestamp
                    }
                },
                upsert=True)
        return roles_added, roles_removed
    
    ##################################################
    ### NICKNAME ATTRIBUTES & METHODS
    ##################################################
    async def _get_default_account_tag(self) -> Optional[str]:
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        
        if len(self.accounts) == 0:
            return None
        
        def_tag = None
        db = await bot_client.coc_db.db__discord_member.find_one({'_id':self.db_id})
        if db and db.get('default_account',None) in self.account_tags:
            def_tag = db['default_account']

        #ARIX
        if self.guild_id == 688449973553201335:
            if not self.is_member:
                return self.accounts[0].tag
            if def_tag in self.member_tags:
                return def_tag
            return self.member_tags[0]        
        
        #ARIX
        if self.guild_id == 688449973553201335 and len(self.member_accounts) > 0:
            return self.member_accounts[0].tag
        
        return self.accounts[0].tag
    
    async def set_default_account(self,tag:str):
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        
        if tag not in await self.account_tags:
            raise InvalidTag(tag)

        await bot_client.coc_db.db__discord_member.update_one(
            {'_id':self.db_id},
            {'$set':{
                'user_id':self.user_id,
                'guild_id':self.guild_id,
                'default_account':tag
                }
            },
            upsert=True)

    async def get_nickname(self) -> str:
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        
        default_tag = await self._get_default_account_tag()
        default_account = await BasicPlayer(default_tag) if default_tag else None

        if not default_account:
            new_nickname = self.discord_member.name
        else:
            new_nickname = default_account.name.replace('[AriX]','')
            new_nickname = new_nickname.strip()

        if self.guild_id == 688449973553201335:
            abb_clans = []

            guild_links = await ClanGuildLink.get_for_guild(self.guild_id)
            linked_clans = [link.tag for link in guild_links]

            if len(self.leader_clans) > 0:
                a_iter = AsyncIter(self.leader_clans)
                async for c in a_iter:
                    if c.abbreviation not in abb_clans and len(c.abbreviation) > 0 and c.tag in linked_clans:
                        abb_clans.append(c.abbreviation)
            
            else:
                if default_account.home_clan and default_account.home_clan.tag in linked_clans:
                    abb_clans.append(default_account.home_clan.abbreviation)
                
                if len(self.home_clans) > 0:
                    a_iter = AsyncIter(self.home_clans)
                    async for c in a_iter:
                        if c.abbreviation not in abb_clans and len(c.abbreviation) > 0 and c.tag in linked_clans:
                            abb_clans.append(c.abbreviation)

            if len(abb_clans) > 0:
                new_nickname += f" | {' + '.join(abb_clans)}"
        return new_nickname