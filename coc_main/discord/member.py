import discord
import pendulum
import asyncio

from typing import *
from mongoengine import *

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

class aMember():
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
            self._account_tags = None
            self._scope_clans = None
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
        def _save_to_db():
            db_DiscordMember.objects(
                member_id=user.db_id,
                user_id=user.user_id,
                guild_id=user.guild_id).update_one(
                    set__roles=[str(r.id) for r in user.discord_member.roles if r.is_assignable()],
                    set__last_role_save=pendulum.now().int_timestamp,
                    upsert=True)
            
        user = cls(user_id,guild_id)
        if not user.discord_member:
            raise InvalidUser(user.user_id)
        if not user.guild:
            raise InvalidGuild(user.guild_id)
        
        last_role_sync = await user.get_last_role_sync()
        if not last_role_sync or pendulum.now().int_timestamp - getattr(last_role_sync,'int_timestamp',0) >= 600:
            try:
                await user.sync_clan_roles()
            except CacheNotReady:
                pass
        
        await bot_client.run_in_thread(_save_to_db)
    
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
        def _query_player_tags():
            query = db_Player.objects(discord_user=self.user_id)
            return [db.tag for db in query]
        
        now = pendulum.now().int_timestamp

        async with self._lock:
            if force or (now - getattr(self._last_refreshed,'int_timestamp',0)) > 30:
                self._account_tags = await bot_client.run_in_thread(_query_player_tags)
                
                if self.guild_id:
                    self._scope_clans = [link.tag for link in await ClanGuildLink.get_for_guild(self.guild_id)]
                else:
                    client_cog = bot_client.bot.get_cog('ClashOfClansClient')
                    self._scope_clans = [clan.tag for clan in await client_cog.get_alliance_clans()]
                
                self._last_refreshed = pendulum.now()

        if self.guild_id:
            global_member = aMember(self.user_id)
            await global_member.refresh_clash_link()
        return self

    @property
    def last_attr_refresh(self) -> Optional[pendulum.DateTime]:
        return self._last_refreshed
    
    @property
    def account_tags(self) -> List[str]:
        if not self._last_refreshed:
            raise CacheNotReady()
        return [] if not self._account_tags else self._account_tags
    
    @property
    def accounts(self) -> List[BasicPlayer]:
        ret_players = [
            BasicPlayer(tag=tag) for tag in self.account_tags
            ]
        return sorted(ret_players, key=lambda x:(ClanRanks.get_number(x.alliance_rank),x.town_hall_level,x.exp_level),reverse=True)
    
    @property
    def member_accounts(self) -> List[BasicPlayer]:
        ret_players = [a for a in self.accounts if a.is_member and getattr(a.home_clan,'tag',None) in self._scope_clans]
        return sorted(ret_players, key=lambda x:(ClanRanks.get_number(x.alliance_rank),x.town_hall_level,x.exp_level),reverse=True)

    @property
    def home_clans(self) -> List[aPlayerClan]:
        clan_tags = list(set([a.home_clan.tag for a in self.member_accounts]))
        return [aPlayerClan(tag=tag) for tag in clan_tags]
    
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
        if len(self.home_clans) > 0:
            return True
        return False
    
    @property
    def is_elder(self) -> bool:
        if len(self.elder_clans) > 0:
            return True
        return False

    @property
    def is_coleader(self) -> bool:
        if len(self.coleader_clans) > 0:
            return True
        return False
    
    @property
    def is_leader(self) -> bool:
        if len(self.leader_clans) > 0:
            return True
        return False
    
    @property
    def member_start(self) -> Optional[pendulum.DateTime]:
        if not self.is_member:
            return None
        if min([a.last_joined for a in self.member_accounts]) == 0:
            return pendulum.from_timestamp(1577836800)
        else:
            return pendulum.from_timestamp(min([a.last_joined for a in self.member_accounts]))
    
    @property
    def member_end(self) -> Optional[pendulum.DateTime]:
        if self.is_member:
            return None
        return pendulum.from_timestamp(max([a.last_removed for a in self.accounts]))

    ##################################################
    ### BANK ATTRIBUTES
    ##################################################
    @property
    def last_payday(self) -> Optional[pendulum.DateTime]:
        m = aMember(self.user_id)
        if not m._last_payday:
            db_member = db_DiscordMember.objects(user_id=self.user_id)
            if len(db_member) == 0:
                m._last_payday = None
            elif max([d.last_payday for d in db_member]) == 0:
                m._last_payday = None
            else:
                m._last_payday = max([d.last_payday for d in db_member])
        if m._last_payday:
            return pendulum.from_timestamp(m._last_payday)
        return None
    
    async def set_last_payday(self,timestamp:pendulum.DateTime):
        def _save_to_db():
            db_DiscordMember.objects(
                member_id=self.db_id,
                user_id=self.user_id,
                guild_id=self.guild_id).update_one(
                    set__last_payday=timestamp.int_timestamp,
                    upsert=True
                    )
        m = aMember(self.user_id)
        m._last_payday = timestamp.int_timestamp
        await bot_client.run_in_thread(_save_to_db)

    ##################################################
    ### ROLE ATTRIBUTES & METHODS
    ##################################################
    async def get_last_role_sync(self) -> Optional[pendulum.DateTime]:
        def _get_from_db():
            try:
                db_member = db_DiscordMember.objects.get(
                    user_id=self.user_id,
                    guild_id=self.guild_id
                    )
            except DoesNotExist:
                return None
            else:
                return pendulum.from_timestamp(db_member.last_role_sync)
        
        if not self.discord_member:
            raise InvalidUser(self.user_id)

        i = await bot_client.run_in_thread(_get_from_db)
        if i:
            return i
        return None

    async def restore_user_roles(self) -> Tuple[List[Optional[discord.Role]],List[Optional[discord.Role]]]:
        def _get_saved_roles():
            try:
                db_member = db_DiscordMember.objects.get(user_id=self.user_id,guild_id=self.guild_id)
            except DoesNotExist:
                return []
            else:
                return [int(r) for r in db_member.roles]

        if not self.discord_member:
            raise InvalidUser(self.user_id)
        
        added_roles = []
        failed_roles = []
        
        if not self.guild:
            return added_roles, failed_roles
        
        saved_roles = await bot_client.run_in_thread(_get_saved_roles)
        
        async for role_id in AsyncIter(saved_roles):
            role = self.guild.guild.get_role(int(role_id))
            if role.is_assignable():
                try:
                    await self.discord_member.add_roles(role)
                except (discord.Forbidden,discord.NotFound):
                    failed_roles.append(role)
                else:
                    added_roles.append(role)
        return added_roles, failed_roles

    async def sync_clan_roles(self,context:Optional[Union[discord.Interaction,commands.Context]]=None) -> Tuple[List[Optional[discord.Role]],List[Optional[discord.Role]]]:
        def _update_last_sync():
            db_DiscordMember.objects(
                member_id=self.db_id,
                user_id=self.user_id,
                guild_id=self.guild_id).update_one(
                    set__last_role_sync=pendulum.now().int_timestamp,
                    upsert=True
                    )
            
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

            linked_clans = await ClanGuildLink.get_for_guild(self.guild.id)
            async for link in AsyncIter(linked_clans):
                clan = aPlayerClan(tag=link.tag)

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
            
            await bot_client.run_in_thread(_update_last_sync)
            
        return roles_added, roles_removed
    
    ##################################################
    ### NICKNAME ATTRIBUTES & METHODS
    ##################################################
    @property
    def default_account(self) -> Optional[BasicPlayer]:
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        if len(self.accounts) == 0:
            return None
      
        de = self.member_accounts[0] if len(self.member_accounts) > 0 else self.accounts[0]

        if self.guild_id == 688449973553201335 and not self.is_member:
            return self.accounts[0]

        if not self._default_account:
            try:
                db_member = db_DiscordMember.objects.get(user_id=self.user_id,guild_id=self.guild_id)
                self._default_account = db_member.default_account
            except DoesNotExist:
                pass
        
        if self._default_account and self._default_account in self.account_tags:
            return BasicPlayer(tag=self._default_account)
        else:
            return de
    
    async def set_default_account(self,tag:str):
        def _update_in_db():
            db_DiscordMember.objects(
                member_id=self.db_id,
                user_id=self.user_id,
                guild_id=self.guild_id).update_one(
                    set__default_account=tag,
                    upsert=True
                    )
            bot_client.coc_data_log.info(f"Default Account for {self.user_id} {self.name} in {self.guild_id} {self.guild.name} set to {tag}.")
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        if tag not in self.account_tags:
            raise InvalidTag(tag)

        self._default_account = tag
        await bot_client.run_in_thread(_update_in_db)

    async def get_nickname(self) -> str:
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        
        await self.refresh_clash_link(force=True)
        
        new_nickname = self.default_account.name.replace('[AriX]','')
        new_nickname = new_nickname.strip()

        if self.guild_id == 688449973553201335:
            abb_clans = []
            linked_clans = await ClanGuildLink.get_for_guild(self.guild_id)
            if len(self.leader_clans) > 0:
                [abb_clans.append(c.abbreviation) for c in self.leader_clans if c.abbreviation not in abb_clans and len(c.abbreviation) > 0 and c.tag in [gc.tag for gc in linked_clans]]

            elif len(self.home_clans) > 0:
                if self.default_account.home_clan and self.default_account.home_clan.tag in [gc.tag for gc in linked_clans]:
                    abb_clans.append(self.default_account.home_clan.abbreviation)
                [abb_clans.append(c.abbreviation) for c in self.home_clans if c.abbreviation not in abb_clans and len(c.abbreviation) > 0 and c.tag in [gc.tag for gc in linked_clans]]

            if len(abb_clans) > 0:
                new_nickname += f" | {' + '.join(abb_clans)}"

        return new_nickname