import pendulum
import discord

from typing import *
from mongoengine import *

from coc_client.api_client import BotClashClient
from ..discord.clan_link import ClanGuildLink

from ...constants.coc_emojis import *
from ...constants.ui_emojis import *
from ...constants.coc_constants import *
from ...exceptions import *

from ...utilities.utils import *

bot_client = BotClashClient()

feed_description = {
    1: "Member Join/Leave",
    2: "Donation Log",
    3: "Raid Weekend Results",
    4: "Capital Contribution"
    }

##################################################
#####
##### DATABASE
#####
##################################################
class db_Clan(Document):
    tag = StringField(primary_key=True,required=True)
    abbreviation = StringField(default="")
    emoji = StringField(default="")
    unicode_emoji = StringField(default="")

    name = StringField(default="")
    badge = StringField(default="")
    level = IntField(default=0)
    capital_hall = IntField(default=0)
    war_league = StringField(default="")

class db_AllianceClan(Document):
    tag = StringField(primary_key=True,required=True)
    description = StringField(default="")
    recruitment_level = ListField(IntField(),default=[])
    recruitment_info = StringField(default="")
    leader = IntField(default=0)
    coleaders = ListField(IntField(),default=[])
    elders = ListField(IntField(),default=[])
    
    #deprecated
    announcement_channel = IntField(default=0)
    member_role = IntField(default=0)
    home_guild = IntField(default=0)
    elder_role = IntField(default=0)
    coleader_role = IntField(default=0)

class db_WarLeagueClanSetup(Document):
    tag = StringField(primary_key=True,required=True)
    is_active = BooleanField(default=False)
    role = IntField(default=0)
    channel = IntField(default=0)

    #deprecated
    webhook = IntField(default=0)

class db_ClanDataFeed(Document):
    #1 - member feed
    #2 - donation feed
    #3 - raid weekend results
    #4 - capital contribution
    tag = StringField(required=True)
    type = IntField(required=True)
    guild_id = IntField(required=True)
    channel_id = IntField(required=True)

class db_ClanEventReminder(Document):
    #type 1 - war
    #type 2 - raid
    #subtype (only for war) - random, friendly, cwl
    tag = StringField(required=True)
    type = IntField(required=True)
    sub_type = ListField(StringField(),default=[])
    guild_id = IntField(required=True)
    channel_id = IntField(required=True)
    reminder_interval = ListField(IntField(),default=[])
    interval_tracker = ListField(IntField(),default=[])

