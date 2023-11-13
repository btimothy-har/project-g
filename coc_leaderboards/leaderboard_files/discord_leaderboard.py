import asyncio
import discord
import pendulum
import re

from typing import *
from mongoengine import *

from collections import defaultdict
from numerize import numerize
from redbot.core.utils import AsyncIter

from coc_main.api_client import BotClashClient, aClashSeason
from coc_main.cog_coc_client import ClashOfClansClient, aClan

from coc_main.coc_objects.players.player import aPlayer, db_PlayerStats
from coc_main.coc_objects.clans.clan import db_AllianceClan
from coc_main.discord.guild import aGuild, ClanGuildLink

from coc_main.utils.components import clash_embed, DiscordButton
from coc_main.utils.constants.coc_emojis import EmojisTownHall
from coc_main.utils.constants.ui_emojis import EmojisUI

from .leaderboard_player import ClanWarLeaderboardPlayer, ResourceLootLeaderboardPlayer, DonationsLeaderboardPlayer, ClanGamesLeaderboardPlayer
from ..exceptions import LeaderboardExists

leaderboard_types = {
    1: "Clan War Triples",
    2: "Capital Contribution",
    3: "Resource Loot",
    4: "Donations",
    5: "Clan Games",
    }

eligible_townhalls = list(range(9,16))[::-1]

bot_client = BotClashClient()

##################################################
#####
##### DATABASE
#####
##################################################
class db_Leaderboard(Document):
    type = IntField(required=True)
    is_global = BooleanField(default=False,required=True)
    guild_id = IntField(default=0,required=True)
    channel_id = IntField(default=0,required=True)
    message_id = IntField(default=0)

##################################################
#####
##### ARCHIVED SEASONS
#####
##################################################
class db_Leaderboard_Archive(Document):
    type = IntField(required=True)
    is_global = BooleanField(default=False,required=True)
    guild_id = IntField(default=0,required=True)
    season = StringField(default="",required=True)
    embed = DictField(default={})

##################################################
#####
##### DATABASE
#####
##################################################
class db_Leaderboard(Document):
    type = IntField(required=True)
    is_global = BooleanField(default=False,required=True)
    guild_id = IntField(default=0,required=True)
    channel_id = IntField(default=0,required=True)
    message_id = IntField(default=0)

