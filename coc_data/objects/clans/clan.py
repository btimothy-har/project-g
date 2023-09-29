import coc
import discord
import pendulum

from typing import *
from mongoengine import *

from coc_client.api_client import BotClashClient

from .clan_attributes import db_Clan, _ClanAttributes
from .clan_cwl_attributes import _ClanCWLConfig

from ..discord.clan_link import ClanGuildLink

from ..season.season import aClashSeason
from ..events.clan_war_leagues import WarLeagueGroup, WarLeagueClan
from ..events.raid_weekend import aRaidWeekend

from ...constants.coc_emojis import *
from ...constants.ui_emojis import *
from ...constants.coc_constants import *
from ...exceptions import *

feed_description = {
    1: "Member Join/Leave",
    2: "Donation Log",
    3: "Raid Weekend Results",
    4: "Capital Contribution"
    }

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

class aClan(coc.Clan):
    def __init__(self,**kwargs):
        self.client = BotClashClient()
        self.bot = kwargs.get('bot',None)
        self.timestamp = pendulum.now()

        self.capital_hall = 0
        self.badge = ""

        if not self.bot:
            self.tag = None
            self.name = "No Clan"            
            return
        
        super().__init__(**kwargs)

        try:
            self.capital_hall = [district.hall_level for district in self.capital_districts if district.name=="Capital Peak"][0]
        except IndexError:
            self.capital_hall = 0

        self.badge = getattr(self.badge,'url',None)

    @classmethod
    def from_cache(cls,tag):
        client = BotClashClient()
        n_tag = coc.utils.correct_tag(tag)        
        clan = client.clan_cache.get(n_tag)
        if clan:
            return clan        
        client.clan_cache.add_to_queue(tag)
        client.cog.coc_data_log.warning(f"Clan {tag} not found in cache."
            + (f" Already in queue." if tag in client.clan_cache.queue else " Added to queue."))
        raise CacheNotReady    
            
    @classmethod
    async def from_abbreviation(cls,abbreviation:str):
        client = BotClashClient()
        try:
            get_clan = db_Clan.objects.get(abbreviation=abbreviation.upper())
        except (DoesNotExist,MultipleObjectsReturned):
            raise InvalidAbbreviation(abbreviation.upper())
        
        clan = await cls.create(get_clan.tag)
        return clan
    
    @classmethod
    async def create(cls,tag:Optional[str]=None,no_cache:bool=False,bot=None):
        if not tag:
            return aClan()
        
        n_tag = coc.utils.correct_tag(tag)
        if not coc.utils.is_valid_tag(tag):
            raise InvalidTag(tag)
        
        if bot:
            bot = bot
            client = bot.get_cog("ClashOfClansClient").client
        else:
            client = BotClashClient()
            bot = client.bot

        try:
            cached = client.clan_cache.get(n_tag)
        except:
            cached = None
        if no_cache:
            pass        
        elif isinstance(cached,aClan):
            if pendulum.now().int_timestamp - cached.timestamp.int_timestamp < 3600:
                return cached

        try:
            clan = await client.bot.coc_client.get_clan(tag,cls=aClan,bot=bot)
        except coc.NotFound as exc:
            raise InvalidTag(tag) from exc
        except (coc.InvalidArgument,coc.InvalidCredentials,coc.Maintenance,coc.Forbidden,coc.GatewayError) as exc:
            if cached:
                return cached
            else:
                raise ClashAPIError(exc) from exc
        
        client.clan_cache.set(clan.tag,clan)
        return clan
    
    ##################################################
    ### CLAN ATTRIBUTES
    ##################################################
    @property
    def _attributes(self) -> _ClanAttributes:
        return _ClanAttributes(self)
    
    @property
    def is_registered_clan(self):
        return self._attributes.is_registered_clan
        
    @property
    def abbreviation(self):
        return self._attributes.abbreviation
    @abbreviation.setter
    def abbreviation(self,new_abbreviation:str):
        self._attributes.abbreviation = new_abbreviation.upper()

    @property
    def emoji(self) -> str:
        return self._attributes.emoji
    @emoji.setter
    def emoji(self,new_emoji:str):
        self._attributes.emoji = new_emoji
    
    @property
    def unicode_emoji(self) -> str:
        return self._attributes.unicode_emoji
    @unicode_emoji.setter
    def unicode_emoji(self,new_emoji:str):
        self._attributes.unicode_emoji = new_emoji

    @property
    def is_alliance_clan(self):
        return self._attributes.is_alliance_clan    
    @is_alliance_clan.setter
    def is_alliance_clan(self,boolean:bool):
        self._attributes.is_alliance_clan = boolean        
    
    @property
    def c_description(self) -> str:
        return self._attributes.description
    @c_description.setter
    def c_description(self,new_description:str):
        self._attributes.description = new_description
    
    @property
    def recruitment_level(self) -> list[int]:
        return self._attributes._recruitment_level    
    @recruitment_level.setter
    def recruitment_level(self,recruitment_levels:list[int]):
        self._attributes.recruitment_level = recruitment_levels
    
    @property
    def max_recruitment_level(self) -> int:
        return max(self.recruitment_level) if len(self.recruitment_level) > 0 else 0
    @property
    def recruitment_level_emojis(self) -> str:
        return " ".join([EmojisTownHall.get(th_level) for th_level in self.recruitment_level])
    
    @property
    def recruitment_info(self) -> str:
        return self._attributes.recruitment_info
    @recruitment_info.setter
    def recruitment_info(self,new_recruitment_info:str):
        self._attributes.recruitment_info = new_recruitment_info

    @property
    def leader(self) -> int:
        return self._attributes.leader
    @leader.setter
    def leader(self,new_leader_id:int):
        self._attributes.leader = new_leader_id
    
    @property
    def coleaders(self) -> list[int]:
        return self._attributes.coleaders
    @coleaders.setter
    def coleaders(self,new_coleaders:list[int]):
        self._attributes.coleaders = new_coleaders
            
    @property
    def elders(self) -> list[int]:
        return self._attributes.elders
    @elders.setter
    def elders(self,new_elders:list[int]):
        self._attributes.elders = new_elders
    
    ##################################################
    ### BANK HELPERS
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
    ### DATA FORMATTERS
    ##################################################
    def __str__(self):
        return f"{self.name} ({self.tag})"
    
    def __eq__(self,other):
        return isinstance(other,aClan) and self.tag == other.tag
    
    def __hash__(self):
        return hash(self.tag)
    
    @property
    def title(self):
        return f"{self.emoji} {self.name} ({self.tag})" if self.emoji else f"{self.name} ({self.tag})"
    
    @property
    def long_description(self):
        description = f"{EmojisClash.CLAN} Level {self.level}\u3000"
        description += f"{EmojisUI.MEMBERS} {self.member_count}" + (f" (R:{self.alliance_member_count})" if self.is_alliance_clan else "") + "\u3000"
        description += f"{EmojisUI.GLOBE} {self.location.name}\n"
        description += (f"{EmojisClash.CLANWAR} W{self.war_wins}/D{self.war_ties}/L{self.war_losses} (Streak: {self.war_win_streak})\n" if self.public_war_log else "")
        description += f"{EmojisClash.WARLEAGUES}" + (f"{EmojisLeagues.get(self.war_league.name)} {self.war_league.name}\n" if self.war_league else "Unranked\n")
        description += f"{EmojisCapitalHall.get(self.capital_hall)} CH {self.capital_hall}\u3000"
        description += f"{EmojisClash.CAPITALTROPHY} {self.capital_points}\u3000"
        description += (f"{EmojisLeagues.get(self.capital_league.name)} {self.capital_league}" if self.capital_league else f"{EmojisLeagues.UNRANKED} Unranked") #+ "\n"
        #description += f"**[Clan Link: {self.tag}]({self.share_link})**"
        return description
    
    @property
    def summary_description(self):
        war_league_str = f"{EmojisLeagues.get(self.war_league.name)} {self.war_league.name}" if self.war_league else ""
        description = f"{EmojisClash.CLAN} Level {self.level}\u3000{EmojisCapitalHall.get(self.capital_hall)} CH {self.capital_hall}\u3000{war_league_str}"
        return description
    
    @property
    def alliance_member_count(self):
        return self.client.cog.count_members_by_season(clan=self)
    
    @property
    def alliance_members(self):
        return self.client.cog.get_members_by_season(clan=self)
    
    ##################################################
    ### CLAN SETTINGS DATABASE PROPERTIES/METHODS
    ##################################################
    @property
    def guild_links(self) -> list[ClanGuildLink]:
        return ClanGuildLink.get_clan_links(self.tag)
    
    @property
    def war_reminders(self) -> list[db_ClanEventReminder]:
        return db_ClanEventReminder.objects(tag=self.tag,type=1)
    async def create_war_reminder(self,
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
    
    @property
    def raid_reminders(self) -> list[db_ClanEventReminder]:
        return db_ClanEventReminder.objects(tag=self.tag,type=2)
    async def create_raid_reminder(self,
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
    def raid_result_feed(self) -> list[db_ClanDataFeed]:
        return db_ClanDataFeed.objects(tag=self.tag,type=3)
    @property
    def capital_contribution_feed(self) -> list[db_ClanDataFeed]:
        return db_ClanDataFeed.objects(tag=self.tag,type=4)
    
    async def create_feed(self,
        type:int,
        channel:Union[discord.TextChannel,discord.Thread]
        ):
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
    def cwl_config(self):
        return _ClanCWLConfig(self)

    def cwl_season(self,season:aClashSeason):
        return WarLeagueClan(self.tag,season)
    
    ##################################################
    ### CLAN METHODS
    ##################################################
    # async def cleanup_staff(self):
    #     #Remove Leaders from Elders/Cos:
    #     if self.leader in self.coleaders:
    #         self.coleaders.remove(self.leader)
    #     if self.leader in self.elders:
    #         self.elders.remove(self.leader)

    #     for m in self.coleaders:
    #         mem = aMember(m)
    #         if self.tag not in [c.tag for c in mem.home_clans]:
    #             self.coleaders.remove(m)

    #     for m in self.elders:
    #         mem = aMember(m)
    #         if self.tag not in [c.tag for c in mem.home_clans]:
    #             self.elders.remove(m)

    async def remove_clan(self):
        self.is_alliance_clan = False

    async def update_member_rank(self,user_id:int,rank:str):
        elders = self.elders.copy()
        coleaders = self.coleaders.copy()
        
        if rank == 'Member':
            if user_id in elders:
                elders.remove(user_id)
            if user_id in coleaders:
                coleaders.remove(user_id)

        if rank == 'Elder':
            if user_id not in elders:
                elders.append(user_id)
            if user_id in coleaders:
                coleaders.remove(user_id)

        if rank == 'Co-Leader':
            if user_id not in coleaders:
                coleaders.append(user_id)
            if user_id in elders:
                elders.remove(user_id)

        if rank == 'Leader':
            #demote existing leader to Co
            if self.leader not in coleaders:
                coleaders.append(self.leader)
            self.leader = user_id
        
        self.elders = elders
        self.coleaders = coleaders

    async def set_description(self,new_desc:str):
        if not self.is_alliance_clan:
            return
        self.description = new_desc
        self._db_attributes._description = new_desc
        self._db_attributes.save_clan()

    async def get_league_group(self):
        client = BotClashClient()
        await client.cog.get_league_group(self.tag)
    
    async def get_current_war(self):
        current_war = await self.client.cog.get_clan_war(self.tag)

        league_group = None
        if self.client.cog.current_season.cwl_start <= pendulum.now() <= self.client.cog.current_season.cwl_end.add(days=1):
            league_group = await self.client.cog.get_league_group(self.tag)        
        
        if not current_war and league_group:
            league_clan = league_group.get_clan(self.clan.tag)
            current_war = league_clan.current_war        
        return current_war

    async def get_raid_weekend(self):
        api_raid = None
        try:
            raidloggen = await self.bot.coc_client.get_raid_log(clan_tag=self.tag,page=False,limit=1)
        except coc.PrivateWarLog:
            return None
        except coc.NotFound as exc:
            raise InvalidTag(self.tag) from exc
        except (coc.Maintenance,coc.GatewayError) as exc:
            raise ClashAPIError(exc) from exc
        
        if len(raidloggen) == 0:
            return None
        api_raid = raidloggen[0]

        if not api_raid:
            return None
        
        raid_weekend = await aRaidWeekend.create_from_api(self.tag,api_raid)
        return raid_weekend