import discord
import pendulum
import asyncio
import logging

from typing import *
from collections import defaultdict

from async_property import AwaitLoader
from redbot.core import commands
from redbot.core.utils import chat_formatting as chat
from redbot.core.utils import AsyncIter

from ..client.global_client import GlobalClient
from ..coc_objects.players.base_player import BasicPlayer
from ..coc_objects.clans.clan import _PlayerClan

from ..exceptions import InvalidUser, InvalidGuild
from ..utils.constants.coc_constants import ClanRanks, MultiplayerLeagues

from .clan_link import ClanGuildLink

LOG = logging.getLogger("coc.main")

class aMember(GlobalClient,AwaitLoader):
    _master_scope = {}
    _rk_members = set()
    _rk_elders = set()
    _rk_coleaders = set()
    _rk_leaders = set()
    _role_lock = defaultdict(asyncio.Lock)
    _payday_lock = defaultdict(asyncio.Lock)

    __slots__ = [
        '_is_new',
        '_lock',
        '_scope_clans'
        'user_id',
        'guild_id',
        'accounts',
        'is_member',
        'is_elder',
        'is_coleader',
        'is_leader'
        'last_role_sync'
        ]
    
    @classmethod
    async def _update_scopes(cls):
        guilds = cls.bot.guilds
        guild_iter = AsyncIter(guilds)
        async for guild in guild_iter:
            cls._master_scope[guild.id] = [link.tag for link in await ClanGuildLink.get_for_guild(guild.id)]
        
        cls._master_scope['global'] = [clan.tag for clan in await cls.coc_client.get_alliance_clans()]
        cls._master_scope['timestamp'] = pendulum.now().int_timestamp

    def __init__(self,user_id:int,guild_id:Optional[int]=None):
        self.user_id = user_id
        self.guild_id = guild_id

        self._scope_clans = aMember._master_scope.get(self.guild_id,[]) if self.guild_id else aMember._master_scope.get('global',[])

        self.accounts = []
        self.is_member = (self.user_id,self.guild_id) in list(aMember._rk_members)
        self.is_elder = (self.user_id,self.guild_id) in list(aMember._rk_elders)
        self.is_coleader = (self.user_id,self.guild_id) in list(aMember._rk_coleaders)
        self.is_leader = (self.user_id,self.guild_id) in list(aMember._rk_leaders)

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
    
    @property
    def role_lock(self) -> asyncio.Lock:
        return self._role_lock[self.user_id]    
    @property
    def payday_lock(self) -> asyncio.Lock:
        return self._payday_lock[self.user_id]
        
    async def load(self):
        rts = pendulum.from_timestamp(aMember._master_scope.get('timestamp',pendulum.now().subtract(hours=3).int_timestamp))
        if pendulum.now().int_timestamp - rts.int_timestamp > 3600:
            await aMember._update_scopes()

        self._scope_clans = aMember._master_scope.get(self.guild_id,[]) if self.guild_id else aMember._master_scope.get('global',[])
        query = self.database.db__player.find(
            {'discord_user':self.user_id},
            {'_id':1,'is_member':1,'home_clan':1}
            )
        
        account_tags = [db.get('_id',None) async for db in query]
        self.accounts = [await BasicPlayer(p) for p in account_tags if p is not None]
        #sort by TH, exp level, alliance rank
        try:
            self.accounts.sort(
                key=lambda x: (x.town_hall_level,x.exp_level,x.clean_name),
                reverse=True
                )
        except:
            pass

        if len(self.member_accounts) > 0:
            self.is_member = True
            aMember._rk_members.add((self.user_id,self.guild_id))
        elif self.is_member:
            self.is_member = False
            aMember._rk_members.discard((self.user_id,self.guild_id))
        
        if len(self.elder_clans) > 0:
            self.is_elder = True
            aMember._rk_elders.add((self.user_id,self.guild_id))
        elif self.is_elder:
            self.is_elder = False
            aMember._rk_elders.discard((self.user_id,self.guild_id))
        
        if len(self.coleader_clans) > 0:
            self.is_coleader = True
            aMember._rk_coleaders.add((self.user_id,self.guild_id))
        elif self.is_coleader:
            self.is_coleader = False
            aMember._rk_coleaders.discard((self.user_id,self.guild_id))
        
        if len(self.leader_clans) > 0:
            self.is_leader = True
            aMember._rk_leaders.add((self.user_id,self.guild_id))
        elif self.is_leader:
            self.is_leader = False
            aMember._rk_leaders.discard((self.user_id,self.guild_id))
    
    ##################################################
    ### DISCORD MEMBER ATTRIBUTES
    ##################################################
    @property
    def guild(self) -> Optional[discord.Guild]:
        return self.bot.get_guild(self.guild_id) if self.guild_id else None
        
    @property
    def discord_member(self) -> Optional[Union[discord.User,discord.Member]]:
        if self.guild:
            return self.guild.get_member(self.user_id)
        return self.bot.get_user(self.user_id)

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
    def member_accounts(self) -> List[BasicPlayer]:
        mem = [a for a in self.accounts if a.is_member and getattr(a.home_clan,'tag',None) in self._scope_clans]
        mem.sort(
            key=lambda x: (ClanRanks.get_number(x.alliance_rank),x.town_hall_level,x.exp_level),
            reverse=True
            )
        return mem
    @property
    def member_tags(self) -> List[str]:
        return [a.tag for a in self.member_accounts]
    @property
    def home_clans(self) -> List[BasicPlayer]:
        accounts = self.member_accounts
        mem = []
        for a in accounts:
            if a.home_clan.tag not in [c.tag for c in mem]:
                mem.append(a.home_clan)
        mem.sort(
            key=lambda x:(x.level, MultiplayerLeagues.get_index(x.war_league_name), x.capital_hall),
            reverse=True
            )
        return mem
    @property
    def leader_clans(self) -> List[_PlayerClan]:
        return [hc for hc in self.home_clans if self.user_id == hc.leader]    
    @property
    def coleader_clans(self) -> List[_PlayerClan]:
        return [hc for hc in self.home_clans if self.user_id in hc.coleaders or self.user_id == hc.leader]    
    @property
    def elder_clans(self) -> List[_PlayerClan]:
        return [hc for hc in self.home_clans if self.user_id in hc.elders or self.user_id in hc.coleaders or self.user_id == hc.leader]

    ##################################################
    ### BANK ATTRIBUTES
    ##################################################
    async def get_last_payday(self) -> Optional[pendulum.DateTime]:
        query = await self.database.db__discord_member.find(
            {'_id':self.db_id},
            {'_id':1,'guild_id':1,'last_payday':1}
            ).to_list(length=None)        
        db_lastpayday = [db.get('last_payday',0) for db in query]

        last_payday = pendulum.from_timestamp(max(db_lastpayday)) if len(db_lastpayday) > 0 else None
        return last_payday
        
    async def set_last_payday(self,timestamp:pendulum.DateTime):
        last_payday = timestamp
        await self.database.db__discord_member.update_one(
            {'_id':self.db_id},
            {'$set':{
                'user_id':self.user_id,
                'guild_id':self.guild_id,
                'last_payday':getattr(last_payday,'int_timestamp',None)
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
        
        await user.sync_clan_roles()
     
    async def restore_user_roles(self) -> Tuple[List[Optional[discord.Role]],List[Optional[discord.Role]]]:
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        
        added_roles = []
        failed_roles = []        
        if not self.guild:
            return added_roles, failed_roles
        
        async with self.role_lock:
            db_saved_roles = await self.database.db__discord_member.find_one({'_id':self.db_id})
            saved_roles = db_saved_roles.get('roles',[]) if db_saved_roles else []

            r_iter = AsyncIter(saved_roles)
            async for role_id in r_iter:
                role = self.guild.get_role(int(role_id))
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
            db_last_sync = await self.database.db__discord_member.find_one({'_id':self.db_id})
            ls = db_last_sync.get('last_role_sync',None) if db_last_sync else None
            
            if ls and pendulum.now().int_timestamp - ls < 600:
                return roles_added, roles_removed
    
        async with self.role_lock:
            #Assassins guild Member Role
            if self.guild.id == 1132581106571550831:
                global_member = await aMember(self.user_id)
                clan_member_role = self.guild.get_role(1139855695068540979)
                
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
                    pass
                except Exception:
                    LOG.exception(f"Error adding roles to {self.discord_member.name} {self.discord_member.id}.")
                else:
                    LOG.info(
                        f"[{self.guild.name} {self.guild.id}] [{self.discord_member.name} {self.discord_member.id}] Roles Added: {chat.humanize_list([r.name for r in roles_added])}. "
                        + f"Initiated by {initiating_user} from {initiating_command}."
                        )
                    
            if len(roles_removed) > 0:
                try:
                    await self.discord_member.remove_roles(*roles_removed,reason=f"Clan Role Sync: {initiating_user} from {initiating_command}")
                except discord.Forbidden:
                    pass
                except Exception:
                    LOG.exception(f"Error removing roles from {self.discord_member.name} {self.discord_member.id}.")
                else:
                    LOG.info(
                        f"[{self.guild.name} {self.guild.id}] [{self.discord_member.name} {self.discord_member.id}] Roles Removed: {chat.humanize_list([r.name for r in roles_removed])}. "
                        + f"Initiated by {initiating_user} from {initiating_command}."
                        )
            
            await self.database.db__discord_member.update_one(
                {'_id':self.db_id},
                {'$set':{
                    'user_id':self.user_id,
                    'guild_id':self.guild_id,
                    'roles':[str(r.id) for r in self.discord_member.roles if r.is_assignable()],
                    'last_role_save':pendulum.now().int_timestamp,
                    'last_role_sync':pendulum.now().int_timestamp,
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
        db = await self.database.db__discord_member.find_one({'_id':self.db_id})
        if db and db.get('default_account',None) and db.get('default_account',None) in self.account_tags:
            def_tag = db['default_account']

        #ARIX
        if self.guild_id == 688449973553201335:
            if not self.is_member:
                return self.accounts[0].tag
            if def_tag in self.member_tags:
                return def_tag
            return self.member_tags[0]        
        
        if def_tag:
            return def_tag        
        return self.accounts[0].tag
    
    async def set_default_account(self,tag:str):
        if not self.discord_member:
            raise InvalidUser(self.user_id)

        await self.database.db__discord_member.update_one(
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
            raise InvalidUser()
        
        default_tag = await self._get_default_account_tag()
        default_account = await self.coc_client.get_player(default_tag) if default_tag else None

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
    
    ##################################################
    ### REWARD ACCOUNT ATTRIBUTES & METHODS
    ##################################################
    async def _get_reward_account_tag(self) -> Optional[str]:
        if not self.discord_member:
            raise InvalidUser()
        
        global_member = await aMember(self.user_id)
        
        guild_member = aMember(self.user_id,1132581106571550831)
        if len(global_member.accounts) == 0:
            return None
        
        def_tag = None
        db = await self.database.db__discord_member.find_one({'_id':guild_member.db_id})
        if db and db.get('reward_account',None):
            if db.get('reward_account',None) in global_member.member_tags:
                def_tag = db['reward_account']

        if def_tag:
            return def_tag
        
        mem = [a for a in global_member.accounts if a.is_member]
        if len(mem) == 0:
            return None
        mem.sort(
            key=lambda x: (x.town_hall_level,x.exp_level),
            reverse=True
            )
        return mem[0].tag
    
    async def get_reward_timer(self) -> Optional[pendulum.DateTime]:
        if not self.discord_member:
            raise InvalidUser()

        guild_member = aMember(self.user_id,1132581106571550831)
        db = await self.database.db__discord_member.find_one({'_id':guild_member.db_id})
        last_updated = db.get('last_reward_account',0) if db else 0

        last_u_ts = pendulum.from_timestamp(last_updated)
        return last_u_ts.add(hours=168)
    
    async def set_reward_account(self,tag:str) -> Tuple[bool, int]:
        if not self.discord_member:
            raise InvalidUser()

        global_member = await aMember(self.user_id)
        
        if tag not in global_member.account_tags:
            raise ValueError(f"{tag} is not a valid account tag for {self.user_id}.")
        
        guild_member = aMember(self.user_id,1132581106571550831)
        db = await self.database.db__discord_member.find_one({'_id':guild_member.db_id})
        last_updated = db.get('last_reward_account',0) if db else 0

        if last_updated > 0:
            last_u = pendulum.from_timestamp(last_updated)
            diff = pendulum.now() - last_u
            if diff.in_hours() < 168:
                return False, last_updated

        await self.database.db__discord_member.update_one(
            {'_id':guild_member.db_id},
            {'$set':{
                'user_id':self.user_id,
                'guild_id':self.guild_id,
                'reward_account':tag,
                'last_reward_account':pendulum.now().int_timestamp
                }
            },
            upsert=True)
        return True, last_updated