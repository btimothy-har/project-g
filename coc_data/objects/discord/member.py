import discord
import pendulum

from typing import *
from mongoengine import *

from redbot.core import commands
from redbot.core.utils import chat_formatting as chat
from redbot.core.utils import AsyncIter

from coc_client.api_client import BotClashClient

from .guild import aGuild
from ..players.player import aPlayer
from ..players.player_attributes import db_Player
from ..clans.clan import aClan
from ..clans.clan_attributes import db_AllianceClan
from ..discord.clan_link import ClanGuildLink

from ...constants.coc_constants import *
from ...constants.coc_emojis import *
from ...exceptions import *

class db_DiscordMember(Document):
    #ID using format {'guild':int,'user':int}
    member_id = DictField(primary_key=True,required=True)    
    user_id = IntField(required=True)
    guild_id = IntField(required=True)
    default_account = StringField(default="")
    roles = ListField(StringField(),default=[])
    last_role_save = IntField(default=0)
    last_role_sync = IntField(default=0)
    last_payday = IntField(default=0)

##################################################
#####
##### MEMBER OBJECT
#####
##################################################
class aMember():
    def __init__(self,user_id,guild_id=None):
        self.client = BotClashClient()
        self.user_id = user_id
        self.guild_id = guild_id

    def __str__(self):
        return getattr(self.discord_member,'display_name',str(self.user_id))
    
    def __eq__(self,other):
        return isinstance(other,aMember) and self.user_id == other.user_id and self.guild_id == other.guild_id

    @property
    def db_id(self):
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
        
        try:
            db_member = db_DiscordMember.objects.get(
                user_id=user.user_id,
                guild_id=user.guild_id
                )
        except DoesNotExist:            
            db_member = db_DiscordMember(
                member_id=user.db_id,
                user_id=user.user_id,
                guild_id=user.guild_id
                )
        db_member.roles = [str(r.id) for r in user.discord_member.roles if r.is_assignable()]
        db_member.last_role_save = pendulum.now().int_timestamp
        db_member.save()

        # if db_member.last_role_save - db_member.last_role_sync > 600 and random.randint(1, 50) == 1:
        #     await self.sync_clan_roles()
    
    ##################################################
    ### DISCORD MEMBER ATTRIBUTES
    ##################################################
    @property
    def discord_member(self) -> Optional[Union[discord.User,discord.Member]]:
        return self.guild.get_member(self.user_id) if self.guild else self.client.bot.get_user(self.user_id)

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
    ### DISCORD GUILD ATTRIBUTES
    ##################################################
    @property
    def guild(self) -> Optional[discord.Guild]:
        return self.client.bot.get_guild(self.guild_id) if self.guild_id else None
    
    ##################################################
    ### ALLIANCE ATTRIBUTES
    ##################################################
    @property
    def is_member(self):
        if self.guild:
            guild_clan_tags = [i.tag for i in ClanGuildLink.get_guild_links(self.guild_id)]
            member_accounts = db_Player.objects(
                discord_user=self.user_id,
                is_member=True,
                home_clan__in=guild_clan_tags
                )
            if len(list(member_accounts)) > 0:
                return True
        else:
            member_accounts = db_Player.objects(
                discord_user=self.user_id,
                is_member=True
                )
            if len(list(member_accounts)) > 0:
                return True
        return False
    
    @property
    def is_elder(self):
        if self.guild:
            guild_clan_tags = [i.tag for i in ClanGuildLink.get_guild_links(self.guild_id)]
            elder_clans = db_AllianceClan.objects(
                (Q(tag__in=guild_clan_tags) & (
                 Q(elders__in=[self.user_id]) | 
                 Q(coleaders__in=[self.user_id]) |
                 Q(leader=self.user_id))
                ))
            member_accounts = db_Player.objects(
                discord_user=self.user_id,
                is_member=True,
                home_clan__in=[c.tag for c in elder_clans]
                )
            if len(list(member_accounts)) > 0:
                return True
        else:
            elder_clans = db_AllianceClan.objects(
                 Q(elders__in=[self.user_id]) | 
                 Q(coleaders__in=[self.user_id]) |
                 Q(leader=self.user_id))
            member_accounts = db_Player.objects(
                discord_user=self.user_id,
                is_member=True,
                home_clan__in=[c.tag for c in elder_clans]
                )
            if len(list(member_accounts)) > 0:
                return True
        return False

    @property
    def is_coleader(self):
        if self.guild:
            guild_clan_tags = [i.tag for i in ClanGuildLink.get_guild_links(self.guild_id)]
            coleader_clans = db_AllianceClan.objects(
                (Q(tag__in=guild_clan_tags) & (
                 Q(coleaders__in=[self.user_id]) |
                 Q(leader=self.user_id))
                ))
            member_accounts = db_Player.objects(
                discord_user=self.user_id,
                is_member=True,
                home_clan__in=[c.tag for c in coleader_clans]
                )
            if len(list(member_accounts)) > 0:
                return True
        else:
            coleader_clans = db_AllianceClan.objects(
                 Q(coleaders__in=[self.user_id]) |
                 Q(leader=self.user_id))
            member_accounts = db_Player.objects(
                discord_user=self.user_id,
                is_member=True,
                home_clan__in=[c.tag for c in coleader_clans]
                )
            if len(list(member_accounts)) > 0:
                return True
        return False
    
    @property
    def is_leader(self):
        if self.guild:
            guild_clan_tags = [i.tag for i in ClanGuildLink.get_guild_links(self.guild_id)]
            leader_clans = db_AllianceClan.objects(
                (Q(tag__in=guild_clan_tags) & 
                 Q(leader=self.user_id))
                )
            member_accounts = db_Player.objects(
                discord_user=self.user_id,
                is_member=True,
                home_clan__in=[c.tag for c in leader_clans]
                )
            if len(member_accounts) > 0:
                return True
        else:
            leader_clans = db_AllianceClan.objects(
                 Q(leader=self.user_id))
            member_accounts = db_Player.objects(
                discord_user=self.user_id,
                is_member=True,
                home_clan__in=[c.tag for c in leader_clans]
                )
            if len(member_accounts) > 0:
                return True
        return False
    
    ##################################################
    ### CLASH OF CLANS ATTRIBUTES
    ##################################################
    @property
    def account_tags(self):
        query = db_Player.objects(discord_user=self.user_id).only('tag')
        return [db.tag for db in query]
    
    @property
    def accounts(self):
        ret_players = [
            aPlayer.from_cache(tag) for tag in self.account_tags
            ]
        return sorted(ret_players, key=lambda x:(ClanRanks.get_number(x.alliance_rank),x.town_hall.level,x.exp_level),reverse=True)
    
    @property
    def member_accounts(self):
        if self.guild:
            guild_clan_tags = [i.tag for i in ClanGuildLink.get_guild_links(self.guild_id)]
            accounts = db_Player.objects(
                discord_user=self.user_id,
                is_member=True,
                home_clan__in=guild_clan_tags
                )
        else:
            accounts = db_Player.objects(
                discord_user=self.user_id,
                is_member=True
                )
        ret_players = [aPlayer.from_cache(db.tag) for db in accounts]
        return sorted(ret_players, key=lambda x:(ClanRanks.get_number(x.alliance_rank),x.town_hall.level,x.exp_level),reverse=True)

    @property
    def home_clans(self):
        accounts = db_Player.objects(
            discord_user=self.user_id,
            is_member=True
            )
        clan_tags = list(set([a.home_clan for a in accounts]))
        return [aClan.from_cache(tag) for tag in clan_tags]
    
    @property
    def leader_clans(self):
        return [hc for hc in self.home_clans if self.user_id == hc.leader]
    
    @property
    def coleader_clans(self):
        return [hc for hc in self.home_clans if self.user_id in hc.coleaders or self.user_id == hc.leader]
    
    @property
    def elder_clans(self):
        return [hc for hc in self.home_clans if self.user_id in hc.elders or self.user_id in hc.coleaders or self.user_id == hc.leader]
    
    @property
    def member_start(self):
        if not self.is_member:
            return None
        if self.guild:
            guild_clan_tags = [i.tag for i in ClanGuildLink.get_guild_links(self.guild_id)]
            member_accounts = db_Player.objects(
                discord_user=self.user_id,
                is_member=True,
                home_clan__in=guild_clan_tags
                )
            if min([a.last_joined for a in member_accounts]) == 0:
                return pendulum.from_timestamp(1577836800)
            else:
                return pendulum.from_timestamp(min([a.last_joined for a in member_accounts]))
        else:
            member_accounts = db_Player.objects(
                discord_user=self.user_id,
                is_member=True,
                )
            if min([a.last_joined for a in member_accounts]) == 0:
                return pendulum.from_timestamp(1577836800)
            else:
                return pendulum.from_timestamp(min([a.last_joined for a in member_accounts]))
    
    @property
    def member_end(self):
        if self.is_member:
            return None
        if self.guild:
            guild_clan_tags = [i.tag for i in ClanGuildLink.get_guild_links(self.guild_id)]
            ex_member_accounts = db_Player.objects(
                discord_user=self.user_id,
                is_member=False,
                home_clan__in=guild_clan_tags,
                last_removed_gt=0
                )
            if max([a.last_removed for a in ex_member_accounts]) == 0:
                return None
            else:
                return pendulum.from_timestamp(max([a.last_removed for a in ex_member_accounts]))
        else:
            ex_member_accounts = db_Player.objects(
                discord_user=self.user_id,
                is_member=True,
                last_removed_gt=0
                )
            if max([a.last_joined for a in ex_member_accounts]) == 0:
                return None
            else:
                return pendulum.from_timestamp(max([a.last_joined for a in ex_member_accounts]))

    async def fetch_user_links(self):
        linked_accounts = await self.client.get_linked_players(self.user_id)
        async for tag in AsyncIter(linked_accounts):
            try:
                player = await aPlayer.create(tag)
            except InvalidTag:
                continue
            else:
                if player.discord_user == 0:
                    player.discord_user = self.user_id

    ##################################################
    ### BANK ATTRIBUTES
    ##################################################
    @property
    def last_payday(self):
        db_member = db_DiscordMember.objects(user_id=self.user_id)
        if len(db_member) == 0:
            return None
        if max(d.last_payday for d in db_member) == 0:
            return None
        return pendulum.from_timestamp(max(d.last_payday for d in db_member))
    @last_payday.setter
    def last_payday(self,timestamp:int):
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        try:
            db_member = db_DiscordMember.objects.get(user_id=self.user_id,guild_id=self.guild_id)
        except DoesNotExist:
            member_id = {'guild':self.guild_id,'user':self.user_id}
            db_member = db_DiscordMember(
                member_id=member_id,
                user_id=self.user_id,
                guild_id=self.guild_id
                )
        db_member.last_payday = timestamp
        db_member.save()

    ##################################################
    ### ROLE ATTRIBUTES & METHODS
    ##################################################
    @property
    def saved_roles(self):
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        
        try:
            db_member = db_DiscordMember.objects.get(user_id=self.user_id,guild_id=self.guild_id)
        except DoesNotExist:
            return []
        else:
            return [int(r) for r in db_member.roles]
    
    @property
    def last_role_sync(self) -> Optional[pendulum.DateTime]:
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        try:
            db_member = db_DiscordMember.objects.get(user_id=self.user_id,guild_id=self.guild_id)
        except DoesNotExist:
            return None
        else:
            if db_member.last_role_sync == 0:
                return None
            return pendulum.from_timestamp(db_member.last_role_sync)

    async def restore_user_roles(self):
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        
        added_roles = []
        failed_roles = []
        
        if not self.guild:
            return added_roles, failed_roles
        
        async for role_id in AsyncIter(self.saved_roles):
            role = self.guild.get_role(int(role_id))
            if role.is_assignable():
                try:
                    await self.discord_member.add_roles(role)
                except (discord.Forbidden,discord.NotFound):
                    failed_roles.append(role)
                else:
                    added_roles.append(role)
        return added_roles, failed_roles

    async def sync_clan_roles(self,context:Optional[Union[discord.Interaction,commands.Context]]=None) -> Tuple[List[discord.Role],List[discord.Role]]:
        roles_added = []
        roles_removed = []
 
        if not self.discord_member:
            raise InvalidUser(self.user_id)

        if not self.guild:
            return roles_added, roles_removed
        
        guild = aGuild(self.guild_id)

        try:
            db_member = db_DiscordMember.objects.get(user_id=self.user_id,guild_id=self.guild_id)
        except DoesNotExist:
            db_member = db_DiscordMember(
                member_id=self.db_id,
                user_id=self.user_id,
                guild_id=self.guild_id
                )        
        db_member.last_role_sync = pendulum.now().int_timestamp
        db_member.save()

        if self.guild_id == 1132581106571550831:
            global_member = aMember(self.user_id)
            if global_member.is_member:
                clan_member_role = self.guild.get_role(1139855695068540979)
                if clan_member_role not in self.discord_member.roles:
                    roles_added.append(clan_member_role)

            if not global_member.is_member:                
                if clan_member_role in self.discord_member.roles:
                    roles_removed.append(clan_member_role)

        async for clan in AsyncIter(guild.clans):
            clan_link = ClanGuildLink.get_link(clan.tag,self.guild_id)

            if clan.tag in [c.tag for c in self.home_clans]:
                is_elder = False
                is_coleader = False

                if self.user_id == clan.leader or self.user_id in clan.coleaders:
                    is_elder = True
                    is_coleader = True
                elif self.user_id in clan.elders:
                    is_elder = True
                
                if clan_link.member_role:
                    if clan_link.member_role not in self.discord_member.roles:
                        roles_added.append(clan_link.member_role)
                
                if clan_link.elder_role:
                    if is_elder:
                        if clan_link.elder_role not in self.discord_member.roles:
                            roles_added.append(clan_link.elder_role)
                    else:
                        if clan_link.elder_role in self.discord_member.roles:
                            roles_removed.append(clan_link.elder_role)
                
                if clan_link.coleader_role:
                    if is_coleader:
                        if clan_link.coleader_role not in self.discord_member.roles:
                            roles_added.append(clan_link.coleader_role)
                    else:
                        if clan_link.coleader_role in self.discord_member.roles:
                            roles_removed.append(clan_link.coleader_role)

            else:
                if clan_link.member_role:
                    if clan_link.member_role in self.discord_member.roles:
                        roles_removed.append(clan_link.member_role)
                if clan_link.elder_role:
                    if clan_link.elder_role in self.discord_member.roles:
                        roles_removed.append(clan_link.elder_role)
                if clan_link.coleader_role:
                    if clan_link.coleader_role in self.discord_member.roles:
                        roles_removed.append(clan_link.coleader_role)

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
                self.client.cog.coc_main_log.exception(f"Error adding roles to {self.discord_member.name} {self.discord_member.id}.")
            else:
                self.client.cog.coc_main_log.info(f"[{self.guild.name} {self.guild.id}] [{self.discord_member.name} {self.discord_member.id}] Roles Added: {chat.humanize_list([r.name for r in roles_added])}. Initiated by {initiating_user} from {initiating_command}.")
                
        if len(roles_removed) > 0:
            try:
                await self.discord_member.remove_roles(*roles_removed)
            except discord.Forbidden:
                self.client.cog.coc_main_log.exception(f"Error removing roles from {self.discord_member.name} {self.discord_member.id}.")
            else:
                self.client.cog.coc_main_log.info(f"[{self.guild.name} {self.guild.id}] [{self.discord_member.name} {self.discord_member.id}] Roles Removed: {chat.humanize_list([r.name for r in roles_removed])}. Initiated by {initiating_user} from {initiating_command}.")
        
        return roles_added, roles_removed
    
    ##################################################
    ### NICKNAME ATTRIBUTES & METHODS
    ##################################################
    @property
    def default_account(self):
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        if len(self.accounts) == 0:
            return None
        de = self.member_accounts[0] if len(self.member_accounts) > 0 else self.accounts[0]
        try:
            db_member = db_DiscordMember.objects.get(user_id=self.user_id,guild_id=self.guild_id)
        except DoesNotExist:
            return de
        if db_member.default_account and db_member.default_account in self.account_tags:
            return aPlayer.from_cache(db_member.default_account)
        else:
            return de
    @default_account.setter
    def default_account(self,account_tag:str):
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        if account_tag not in self.account_tags:
            raise InvalidTag(account_tag)
        try:
            db_member = db_DiscordMember.objects.get(user_id=self.user_id,guild_id=self.guild_id)
        except DoesNotExist:
            member_id = {'guild':self.guild_id,'user':self.user_id}
            db_member = db_DiscordMember(
                member_id=member_id,
                user_id=self.user_id,
                guild_id=self.guild_id
                )
        db_member.default_account = account_tag
        db_member.save()

    async def get_nickname(self):
        if not self.discord_member:
            raise InvalidUser(self.user_id)
        
        new_nickname = self.default_account.name.replace('[AriX]','')
        new_nickname = new_nickname.strip()
        
        abb_clans = []
        guild = aGuild(self.guild.id)
        if len(self.leader_clans) > 0:
            [abb_clans.append(c.abbreviation) for c in self.leader_clans if c.abbreviation not in abb_clans and len(c.abbreviation) > 0 and c.tag in [gc.tag for gc in guild.clans]]
        elif len(self.home_clans) > 0:
            [abb_clans.append(c.abbreviation) for c in self.home_clans if c.abbreviation not in abb_clans and len(c.abbreviation) > 0 and c.tag in [gc.tag for gc in guild.clans]]

        if len(abb_clans) > 0:
            new_nickname += f" | {' + '.join(abb_clans)}"
        return new_nickname