##################################################
#####
##### BASIC CLAN
#####
##################################################
class BasicClan():
    """
    This is a Clan wrapper for Project G Clan attributes and methods.

    Inheriting from this Class: aClan, WarLeagueClan
    """
    def __init__(self,**kwargs):
        self.timestamp = pendulum.now()

        self.tag = kwargs.get('tag',None)
        self.name = kwargs.get('name','No Clan')
        self.badge = ""
        self.level = 0
        self.capital_hall = 0
        self.war_league_name = ""

        if self.tag:
            self.tag = coc.utils.correct_tag(self.tag)
            self.name = self.cached_name
            self.badge = self.cached_badge
            self.level = self.cached_level
            self.capital_hall = self.cached_capital_hall
            self.war_league_name = self.cached_war_league

            bot_client.clan_cache.add_to_queue(self.tag)

    def __str__(self):
        return f"Clan {self.tag} {self.name}"

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
    
    async def get_full_clan(self):
        return await bot_client.cog.fetch_clan(self.tag)
    
    ##################################################
    #####
    ##### CACHED VALUES
    #####
    ##################################################
    @property
    def cached_name(self) -> str:
        return getattr(self.database_attributes,'name',"")
    @cached_name.setter
    def cached_name(self,new_name:str):
        db_Clan.objects(tag=self.tag).update_one(set__name=new_name, upsert=True)
        bot_client.cog.coc_data_log.debug(f"{self}: cached_name changed to {new_name}.")    
    
    @property
    def cached_badge(self) -> str:
        return getattr(self.database_attributes,'badge',"")
    @cached_badge.setter
    def cached_badge(self,new_badge:str):
        db_Clan.objects(tag=self.tag).update_one(set__badge=new_badge, upsert=True)
        bot_client.cog.coc_data_log.debug(f"{self}: cached_badge changed to {new_badge}.")

    @property
    def cached_level(self) -> int:
        return getattr(self.database_attributes,'level',0)
    @cached_level.setter
    def cached_level(self,new_level:int):
        db_Clan.objects(tag=self.tag).update_one(set__level=new_level, upsert=True)
        bot_client.cog.coc_data_log.debug(f"{self}: cached_level changed to {new_level}.")
    
    @property
    def cached_capital_hall(self) -> int:
        return getattr(self.database_attributes,'capital_hall',0)
    @cached_capital_hall.setter
    def cached_capital_hall(self,new_level:int):
        db_Clan.objects(tag=self.tag).update_one(set__capital_hall=new_level, upsert=True)
        bot_client.cog.coc_data_log.debug(f"{self}: cached_capital_hall changed to {new_level}.")
    
    @property
    def cached_war_league(self) -> str:
        return getattr(self.database_attributes,'war_league',"")
    @cached_war_league.setter
    def cached_war_league(self,new_name:str):
        db_Clan.objects(tag=self.tag).update_one(set__war_league=new_name, upsert=True)
        bot_client.cog.coc_data_log.debug(f"{self}: cached_war_league changed to {new_name}.")
    
    ##################################################
    #####
    ##### DISPLAY / FORMATTED ATTRIBUTES
    #####
    ##################################################
    @property
    def title(self):
        return f"{self.emoji} {self.name} ({self.tag})" if self.emoji else f"{self.name} ({self.tag})"

    ##################################################
    #####
    ##### GENERIC CLAN ATTRIBUTES
    #####
    ##################################################
    @property
    def database_attributes(self) -> Optional[db_Clan]:
        try:
            return db_Clan.objects.get(tag=self.tag)
        except DoesNotExist:
            return None
        
    @property
    def is_registered_clan(self) -> bool:
        return True if len(getattr(self.database_attributes,'emoji','')) > 0 else False
    
    @property
    def abbreviation(self) -> str:
        return getattr(self.database_attributes,'abbreviation',"")
    @abbreviation.setter
    def abbreviation(self,new_abbreviation:str):
        db_Clan.objects(tag=self.tag).update_one(set__abbreviation=new_abbreviation.upper(), upsert=True)
        bot_client.cog.coc_data_log.info(f"{self}: abbreviation changed to {new_abbreviation.upper()}.")
    
    @property
    def _emoji(self) -> str:
        return getattr(self.database_attributes,'emoji',"")
    @_emoji.setter
    def _emoji(self,new_emoji:str):
        db_Clan.objects(tag=self.tag).update_one(set__emoji=new_emoji, upsert=True)
        bot_client.cog.coc_data_log.info(f"{self}: emoji changed to {new_emoji}.")
    
    @property
    def emoji(self) -> str:
        return self._emoji
    @emoji.setter
    def emoji(self,new_emoji:str):
        self._emoji = new_emoji
    
    @property
    def unicode_emoji(self) -> str:
        return getattr(self.database_attributes,'unicode_emoji',"")
    @unicode_emoji.setter
    def unicode_emoji(self,new_emoji:str):
        db_Clan.objects(tag=self.tag).update_one(set__unicode_emoji=new_emoji, upsert=True)
        bot_client.cog.coc_data_log.info(f"{self}: unicode emoji changed to {new_emoji}.")
    
    ##################################################
    #####
    ##### ALLIANCE / FAMILY CLAN ATTRIBUTES
    #####
    ##################################################    
    @property
    def alliance_members(self) -> List['BasicPlayer']:
        return bot_client.cog.get_members_by_season(self)
    
    @property
    def alliance_member_count(self):
        return len(self.alliance_members)
    
    @property
    def alliance_attributes(self) -> Optional[db_AllianceClan]:
        try:
            return db_AllianceClan.objects.get(tag=self.tag)
        except DoesNotExist:
            return None
               
    @property
    def is_alliance_clan(self) -> bool:
        return True if self.alliance_attributes else False

    @property
    def custom_description(self) -> str:
        return getattr(self.alliance_attributes,'description',"")
    @custom_description.setter
    def custom_description(self,new_description:str):
        db_AllianceClan.objects(tag=self.tag).update_one(set__description=new_description, upsert=False)
        bot_client.cog.coc_data_log.info(f"{self}: custom description changed to {new_description}.")

    @property
    def recruitment_level(self) -> list[int]:
        i = getattr(self.alliance_attributes,'recruitment_level',[])
        return sorted(i)
    @recruitment_level.setter
    def recruitment_level(self,recruitment_levels:list[int]):
        db_AllianceClan.objects(tag=self.tag).update_one(set__recruitment_level=sorted(recruitment_levels), upsert=False)
        bot_client.cog.coc_data_log.info(f"{self}: recruitment level changed to {sorted(recruitment_levels)}.")
    @property
    def max_recruitment_level(self) -> int:
        return max(self.recruitment_level) if len(self.recruitment_level) > 0 else 0
    @property
    def recruitment_level_emojis(self) -> str:
        return " ".join([EmojisTownHall.get(th_level) for th_level in self.recruitment_level])
    
    @property
    def recruitment_info(self) -> str:
        return getattr(self.alliance_attributes,'recruitment_info',"")
    @recruitment_info.setter
    def recruitment_info(self,new_recruitment_info:str):
        db_AllianceClan.objects(tag=self.tag).update_one(set__recruitment_info=new_recruitment_info, upsert=False)
        bot_client.cog.coc_data_log.info(f"{self}: recruitment info changed to {new_recruitment_info}.")
    
    @property
    def leader(self) -> int:
        return getattr(self.alliance_attributes,'leader',0)    
    async def new_leader(self,new_leader:int):
        if new_leader == self.leader:
            return
        await self.new_coleader(self.leader,force=True)
        db_AllianceClan.objects(tag=self.tag).update_one(set__leader=new_leader, upsert=True)
        bot_client.cog.coc_data_log.info(f"{self}: new leader {new_leader} added.")

        if new_leader in self.coleaders:
            await self.remove_coleader(new_leader)
        if new_leader in self.elders:
            await self.remove_elder(new_leader)
    
    @property
    def coleaders(self) -> list[int]:
        i = getattr(self.alliance_attributes,'coleaders',[])
        return list(set(i))
    
    async def new_coleader(self,new_coleader:int,force=False):
        if not force:
            if new_coleader == self.leader:
                return
        
        if new_coleader not in self.coleaders:
            db_AllianceClan.objects(tag=self.tag).update_one(push__coleaders=new_coleader, upsert=False)
            bot_client.cog.coc_data_log.info(f"{self}: new coleader {new_coleader} added.")

            if new_coleader in self.elders:
                await self.remove_elder(new_coleader)

    async def remove_coleader(self,coleader:int):
        if coleader in self.coleaders:
            db_AllianceClan.objects(tag=self.tag).update_one(pull__coleaders=coleader, upsert=False)
            bot_client.cog.coc_data_log.info(f"{self}: coleader {coleader} removed.")
    
    @property
    def elders(self) -> list[int]:
        i = getattr(self.alliance_attributes,'elders',[])
        return list(set(i))
    
    async def new_elder(self,new_elder:int):
        if new_elder == self.leader:
            return
        
        if new_elder not in self.elders:
            db_AllianceClan.objects(tag=self.tag).update_one(push__elders=new_elder, upsert=False)
            bot_client.cog.coc_data_log.info(f"{self}: new elder {new_elder} added.")

            if new_elder in self.coleaders:
                await self.remove_coleader(new_elder)

    async def remove_elder(self,elder:int):
        if elder in self.elders:
            db_AllianceClan.objects(tag=self.tag).update_one(pull__elders=elder, upsert=False)
            bot_client.cog.coc_data_log.info(f"{self}: elder {elder} removed.")
    
    ##################################################
    #####
    ##### BANK HELPERS
    #####
    ##################################################     
    @property
    def bank_account(self):
        bank_cog = self.client.bot.get_cog("Bank")
        if not bank_cog or not self.is_alliance_clan:
            return None
        return bank_cog.get_clan_account(self)
    
    @property
    def balance(self):
        return getattr(self.bank_account,'balance',0)
    
    ##################################################
    #####
    ##### DISCORD INTERACTIONS
    #####
    ##################################################
    @property
    def linked_servers(self) -> list[ClanGuildLink]:
        return ClanGuildLink.get_clan_links(self.tag)
    
    @property
    def discord_feeds(self) -> list[db_ClanDataFeed]:
        return db_ClanDataFeed.objects(tag=self.tag)
    
    @property
    def member_feed(self) -> list[db_ClanDataFeed]:
        return db_ClanDataFeed.objects(tag=self.tag,type=1)
    
    @property
    def donation_feed(self) -> list[db_ClanDataFeed]:
        return db_ClanDataFeed.objects(tag=self.tag,type=2)
    
    @property
    def capital_raid_results_feed(self) -> list[db_ClanDataFeed]:
        return db_ClanDataFeed.objects(tag=self.tag,type=3)

    @property
    def capital_contribution_feed(self) -> list[db_ClanDataFeed]:
        return db_ClanDataFeed.objects(tag=self.tag,type=4)

    async def create_feed(self,
        type:int,
        channel:Union[discord.TextChannel,discord.Thread]):
        if type not in [1,2,3,4]:
            return
        new_feed = db_ClanDataFeed(
            tag=self.tag,
            type=type,
            guild_id=channel.guild.id,
            channel_id=channel.id
            )
        new_feed.save()

    async def delete_feed(self,feed_id):
        try:
            feed = db_ClanDataFeed.objects.get(id=feed_id)
        except DoesNotExist:
            pass
        else:
            feed.delete()
    
    @property
    def clan_war_reminders(self) -> list[db_ClanEventReminder]:
        return db_ClanEventReminder.objects(tag=self.tag,type=1)
    
    @property
    def capital_raid_reminders(self) -> list[db_ClanEventReminder]:
        return db_ClanEventReminder.objects(tag=self.tag,type=2)
    
    async def create_clan_war_reminder(self,
        channel:Union[discord.TextChannel,discord.Thread],
        war_types:list[str],
        interval:list[int]):

        valid_types = ['random','cwl','friendly']
        wt = [w for w in war_types if w in valid_types]
        intv = sorted([int(i) for i in interval],reverse=True)
        new_reminder = db_ClanEventReminder(
            tag=self.tag,
            type=1,
            sub_type=wt,
            guild_id=channel.guild.id,
            channel_id=channel.id,
            reminder_interval=intv
            )
        new_reminder.save()
    
    async def create_capital_raid_reminder(self,
        channel:Union[discord.TextChannel,discord.Thread],
        interval:list[int]):

        intv = sorted([int(i) for i in interval],reverse=True)
        new_reminder = db_ClanEventReminder(
            tag=self.tag,
            type=2,
            guild_id=channel.guild.id,
            channel_id=channel.id,
            reminder_interval=intv
            )
        new_reminder.save()
    
    async def delete_reminder(self,reminder_id):
        try:
            reminder = db_ClanEventReminder.objects.get(id=reminder_id)
        except DoesNotExist:
            pass
        else:
            reminder.delete()

    ##################################################
    #####
    ##### CLAN CWL ATTRIBUTES
    #####
    ##################################################    
    @property
    def league_clan_setup(self) -> Optional[db_WarLeagueClanSetup]:    
        try:
            return db_WarLeagueClanSetup.objects.get(tag=self.tag)
        except DoesNotExist:
            return None
    
    @property
    def is_active_league_clan(self) -> bool:
        return getattr(self.league_clan_setup,'is_active',False)
    @is_active_league_clan.setter
    def is_active_league_clan(self,new_value:bool):
        db_WarLeagueClanSetup.objects(tag=self.tag).update_one(set__is_active=new_value, upsert=True)
        bot_client.cog.coc_data_log.info(f"{self}: is_active_league_clan changed to {new_value}.")

    @property
    def league_clan_channel(self) -> Optional[Union[discord.TextChannel,discord.Thread]]:
        channel_id = getattr(self.league_clan_setup,'channel',0)
        channel = bot_client.bot.get_channel(channel_id)
        if isinstance(channel,(discord.TextChannel,discord.Thread)):
            return channel
        return None
    @league_clan_channel.setter
    def league_clan_channel(self,new_channel:Union[discord.TextChannel,discord.Thread]):
        db_WarLeagueClanSetup.objects(tag=self.tag).update_one(set__channel=new_channel.id, upsert=True)
        bot_client.cog.coc_data_log.info(f"{self}: league_clan_channel changed to {new_channel.id}.")
    
    @property
    def league_clan_role(self) -> Optional[discord.Role]:
        role_id = getattr(self.league_clan_setup,'role',0)
        for guild in bot_client.bot.guilds:
            role = guild.get_role(role_id)
            if isinstance(role,discord.Role):
                return role
        return None
    @league_clan_role.setter
    def league_clan_role(self,new_role:discord.Role):
        db_WarLeagueClanSetup.objects(tag=self.tag).update_one(set__role=new_role.id, upsert=True)
        bot_client.cog.coc_data_log.info(f"{self}: league_clan_role changed to {new_role.id}.")