class LeaderboardView(discord.ui.View):
    def __init__(self,leaderboard):

        self.leaderboard = leaderboard
        super().__init__(timeout=None)

        for season in self.leaderboard.seasons:
            if pendulum.now() >= season.season_end:
                button = DiscordButton(
                    function=self._callback_season_button,
                    label=f"{season.description}",
                    reference=season.id
                    )
                self.add_item(button)

    async def on_timeout(self):
        pass
    
    async def _callback_season_button(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer(ephemeral=True)
        season_embed = self.leaderboard._leaderboard_data.get(button.reference)
        await interaction.followup.send(embed=season_embed,ephemeral=True)
    
    @property
    def bot_client(self) -> BotClashClient:
        return BotClashClient()

    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")

##################################################
#####
##### DISCORD LEADERBOARD HOLDER
#####
##################################################
class DiscordLeaderboard():  

    @staticmethod
    def get_leaderboard_seasons():
        return [bot_client.current_season] + bot_client.tracked_seasons[:3]
    
    @classmethod
    async def get_all_leaderboards(cls) -> List['DiscordLeaderboard']:
        def _db_query():
            return [lb for lb in db_Leaderboard.objects()]
        leaderboards = await bot_client.run_in_thread(_db_query)
        return [cls(lb) for lb in leaderboards]
    
    @classmethod
    async def get_by_id(cls,leaderboard_id:str) -> 'DiscordLeaderboard':
        def _db_query():
            try:
                return db_Leaderboard.objects.get(pk=leaderboard_id)
            except DoesNotExist:
                return None
        
        leaderboard = await bot_client.run_in_thread(_db_query)
        if leaderboard:
            return cls(leaderboard)
        return None

    @classmethod
    async def get_guild_leaderboards(cls,guild_id:int) -> List['DiscordLeaderboard']:
        def _db_query():
            return [lb for lb in db_Leaderboard.objects(guild_id=guild_id)]
        
        leaderboards = await bot_client.run_in_thread(_db_query)
        return [cls(lb) for lb in leaderboards]

    def __init__(self,database_entry:db_Leaderboard):
        self.id = str(database_entry.pk)

        self.type = database_entry.type
        self.is_global = database_entry.is_global
        self.guild_id = database_entry.guild_id
        self.channel_id = database_entry.channel_id
        self.message_id = database_entry.message_id
        
        self.seasons = []

        self._primary_embed = None
        self._leaderboard_data = {}
    
    def __str__(self):
        return f"{self.lb_type} Leaderboard (Channel: {self.channel.name})"    
    
    def is_season_current(self,season):
        if self.type == 5:            
            if season.id == aClashSeason.last_completed_clangames().id:
                return True
        else:
            if season.is_current:
                return True
        return False

    @property
    def guild(self):
        return bot_client.bot.get_guild(self.guild_id)

    @property
    def channel(self):
        if not self.guild:
            return None
        return self.guild.get_channel(self.channel_id)
    
    @property
    def lb_type(self):
        return leaderboard_types.get(self.type,"Unknown Leaderboard")
    
    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    @classmethod
    async def create(cls,leaderboard_type:int,is_global:bool,guild:discord.Guild,channel:discord.TextChannel):

        def _query_existing():
            return db_Leaderboard.objects(
                type=leaderboard_type,
                is_global=is_global,
                guild_id=guild.id
                )
        
        def _create_in_db():
            db_entry = db_Leaderboard(
                type = leaderboard_type,
                is_global = is_global,
                guild_id = guild.id,
                channel_id = channel.id
                )
            db_entry.save()
            return db_entry
        
        existing_db = await bot_client.run_in_thread(_query_existing)
        if len(existing_db) > 0:
            raise LeaderboardExists(f"{leaderboard_types.get(leaderboard_type,'Unknown Leaderboard')} already exists for {guild.name}.")

        db_entry = await bot_client.run_in_thread(_create_in_db)
        lb = cls(db_entry)
        await lb.send_blank_lb()
        return lb
    
    async def delete(self):
        def _delete_in_db():
            db_Leaderboard.objects(pk=self.id).delete()
        
        message = await self.fetch_message()
        if message:
            await message.delete()  
        await bot_client.run_in_thread(_delete_in_db)
    
    async def get_leaderboard_clans(self) -> List[aClan]:
        if self.is_global:
            return await self.client.get_alliance_clans()
        elif self.guild:
            guild_links = await ClanGuildLink.get_for_guild(self.guild_id)
            clans = await asyncio.gather(*(self.client.fetch_clan(tag=link.tag) for link in guild_links))
            return clans
        else:
            return []

    async def update_leaderboard(self):
        def _db_get_archive(season):
            try:
                return db_Leaderboard_Archive.objects.get(
                    type = self.type,
                    is_global = self.is_global,
                    guild_id = self.guild_id,
                    season = season.id
                    )
            except DoesNotExist:
                return None
            except MultipleObjectsReturned:
                bot_client.coc_main_log.warning(f"Multiple {self.lb_type} Leaderboards found for {season.description} in {self.guild.name}.")
                db_Leaderboard_Archive.objects(
                    type = self.type,
                    is_global = self.is_global,
                    guild_id = self.guild_id,
                    season = season.id
                    ).delete()
                return None

        seasons = DiscordLeaderboard.get_leaderboard_seasons()

        try:
            async for season in AsyncIter(seasons):
                calculate = False
                archive = False

                if not self.is_season_current(season):
                    archived_lb = await bot_client.run_in_thread(_db_get_archive,season)
                    if not archived_lb:
                        calculate = True
                        archive = True

                elif self.type == 5 and self.is_season_current(season) and pendulum.now() >= season.clangames_end:
                    archived_lb = await bot_client.run_in_thread(_db_get_archive,season)
                    if not archived_lb:
                        calculate = True
                        archive = True
               
                else:
                    calculate = True

                if calculate:
                    if self.type == 1:
                        data = await ClanWarLeaderboard.calculate(self,season)
                    elif self.type == 3:
                        data = await ResourceLootLeaderboard.calculate(self,season)
                    elif self.type == 4:
                        data = await DonationsLeaderboard.calculate(self,season)
                    elif self.type == 5:
                        data = await ClanGamesLeaderboard.calculate(self,season)                
                else:
                    data = discord.Embed.from_dict(archived_lb.embed)

                await self.consolidate_data(season,data,archive)

            await self.send_to_discord()

        except Exception as ex:
            bot_client.coc_main_log.exception(f"Error updating {self.lb_type} Leaderboard for {self.guild.name}.")
            await bot_client.bot.send_to_owners(f"Error updating {self.lb_type} Leaderboard for {self.guild.name}.\n```{ex}```")
    
    async def fetch_message(self):
        if self.channel:
            try:
                return await self.channel.fetch_message(self.message_id)
            except discord.NotFound:
                pass
        return None

    async def send_blank_lb(self):
        season = bot_client.current_season
        if self.type == 1:
            data = ClanWarLeaderboard(self,season)
        elif self.type == 3:
            data = ResourceLootLeaderboard(self,season)
        elif self.type == 4:
            data = DonationsLeaderboard(self,season)
        elif self.type == 5:
            data = ClanGamesLeaderboard(self,season)    
        embed = await data.get_embed()
        self._primary_embed = embed
        await self.send_to_discord()

    async def consolidate_data(self,season,embed,send_to_archive=False):
        def _save_archive():
            lb = db_Leaderboard_Archive(
                type = self.type,
                is_global = self.is_global,
                guild_id = self.guild_id,
                season = season.id,
                embed = embed.to_dict()
                )
            lb.save()

        if self.is_season_current(season):
            self._primary_embed = embed
        
        else:
            self.seasons.append(season)
            self._leaderboard_data[season.id] = embed
        
        if send_to_archive:
            await bot_client.run_in_thread(_save_archive)
            bot_client.coc_main_log.info(f"Archived {self.lb_type} Leaderboard for {season.description} in {getattr(self.guild,'name','')} {self.guild_id}.")
    
    async def send_to_discord(self):
        def _update_message_id():
            db_Leaderboard.objects(pk=self.id).update_one(
                set__message_id=self.message_id
                )
        if not self.channel:
            await self.delete()
        
        try:
            lb_view = LeaderboardView(self)
            try:
                message = await self.channel.fetch_message(self.message_id)
            except discord.NotFound:
                message = await self.channel.send(embed=self._primary_embed,view=lb_view)
            else:
                message = await message.edit(embed=self._primary_embed,view=lb_view)
                
            self.message_id = message.id
            await bot_client.run_in_thread(_update_message_id)
        except:
            bot_client.coc_main_log.exception(f"Error sending {self.lb_type} Leaderboard to Discord.")

class Leaderboard():
    def __init__(self):
        self._players = []
    
    @property
    def bot_client(self) -> BotClashClient:
        return BotClashClient()

    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")

##################################################
#####
##### TYPE 1 LEADERBOARD
##### War Triple Leaderboard
##################################################
class ClanWarLeaderboard(Leaderboard):
    def __init__(self,parent:DiscordLeaderboard,season:aClashSeason):
        self.season = season
        self.parent = parent
        super().__init__()

        self.leaderboard_players = defaultdict(list)
        self.timestamp = None    

    @classmethod
    async def calculate(cls,parent:DiscordLeaderboard,season:aClashSeason):
        def _db_query():
            query_players = db_PlayerStats.objects(
                is_member=True,
                season=season.id
                ).only('tag')
            return [p.tag for p in query_players]
        
        leaderboard = cls(parent,season)        
        
        query_players = await bot_client.run_in_thread(_db_query)

        lb_players = await asyncio.gather(*(leaderboard.client.fetch_player(tag=p,enforce_lock=True) for p in query_players))
        lb_clans = await leaderboard.parent.get_leaderboard_clans()

        async for p in AsyncIter(lb_players):
            stats = p.get_season_stats(season)

            async for lb_th in AsyncIter(eligible_townhalls):
                if parent.is_global:
                    lb_player = await ClanWarLeaderboardPlayer.calculate(stats,lb_th)
                else:
                    lb_player = await ClanWarLeaderboardPlayer.calculate(stats,lb_th,lb_clans)
                if lb_player.wars_participated > 0:
                    leaderboard.leaderboard_players[lb_th].append(lb_player)
        
        leaderboard.timestamp = pendulum.now()
        return await leaderboard.get_embed()
    
    async def get_embed(self):
        embed = await clash_embed(
            context=self.bot_client.bot,
            title=f"**Clan War Leaderboard: {self.season.description}**",
            message=f"***Ranks players by number of War Triples achieved in the month.***"
                + (f"\nLast Refreshed: <t:{getattr(self.timestamp,'int_timestamp',0)}:R>" if self.season.is_current and self.timestamp else "")
                + f"\n\n"
                + f"- You must have participated in at least 1 eligible war to be considered for the Leaderboard."
                + f"\n- Only regular Clan Wars are included (friendly & CWL wars excluded)."
                + (f"\n- Only Wars with Clans linked to this Server are included." if not self.parent.is_global else "")
                + f"\n- Townhall levels are captured from the specific War you participated in."
                + f"\n- Leaderboard resets at the end of every month."
                + f"\n\n{EmojisUI.SPACER}{EmojisUI.SPACER}`{'':<2}{'TRP':>3}{'':<4}{'ATT':>3}{'':<4}{'AVG':>3}{'':<4}{'HITRT':>5}{'':<2}`"
                )
        async for lb_th in AsyncIter(eligible_townhalls):
            wl_players = self.leaderboard_players.get(lb_th,[])
            wl_players.sort(key=lambda x: (getattr(x,'total_triples',0),getattr(x,'hit_rate',0)),reverse=True)

            if len(wl_players) > 0:
                embed.add_field(
                    name=f"**TH{lb_th}**",
                    value="\n".join([
                        f"{EmojisTownHall.get(lb_th)}{p.stats.home_clan.emoji}`{'':<2}{p.total_triples:>3}{'':<4}{p.total_attacks:>3}{'':<4}{p.avg_stars:>3}{'':<4}{str(p.hit_rate)+'%':>5}{'':<2}`\u3000{re.sub('[_*/]','',p.clean_name)}"
                        for p in wl_players[:5]]),
                    inline=False
                    )
            else:
                embed.add_field(
                    name=f"**TH{lb_th}**",
                    value=f"{EmojisUI.SPACER}<a:barbarian_bored:1156458893900267520> *It's a little lonely... there's no one participating :(.*",
                    inline=False
                    )
        return embed

##################################################
#####
##### TYPE 3 LEADERBOARD
##### Multiplayer Loot Leaderboard
##################################################
class ResourceLootLeaderboard(Leaderboard):    
    def __init__(self,parent:DiscordLeaderboard,season:aClashSeason):
        self.season = season
        self.parent = parent
        super().__init__()

        self.leaderboard_players = defaultdict(list)
        self.timestamp = None

    @classmethod
    async def calculate(cls,parent:DiscordLeaderboard,season:aClashSeason):

        def _db_query():
            query_players = db_PlayerStats.objects(
                is_member=True,
                season=season.id,
                loot_darkelixir__season_total__gt=0
                ).only('tag')
            return [p.tag for p in query_players]

        def predicate_leaderboard(player:aPlayer):
            stats = player.get_season_stats(season)            
            if parent.is_global:
                return stats.attacks.season_total > 0
            else:
                return stats.attacks.season_total > 0 and stats.home_clan_tag in [c.tag for c in lb_clans]

        leaderboard = cls(parent,season)

        query_players = await bot_client.run_in_thread(_db_query)
        
        all_players = await asyncio.gather(*(leaderboard.client.fetch_player(tag=p,enforce_lock=True) for p in query_players))
        lb_clans = await leaderboard.parent.get_leaderboard_clans()
        
        iter_players = AsyncIter(all_players)
        async for p in iter_players.filter(predicate_leaderboard):
            stats = p.get_season_stats(season)

            async for lb_th in AsyncIter(eligible_townhalls):
                if stats.town_hall == lb_th:
                    lb_player = await ResourceLootLeaderboardPlayer.calculate(stats,lb_th)
                    leaderboard.leaderboard_players[lb_th].append(lb_player)
        
        leaderboard.timestamp = pendulum.now()
        return await leaderboard.get_embed()
    
    async def get_embed(self):
        embed = await clash_embed(
            context=self.bot_client.bot,
            title=f"**Resource Leaderboard: {self.season.description}**",
            message=f"***Ranks players by amount of Dark Elixir looted in the month.***"
                + (f"\nLast Refreshed: <t:{getattr(self.timestamp,'int_timestamp',0)}:R>" if self.season.is_current and self.timestamp else "")
                + f"\n\n"
                + f"- You must have won at least one multiplayer attack to be considered for the Leaderboard."
                + (f"\n- Only Members of Clans linked to this Server are included." if not self.parent.is_global else "")
                + f"\n- Loot achievement values beyond 2B are no longer tracked by Clash of Clans. These will appear as 'max' below."
                + f"\n- Townhall levels are based on your current TH level."
                + f"\n- Leaderboard resets at the end of every month."                
                + f"\n\n{EmojisUI.SPACER}{EmojisUI.SPACER}`{'':<2}{'DRK ELI':>7}{'':<3}{'GOLD':>7}{'':<3}{'ELIXIR':>7}{'':<2}`"
                )
        async for lb_th in AsyncIter(eligible_townhalls):
            wl_players = self.leaderboard_players.get(lb_th,[])
            wl_players.sort(key=lambda x: (getattr(x,'loot_darkelixir',0)),reverse=True)

            if len(wl_players) > 0:
                embed.add_field(
                    name=f"**TH{lb_th}**",
                    value="\n".join([
                        f"{EmojisTownHall.get(lb_th)}{p.stats.home_clan.emoji}`{'':<2}{numerize.numerize(p.loot_darkelixir,2):>7}{'':<3}{p.loot_gold:>7}{'':<3}{p.loot_elixir:>7}{'':<2}`\u3000{re.sub('[_*/]','',p.clean_name)}"
                        for p in wl_players[:5]]),
                    inline=False
                    )
            else:
                embed.add_field(
                    name=f"**TH{lb_th}**",
                    value=f"{EmojisUI.SPACER}<a:barbarian_bored:1156458893900267520> *It's a little lonely... there's no one participating :(.*",
                    inline=False
                    )
        return embed

##################################################
#####
##### TYPE 4 LEADERBOARD
##### Donations
##################################################
class DonationsLeaderboard(Leaderboard):    
    def __init__(self,parent:DiscordLeaderboard,season:aClashSeason):
        self.season = season
        self.parent = parent
        super().__init__()

        self.leaderboard_players = defaultdict(list)
        self.timestamp = None

    @classmethod
    async def calculate(cls,parent:DiscordLeaderboard,season:aClashSeason):

        def _db_query():
            query_players = db_PlayerStats.objects(
                is_member=True,
                season=season.id,
                donations_sent__season_total__gt=0
                ).only('tag')
            return [p.tag for p in query_players]

        def predicate_leaderboard(player:aPlayer):
            stats = player.get_season_stats(season)            
            if parent.is_global:
                return stats.donations_sent.season_total > 0
            else:
                return stats.donations_sent.season_total > 0 and stats.home_clan_tag in [c.tag for c in lb_clans]

        leaderboard = cls(parent,season)

        query_players = await bot_client.run_in_thread(_db_query)
        
        all_players = await asyncio.gather(*(leaderboard.client.fetch_player(tag=p,enforce_lock=True) for p in query_players))
        lb_clans = await leaderboard.parent.get_leaderboard_clans()
        
        iter_players = AsyncIter(all_players)
        async for p in iter_players.filter(predicate_leaderboard):
            stats = p.get_season_stats(season)

            async for lb_th in AsyncIter(eligible_townhalls):
                if stats.town_hall == lb_th:
                    lb_player = await DonationsLeaderboardPlayer.calculate(stats,lb_th)
                    leaderboard.leaderboard_players[lb_th].append(lb_player)
        
        leaderboard.timestamp = pendulum.now()
        return await leaderboard.get_embed()
    
    async def get_embed(self):
        embed = await clash_embed(
            context=bot_client.bot,
            title=f"**Donations Leaderboard: {self.season.description}**",
            message=f"***Ranks players by number of Donated Troops/Spells/Sieges in the month.***"
                + (f"\nLast Refreshed: <t:{getattr(self.timestamp,'int_timestamp',0)}:R>" if self.season.is_current and self.timestamp else "")
                + f"\n\n"
                + (f"- Only Members of Clans linked to this Server are included.\n" if not self.parent.is_global else "")
                + f"- Donations are tracked cumulatively across all Clans you've been in this Season."
                + f"\n- Townhall levels are based on your current TH level."
                + f"\n- Leaderboard resets at the end of every month."
                + f"\n\n{EmojisUI.SPACER}{EmojisUI.SPACER}`{'':<2}{'SENT':>7}{'':<3}{'RCVD':>7}{'':<2}`"
                )
        async for lb_th in AsyncIter(eligible_townhalls):
            wl_players = self.leaderboard_players.get(lb_th,[])
            wl_players.sort(key=lambda x: (getattr(x,'donations_sent',0)),reverse=True)

            if len(wl_players) > 0:
                embed.add_field(
                    name=f"**TH{lb_th}**",
                    value="\n".join([
                        f"{EmojisTownHall.get(lb_th)}{p.stats.home_clan.emoji}`{'':<2}{numerize.numerize(p.donations_sent,3):>7}{'':<3}{numerize.numerize(p.donations_rcvd,3):>7}{'':<2}`\u3000{re.sub('[_*/]','',p.name)}"
                        for p in wl_players[:5]]),
                    inline=False
                    )
            else:
                embed.add_field(
                    name=f"**TH{lb_th}**",
                    value=f"{EmojisUI.SPACER}<a:barbarian_bored:1156458893900267520> *It's a little lonely... there's no one participating :(.*",
                    inline=False
                    )
        return embed

##################################################
#####
##### TYPE 5 LEADERBOARD
##### Clan Games - by default, this cannot be a global leaderboard
##################################################
class ClanGamesLeaderboard(Leaderboard):    
    def __init__(self,parent:DiscordLeaderboard,season:aClashSeason):
        self.season = season
        self.parent = parent
        super().__init__()

        self.leaderboard_players = defaultdict(list)
        self.timestamp = None

    @classmethod
    async def calculate(cls,parent:DiscordLeaderboard,season:aClashSeason):

        def _db_query():
            query_players = db_PlayerStats.objects(
                is_member=True,
                season=season.id,
                clangames__score__gt=0
                ).only('tag')
            return [p.tag for p in query_players]

        def predicate_leaderboard(player:aPlayer):
            stats = player.get_season_stats(season)
            return stats.clangames.score > 0 and stats.clangames.clan_tag in [c.tag for c in lb_clans] and stats.home_clan_tag == stats.clangames.clan_tag

        leaderboard = cls(parent,season)

        query_players = await bot_client.run_in_thread(_db_query)
        
        all_players = await asyncio.gather(*(leaderboard.client.fetch_player(tag=p,enforce_lock=True) for p in query_players))
        lb_clans = await leaderboard.parent.get_leaderboard_clans()

        iter_players = AsyncIter(all_players)
        async for p in iter_players.filter(predicate_leaderboard):
            stats = p.get_season_stats(season)

            if parent.is_global:
                lb_player = await ClanGamesLeaderboardPlayer.calculate(stats)
                leaderboard.leaderboard_players['global'].append(lb_player)
            
            else:
                lb_clans.sort(key=lambda x:(x.level,x.capital_hall),reverse=True)

                async for c in AsyncIter(lb_clans):
                    if stats.clangames.clan_tag == c.tag:
                        lb_player = await ClanGamesLeaderboardPlayer.calculate(stats)
                        leaderboard.leaderboard_players[c.tag].append(lb_player)
        
        leaderboard.timestamp = pendulum.now()
        return await leaderboard.get_embed()
    
    async def get_embed(self):
        embed = await clash_embed(
            context=self.bot_client.bot,
            title=f"**Clan Games Leaderboard: {self.season.description}**",
            message=f"***Ranks players by Clan Games score & completion time.***"
                + (f"\nLast Refreshed: <t:{getattr(self.timestamp,'int_timestamp',0)}:R>" if self.season.is_current and self.timestamp else "")
                + f"\n\n"
                + (f"- Only Clans linked to this Server are included.\n" if not self.parent.is_global else "")
                + f"- You must have started Clan Games in your assigned Home Clan to be eligible."
                + f"\n- Completion Time is measured from the global start of Clan Games."
                + f"\n\u200b"
                )
        if self.parent.is_global:
            wl_players = self.leaderboard_players.get('global',[])
            wl_players.sort(key=lambda x: (x.score,(x.completion_seconds * -1)),reverse=True)

            leaderboard_text = f"`{'':<3}{'Score':>6}{'Time':>13}{'':<2}`"

            async for i,p in AsyncIter(enumerate(wl_players[:30],start=1)):
                clan = await self.client.fetch_clan(p.clangames_clan_tag)
                leaderboard_text += f"\n`{i:<3}{p.score:>6,}{p.time_to_completion:>13}{'':<2}`\u3000{clan.emoji}{EmojisTownHall.get(p.stats.town_hall)} {re.sub('[_*/]','',p.clean_name)}"
            embed.description += leaderboard_text
        
        else:
            lb_clans = await self.parent.get_leaderboard_clans()
            async for clan in AsyncIter(lb_clans):
                wl_players = self.leaderboard_players.get(clan.tag,[])
                wl_players.sort(key=lambda x: (x.score,(x.completion_seconds * -1)),reverse=True)

                if len(wl_players) > 0:
                    embed.add_field(
                        name=f"{clan.emoji} **{clan.clean_name}**",
                        value=f"`{'':<3}{'Score':>6}{'Time':>13}{'':<2}`\n"
                            + "\n".join([
                            f"`{i:<3}{p.score:>6,}{p.time_to_completion:>13}{'':<2}`\u3000{EmojisTownHall.get(p.stats.town_hall)} {re.sub('[_*/]','',p.name)}"
                            for i,p in enumerate(wl_players[:5],start=1)]),
                        inline=False
                        )
                else:
                    embed.add_field(
                        name=f"{clan.emoji} **{clan.clean_name}**",
                        value=f"{EmojisUI.SPACER}<a:barbarian_bored:1156458893900267520> *It's a little lonely... there's no one participating :(.*",
                        inline=False
                        )
        return embed