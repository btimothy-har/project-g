import discord
import pendulum
import asyncio

from typing import *
from mongoengine import *

from async_property import AwaitLoader, AwaitableOnly, async_property, async_cached_property
from redbot.core import commands
from redbot.core.utils import chat_formatting as chat
from redbot.core.utils import AsyncIter

from ..api_client import BotClashClient as client

from .guild import aGuild, ClanGuildLink

from ..coc_objects.players.player import BasicPlayer, db_Player
from ..coc_objects.clans.player_clan import db_AllianceClan, aPlayerClan

from .mongo_discord import db_DiscordMember

from ..exceptions import InvalidUser, InvalidGuild, InvalidTag, CacheNotReady
from ..utils.constants.coc_constants import ClanRanks

bot_client = client()

class aMember(AwaitLoader):
    _global = {}
    _local = {}

    @classmethod
    async def load_all(cls) -> List['aMember']:
        all_members = []
        iter_guilds = AsyncIter(bot_client.bot.guilds)
        async for guild in iter_guilds:
            members = await asyncio.gather(*(cls(member.id,guild.id).refresh_clash_link()
                for member in guild.members if not member.bot
                ))
            all_members.extend(members)
        return all_members    

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
            self._last_refreshed = None
            
            self.is_member = None
            self.is_elder = None
            self.is_coleader = None

            self._accounts = None
            self._home_clans = None
            self._default_account = None
            
            self._last_payday = None
        
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
    
    ##################################################
    ### CLASS METHODS
    ##################################################
    @classmethod
    async def save_user_roles(cls,user_id:int,guild_id:int):
        user = cls(user_id,guild_id)
        if not user.discord_member:
            raise InvalidUser(user.user_id)
        if not user.guild:
            raise InvalidGuild(user.guild_id)
        
        if not await user.last_role_sync or pendulum.now().int_timestamp - getattr(await user.last_role_sync,'int_timestamp',0) >= 600:
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
    async def refresh_clash_link(self,force:bool=False) -> 'aMember':        
        now = pendulum.now().int_timestamp

        async with self._lock:
            if force or (now - getattr(self._last_refreshed,'int_timestamp',0)) > 30:
                await self.eval_is_member()
                await self.eval_is_elder()
                await self.eval_is_coleader()
                await self.eval_is_leader()
                
                self._last_refreshed = pendulum.now()

        if self.guild_id:
            global_member = aMember(self.user_id)
            await global_member.refresh_clash_link()
        return self

    @async_property
    async def _scope_clans(self) -> List[str]:
        if self.guild_id:
            return [link.tag for link in await ClanGuildLink.get_for_guild(self.guild_id)]
        else:
            client_cog = bot_client.bot.get_cog('ClashOfClansClient')
            return [clan.tag for clan in await client_cog.get_alliance_clans()]
    
    @async_property
    async def account_tags(self) -> List[str]:
        query = bot_client.coc_db.db__player.find({'discord_user':self.user_id},{'_id':1})
        account_tags = [db['_id'] async for db in query]
        return account_tags
    
    @async_property
    async def accounts(self) -> List[BasicPlayer]:
        ret_players = [
            await BasicPlayer(tag=tag) for tag in await self.account_tags
            ]
        return sorted(ret_players, key=lambda x:(ClanRanks.get_number(x.alliance_rank),x.town_hall_level,x.exp_level),reverse=True)
    
    @async_property
    async def member_accounts(self) -> List[BasicPlayer]:
        accounts = await self.accounts
        ret = []
        a_iter = AsyncIter(accounts)
        async for account in a_iter:
            if await account.is_member and await account.home_clan:
                if account.home_clan.tag in await self._scope_clans:
                    ret.append(account)
        return sorted(ret, key=lambda x:(ClanRanks.get_number(x.alliance_rank),x.town_hall_level,x.exp_level),reverse=True)

    @async_property
    async def home_clans(self) -> List[aPlayerClan]:
        accounts = await self.accounts
        ret = []
        a_iter = AsyncIter(accounts)
        async for account in a_iter:
            if await account.home_clan:
                if account.home_clan.tag not in [c.tag for c in ret]:
                    ret.append(account.home_clan)
        return ret
    
    @async_property
    async def leader_clans(self) -> List[aPlayerClan]:
        return [hc for hc in await self.home_clans if self.user_id == await hc.leader]
    
    @async_property
    async def coleader_clans(self) -> List[aPlayerClan]:
        return [hc for hc in await self.home_clans if self.user_id in await hc.coleaders or self.user_id == await hc.leader]
    
    @async_property
    async def elder_clans(self) -> List[aPlayerClan]:
        return [hc for hc in await self.home_clans if self.user_id in await hc.elders or self.user_id in await hc.coleaders or self.user_id == await hc.leader]
    
    async def eval_is_member(self) -> bool:
        if len(await self.home_clans) > 0:
            self.is_member = True
            return
        self.is_member = False
    
    async def eval_is_elder(self) -> bool:
        if len(await self.elder_clans) > 0:
            self.is_elder = True
            return
        self.is_elder = False

    async def eval_is_coleader(self) -> bool:
        if len(await self.coleader_clans) > 0:
            self.is_coleader = True
            return
        self.is_coleader = False    
    
    async def eval_is_leader(self) -> bool:
        if len(await self.leader_clans) > 0:
            self.is_leader = True
            return
        self.is_leader = False

    ##################################################
    ### BANK ATTRIBUTES
    ##################################################
    @async_property
    async def last_payday(self) -> Optional[pendulum.DateTime]:
        if self.guild_id:
            raise InvalidUser(self.user_id)        
        m = aMember(self.user_id)
        return await m._last_payday
    
    @async_cached_property
    async def _last_payday(self) -> Optional[pendulum.DateTime]:
        query = bot_client.coc_db.db__discord_member.find({'_id':self.db_id},{'_id':1,'last_payday':1})
        last_paydays = [db['last_payday'] async for db in query]
        if len(last_paydays) > 0:
            return pendulum.from_timestamp(max(last_paydays))
        return None
    
    async def set_last_payday(self,timestamp:pendulum.DateTime):
        m = aMember(self.user_id)
        m._last_payday = timestamp.int_timestamp
        await bot_client.coc_db.db__discord_member.update_one(
            {'_id':self.db_id},
            {'$set':{
                'user_id':self.user_id,
                'guild_id':self.guild_id,
                'last_payday':getattr(await m._last_payday,'int_timestamp',None)
                }
            },
            upsert=True)

    ##################################################
    ### ROLE ATTRIBUTES & METHODS
    ##################################################
    @async_cached_property
    async def last_role_sync(self) -> Optional[pendulum.DateTime]:        
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        
        db = await bot_client.coc_db.db__discord_member.find_one({'_id':self.db_id})
        if db and db.get('last_role_sync',None):
            return pendulum.from_timestamp(db['last_role_sync'])
        return None
    
    @async_property
    async def saved_roles(self) -> List[Optional[discord.Role]]:
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        
        db = await bot_client.coc_db.db__discord_member.find_one({'_id':self.db_id})
        if db and db.get('roles',None):
            return [self.guild.guild.get_role(int(r)) for r in db['roles']]
        return []

    async def restore_user_roles(self) -> Tuple[List[Optional[discord.Role]],List[Optional[discord.Role]]]:
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        
        added_roles = []
        failed_roles = []        
        if not self.guild:
            return added_roles, failed_roles        
        
        saved_roles = await self.saved_roles        
        async for role in AsyncIter(saved_roles):
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

    async def sync_clan_roles(self,context:Optional[Union[discord.Interaction,commands.Context]]=None) -> Tuple[List[Optional[discord.Role]],List[Optional[discord.Role]]]:
        roles_added = []
        roles_removed = []
 
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        if not self.guild:
            return roles_added, roles_removed
    
        await self.refresh_clash_link(force=True)
        async with self._lock:            
            #Assassins guild Member Role
            if self.guild.id == 1132581106571550831:
                global_member = aMember(self.user_id)
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

                if clan.tag in [c.tag for c in await self.home_clans]:
                    is_elder = False
                    is_coleader = False

                    if self.user_id == await clan.leader or self.user_id in await clan.coleaders:
                        is_elder = True
                        is_coleader = True
                    elif self.user_id in await clan.elders:
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
                    await self.discord_member.add_roles(*roles_added)
                except discord.Forbidden:
                    bot_client.coc_main_log.exception(f"Error adding roles to {self.discord_member.name} {self.discord_member.id}.")
                else:
                    bot_client.coc_main_log.info(f"[{self.guild.name} {self.guild.id}] [{self.discord_member.name} {self.discord_member.id}] Roles Added: {chat.humanize_list([r.name for r in roles_added])}. Initiated by {initiating_user} from {initiating_command}.")
                    
            if len(roles_removed) > 0:
                try:
                    await self.discord_member.remove_roles(*roles_removed)
                except discord.Forbidden:
                    bot_client.coc_main_log.exception(f"Error removing roles from {self.discord_member.name} {self.discord_member.id}.")
                else:
                    bot_client.coc_main_log.info(f"[{self.guild.name} {self.guild.id}] [{self.discord_member.name} {self.discord_member.id}] Roles Removed: {chat.humanize_list([r.name for r in roles_removed])}. Initiated by {initiating_user} from {initiating_command}.")
            
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
    @async_cached_property
    async def default_account_tag(self) -> Optional[str]:
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        
        all_accounts = await self.accounts
        member_accounts = await self.member_accounts

        if len(all_accounts) == 0:
            return None        

        #ARIX
        if self.guild_id == 688449973553201335 and not self.is_member:
            return all_accounts[0].tag

        db = await bot_client.coc_db.db__discord_member.find_one({'_id':self.db_id})
        if db and db.get('default_account',None) in await self.account_tags:
            return db['default_account']
        
        #ARIX
        if self.guild_id == 688449973553201335 and len(member_accounts) > 0:
            return member_accounts[0].tag
        
        return all_accounts[0].tag
    
    @async_property
    async def default_account(self) -> Optional[BasicPlayer]:
        if await self.default_account_tag:
            return await BasicPlayer(tag=await self.default_account_tag)
        return None
    
    async def set_default_account(self,tag:str):
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        
        if tag not in await self.account_tags:
            raise InvalidTag(tag)

        self.default_account_tag = tag
        await bot_client.coc_db.db__discord_member.update_one(
                {'_id':self.db_id},
                {'$set':{
                    'user_id':self.user_id,
                    'guild_id':self.guild_id,
                    'default_account':await self.default_account_tag
                    }
                },
                upsert=True)

    async def get_nickname(self) -> str:
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        
        await self.refresh_clash_link(force=True)

        default_account = await self.default_account
        
        new_nickname = default_account.name.replace('[AriX]','')
        new_nickname = new_nickname.strip()

        if self.guild_id == 688449973553201335:
            abb_clans = []
            guild_links = await ClanGuildLink.get_for_guild(self.guild_id)
            linked_clans = [link.tag for link in guild_links]
            if len(await self.leader_clans) > 0:
                a_iter = AsyncIter(await self.leader_clans)
                async for c in a_iter:
                    if await c.abbreviation not in abb_clans and len(await c.abbreviation) > 0 and c.tag in linked_clans:
                        abb_clans.append(await c.abbreviation)
            
            else:
                home_clan = await default_account.home_clan
                if home_clan and home_clan.tag in linked_clans:
                    abb_clans.append(await home_clan.abbreviation)
                
                if len(await self.home_clans) > 0:
                    a_iter = AsyncIter(await self.home_clans)
                    async for c in a_iter:
                        if await c.abbreviation not in abb_clans and len(await c.abbreviation) > 0 and c.tag in linked_clans:
                            abb_clans.append(await c.abbreviation)

            if len(abb_clans) > 0:
                new_nickname += f" | {' + '.join(abb_clans)}"
        return new_nickname