import discord
import pendulum
import re
import bson
import coc
import logging

from typing import *

from collections import defaultdict
from numerize import numerize

from redbot.core.bot import Red
from redbot.core.utils import AsyncIter

from coc_main.client.global_client import GlobalClient
from coc_main.coc_objects.season.season import aClashSeason

from coc_main.discord.clan_link import ClanGuildLink

from coc_main.utils.components import clash_embed, DiscordButton
from coc_main.utils.constants.coc_emojis import EmojisTownHall
from coc_main.utils.constants.ui_emojis import EmojisUI

from .leaderboard_player import ClanWarLeaderboardPlayer, ResourceLootLeaderboardPlayer, DonationsLeaderboardPlayer, ClanGamesLeaderboardPlayer
from ..exceptions import LeaderboardExists

LOG = logging.getLogger("coc.main")

leaderboard_types = {
    1: "Clan War Triples",
    2: "Capital Contribution",
    3: "Resource Loot",
    4: "Donations",
    5: "Clan Games",
    }

eligible_townhalls = [16,15,14,13,12,11,10]

##################################################
#####
##### DATABASE
#####
##################################################
# db__leaderboard = {
#     '_id': ObjectId,
#     'type': int,
#     'is_global': bool,
#     'guild_id': int,
#     'channel_id': int,
#     'message_id': int
#     }

##################################################
#####
##### ARCHIVED SEASONS
#####
##################################################
# db__leaderboard_archive = {
#     '_id': ObjectId,
#     'type': int,
#     'is_global': bool,
#     'guild_id': int,
#     'season': string,
#     'embed': dict
#     }

##################################################
#####
##### LEADERBOARD VIEW
#####
##################################################
class LeaderboardView(discord.ui.View,GlobalClient):
    def __init__(self,leaderboard:'DiscordLeaderboard'):

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

##################################################
#####
##### DISCORD LEADERBOARD HOLDER
#####
##################################################
class DiscordLeaderboard(GlobalClient):
    __slots__ = [
        '_id',
        'id',
        '_type',
        'is_global',
        'guild_id',
        'channel_id',
        'message_id',
        'seasons',
        '_primary_embed',
        '_leaderboard_data'
        ]

    @staticmethod
    def get_leaderboard_seasons():
        return [i for i in aClashSeason.all_seasons() if pendulum.now() <= i.season_end][:4]

    def __init__(self,database_entry:dict):
        self._id = database_entry.get('_id')
        self.id = str(self._id)

        self._type = database_entry.get('type',0)
        self.is_global = database_entry.get('is_global',False)
        self.guild_id = database_entry.get('guild_id',0)
        self.channel_id = database_entry.get('channel_id',0)
        self.message_id = database_entry.get('message_id',0)
        
        self.seasons = []

        self._primary_embed = None
        self._leaderboard_data = {}
    
    def __str__(self):
        return f"{self.type} Leaderboard (Global: {self.is_global})"
    
    @property
    def bot(self) -> Red:
        return GlobalClient.bot
    
    @property
    def guild(self):
        return self.bot.get_guild(self.guild_id)
    @property
    def channel(self):
        return self.bot.get_channel(self.channel_id)
    @property
    def type(self):
        return leaderboard_types.get(self._type,"Unknown Leaderboard")
    
    @classmethod
    async def get_all_leaderboards(cls) -> List['DiscordLeaderboard']:
        query = GlobalClient.database.db__leaderboard.find({})
        return [cls(lb) async for lb in query]
    
    @classmethod
    async def get_by_id(cls,leaderboard_id:str) -> 'DiscordLeaderboard':
        find_lb = await GlobalClient.database.db__leaderboard.find_one({'_id':bson.ObjectId(leaderboard_id)})
        if find_lb:
            return cls(find_lb)
        return None

    @classmethod
    async def get_guild_leaderboards(cls,guild_id:int) -> List['DiscordLeaderboard']:        
        query = GlobalClient.database.db__leaderboard.find({'guild_id':guild_id})
        return [cls(lb) async for lb in query]
    
    @classmethod
    async def create(cls,leaderboard_type:int,is_global:bool,guild:discord.Guild,channel:discord.TextChannel):        
        existing_db = await GlobalClient.database.db__leaderboard.find({
            'type':leaderboard_type,
            'is_global':is_global,
            'guild_id':guild.id}
            ).to_list(length=1)
        
        if existing_db and len(existing_db) > 0:
            raise LeaderboardExists(f"{leaderboard_types.get(leaderboard_type,'Unknown Leaderboard')} already exists for {guild.name}.")

        new_db = await GlobalClient.database.db__leaderboard.insert_one({
            'type':leaderboard_type,
            'is_global':is_global,
            'guild_id':guild.id,
            'channel_id':channel.id
            })

        lb = await cls.get_by_id(new_db.inserted_id)
        await lb.send_blank_lb()
        return lb
    
    async def delete(self):        
        message = await self.fetch_message()
        if message:
            await message.delete()  
        await self.database.db__leaderboard.delete_one({'_id':self._id})

    async def fetch_message(self) -> Optional[discord.Message]:
        if self.channel:
            try:
                return await self.channel.fetch_message(self.message_id)
            except discord.NotFound:
                pass
        return None
    
    async def is_season_current(self,season) -> bool: 
        if self._type == 5:
            last_games = await aClashSeason.last_completed_clangames()
            if season.id == last_games.id:
                return True
        else:
            if season.is_current:
                return True
        return False    
    
    async def get_leaderboard_clans(self) -> List[coc.Clan]:
        if self.is_global:
            return await self.coc_client.get_alliance_clans()
        elif self.guild:
            guild_links = await ClanGuildLink.get_for_guild(self.guild_id)
            clans = [c async for c in self.coc_client.get_clans([link.tag for link in guild_links])]
            return clans
        else:
            return []
    
    async def _retrieve_archived(self,season:aClashSeason) -> Optional[discord.Embed]:
        query = await self.database.db__leaderboard_archive.find({
            'type':self._type,
            'is_global':self.is_global,
            'guild_id':self.guild_id,
            'season':season.id
            }).to_list(length=None)
        
        if query and len(query) > 1:
            await self.database.db__leaderboard_archive.delete_many({
                'type':self._type,
                'is_global':self.is_global,
                'guild_id':self.guild_id,
                'season':season.id
                })
            return None
        elif query and len(query) == 1:
            return discord.Embed.from_dict(query[0].get('embed'))
        else:
            return None

    async def update_leaderboard(self):
        if not self.channel:
            return 
        seasons = DiscordLeaderboard.get_leaderboard_seasons()
        a_iter = AsyncIter(seasons)

        async for season in a_iter:
            try:
                calculate = False
                archive = False

                is_current = await self.is_season_current(season)
                if not is_current:
                    archived_data = await self._retrieve_archived(season)
                    if not archived_data:
                        calculate = True
                        archive = True
                elif self._type == 5 and is_current and pendulum.now() >= season.clangames_end:
                    archived_data = await self._retrieve_archived(season)
                    if not archived_data:
                        calculate = True
                        archive = True               
                else:
                    calculate = True

                if calculate:
                    if self._type == 1:
                        data = await ClanWarLeaderboard.calculate(self,season)
                    elif self._type == 3:
                        data = await ResourceLootLeaderboard.calculate(self,season)
                    elif self._type == 4:
                        data = await DonationsLeaderboard.calculate(self,season)
                    elif self._type == 5:
                        data = await ClanGamesLeaderboard.calculate(self,season)                
                else:
                    data = archived_data
            
            except (coc.Maintenance,coc.GatewayError):
                continue
            except Exception as ex:
                LOG.exception(f"Error updating {self.type} Leaderboard for {self.guild.name} for {season.description}.")
                await self.bot.send_to_owners(f"Error updating {self.type} Leaderboard for {self.guild.name} for {season.description}.\n```{ex}```")
            else:
                await self.consolidate_data(season,data,archive)
        
        await self.send_to_discord()
        return

    async def send_blank_lb(self):
        season = aClashSeason.current()
        if self._type == 1:
            data = ClanWarLeaderboard(self,season)
        elif self._type == 3:
            data = ResourceLootLeaderboard(self,season)
        elif self._type == 4:
            data = DonationsLeaderboard(self,season)
        elif self._type == 5:
            data = ClanGamesLeaderboard(self,season)

        embed = await data.get_embed()
        self._primary_embed = embed
        await self.send_to_discord()

    async def consolidate_data(self,season:aClashSeason,embed:discord.Embed,send_to_archive=False):
        if await self.is_season_current(season):
            self._primary_embed = embed
        
        else:
            self.seasons.append(season)
            self._leaderboard_data[season.id] = embed
        
        if send_to_archive:
            await self.database.db__leaderboard_archive.insert_one({
                'type':self._type,
                'is_global':self.is_global,
                'guild_id':self.guild_id,
                'season':season.id,
                'embed':embed.to_dict()
                })
            LOG.info(
                f"Archived {self.type} Leaderboard for {season.description} in {getattr(self.guild,'name','')} {self.guild_id}."
                )
    
    async def send_to_discord(self):
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
            await self.database.db__leaderboard.update_one(
                {'_id':self._id},
                {'$set': {
                    'message_id':self.message_id
                    }
                },
                upsert=True
                )
        except:
            LOG.exception(f"Error sending {self.type} Leaderboard to Discord.")

class Leaderboard(GlobalClient):
    def __init__(self):
        self._players = []
    
    @property
    def bot(self) -> Red:
        return GlobalClient.bot

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
        leaderboard = cls(parent,season)        
        filter_criteria = {
            'is_member':True,
            'timestamp': {
                '$gt':season.season_start.int_timestamp,
                '$lte':season.season_end.int_timestamp
                }
            }
        query = GlobalClient.database.db__player_activity.find(filter_criteria,{'tag':1})
        member_tags = list(set([p['tag'] async for p in query]))        

        leaderboard_clans = await leaderboard.parent.get_leaderboard_clans()

        async for player in GlobalClient.coc_client.get_players(member_tags):            
            stats = await player.get_season_stats(season)
            if not stats.is_member or not stats.home_clan:
                continue

            th_iter = AsyncIter(eligible_townhalls)
            async for lb_th in th_iter:
                if parent.is_global:
                    lb_player = await ClanWarLeaderboardPlayer.calculate(stats,lb_th)
                else:
                    lb_player = await ClanWarLeaderboardPlayer.calculate(stats,lb_th,leaderboard_clans)
                if lb_player.wars_participated > 0:
                    leaderboard.leaderboard_players[lb_th].append(lb_player)
        
        leaderboard.timestamp = pendulum.now()
        return await leaderboard.get_embed()
    
    async def get_embed(self):
        embed = await clash_embed(
            context=self.bot,
            title=f"**Clan War Leaderboard: {self.season.description}**",
            message=f"***Ranks players by number of War Triples achieved in the month.***"
                + (f"\nLast Refreshed: <t:{getattr(self.timestamp,'int_timestamp',0)}:R>" if self.season.is_current and self.timestamp else "")
                + f"\n\n"
                + f"- You must have participated in at least 1 eligible war to be considered for the Leaderboard."
                + f"\n- Only regular Clan Wars are included (friendly & CWL wars excluded)."
                + (f"\n- Only Wars with Clans linked to this Server are included." if not self.parent.is_global else "")
                + f"\n- Townhall levels are captured from the specific War you participated in."
                + f"\n- Leaderboard resets at the end of every month."
                + f"\n\n{EmojisUI.SPACER}{EmojisUI.SPACER}`{'':<2}{'TRP':>3}{'':<4}{'ATT':>3}{'':<4}{'WARS':>4}{'':<4}{'AVG':>3}{'':<4}{'HITRT':>5}{'':<2}`"
                )
        
        th_iter = AsyncIter(eligible_townhalls)
        async for lb_th in th_iter:
            wl_players = self.leaderboard_players.get(lb_th,[])
            wl_players.sort(
                key=lambda x: (getattr(x,'total_triples',0),getattr(x,'hit_rate',0)),
                reverse=True
                )
            if len(wl_players) > 0:
                embed.add_field(
                    name=f"**TH{lb_th}**",
                    value="\n".join([
                        f"{EmojisTownHall.get(lb_th)}{p.stats.home_clan.emoji}`{'':<2}{p.total_triples:>3}{'':<4}{p.total_attacks:>3}{'':<4}{p.wars_participated:>4}{'':<4}{p.avg_stars:>3}{'':<4}{str(p.hit_rate)+'%':>5}{'':<2}`\u3000{re.sub('[_*/]','',p.clean_name)}"
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
        leaderboard = cls(parent,season)
        
        filter_criteria = {
            'is_member':True,
            'activity':'loot_darkelixir',
            'change': {'$gt':0},
            'timestamp': {
                '$gt':season.season_start.int_timestamp,
                '$lte':season.season_end.int_timestamp
                }
            }
        query = GlobalClient.database.db__player_activity.find(filter_criteria,{'tag':1})

        member_tags = list(set([p['tag'] async for p in query]))
        leaderboard_clans = await leaderboard.parent.get_leaderboard_clans() if not parent.is_global else None
        
        async for player in GlobalClient.coc_client.get_players(member_tags):
            stats = await player.get_season_stats(season)
            if not stats.is_member:
                continue
            if leaderboard_clans and stats.home_clan_tag not in [c.tag for c in leaderboard_clans]:
                continue

            th_iter = AsyncIter(eligible_townhalls)
            async for lb_th in th_iter:
                if stats.town_hall == lb_th:
                    lb_player = await ResourceLootLeaderboardPlayer.calculate(stats,lb_th)
                    leaderboard.leaderboard_players[lb_th].append(lb_player)
        
        leaderboard.timestamp = pendulum.now()
        return await leaderboard.get_embed()
    
    async def get_embed(self):
        embed = await clash_embed(
            context=self.bot,
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
        th_iter = AsyncIter(eligible_townhalls)
        async for lb_th in th_iter:
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
        leaderboard = cls(parent,season)

        filter_criteria = {
            'is_member':True,
            'activity':'donations_sent',
            'change': {'$gt':0},
            'timestamp': {
                '$gt':season.season_start.int_timestamp,
                '$lte':season.season_end.int_timestamp
                }
            }
        query = GlobalClient.database.db__player_activity.find(filter_criteria,{'tag':1})
        member_tags = list(set([p['tag'] async for p in query]))

        leaderboard_clans = await leaderboard.parent.get_leaderboard_clans() if not parent.is_global else None

        async for player in GlobalClient.coc_client.get_players(member_tags):
            stats = await player.get_season_stats(season)
            if not stats.is_member:
                continue
            if leaderboard_clans and stats.home_clan_tag not in [c.tag for c in leaderboard_clans]:
                continue

            th_iter = AsyncIter(eligible_townhalls)
            async for lb_th in th_iter:
                if stats.town_hall == lb_th:
                    lb_player = await DonationsLeaderboardPlayer.calculate(stats,lb_th)
                    leaderboard.leaderboard_players[lb_th].append(lb_player)
        
        leaderboard.timestamp = pendulum.now()
        return await leaderboard.get_embed()
    
    async def get_embed(self):
        embed = await clash_embed(
            context=self.bot,
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
        th_iter = AsyncIter(eligible_townhalls)
        async for lb_th in th_iter:
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
        leaderboard = cls(parent,season)
        leaderboard_clans = await leaderboard.parent.get_leaderboard_clans()

        query_doc = {
            'is_member':True,
            'activity':'clan_games',
            'timestamp': {
                '$gt':season.season_start.int_timestamp,
                '$lte':season.season_end.int_timestamp
                },            
            'change': {'$gt':0}
            }
        query = GlobalClient.database.db__player_activity.find(query_doc,{'tag':1})
        member_tags = list(set([p['tag'] async for p in query]))
        
        async for player in GlobalClient.coc_client.get_players(member_tags):
            stats = await player.get_season_stats(season)

            if not stats.is_member:
                continue

            if parent.is_global:
                if stats.home_clan_tag and stats.home_clan_tag == stats.clangames.clan_tag:
                    lb_player = await ClanGamesLeaderboardPlayer.calculate(stats)
                    leaderboard.leaderboard_players['global'].append(lb_player)
            
            else:
                leaderboard_clans.sort(key=lambda x:(x.level,x.capital_hall),reverse=True)

                clan_iter = AsyncIter(leaderboard_clans)
                async for c in clan_iter:
                    if stats.home_clan_tag and stats.home_clan_tag == stats.clangames.clan_tag and stats.clangames.clan_tag == c.tag:
                        lb_player = await ClanGamesLeaderboardPlayer.calculate(stats)
                        leaderboard.leaderboard_players[c.tag].append(lb_player)
        
        leaderboard.timestamp = pendulum.now()
        return await leaderboard.get_embed()
    
    async def get_embed(self):
        embed = await clash_embed(
            context=self.bot,
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

            a_iter = AsyncIter(wl_players[:20])
            async for i,p in a_iter.enumerate(start=1):
                try:
                    clan = await self.coc_client.get_clan(p.clangames_clan_tag)
                except coc.NotFound:
                    continue                
                leaderboard_text += f"\n`{i:<3}{p.score:>6,}{p.time_to_completion:>13}{'':<2}`\u3000{clan.emoji}{EmojisTownHall.get(p.stats.town_hall)} {re.sub('[_*/]','',p.clean_name)}"
            embed.description += leaderboard_text
        
        else:
            leaderboard_clans = await self.parent.get_leaderboard_clans()
            clan_iter = AsyncIter(leaderboard_clans)
            async for clan in clan_iter:
                wl_players = self.leaderboard_players.get(clan.tag,[])
                wl_players.sort(key=lambda x: (x.score,(x.completion_seconds * -1)),reverse=True)

                if len(wl_players) > 0:
                    embed.add_field(
                        name=f"{clan.emoji} **{clan.clean_name}**",
                        value=f"`{'':<3}{'Score':>6}{'Time':>13}{'':<2}`\n"
                            + "\n".join([
                            f"`{i:<3}{p.score:>6,}{p.time_to_completion:>13}{'':<2}`\u3000{EmojisTownHall.get(p.stats.town_hall)} {re.sub('[_*/]','',p.clean_name)}"
                            for i,p in enumerate(wl_players[:3],start=1)]),
                        inline=False
                        )
                else:
                    embed.add_field(
                        name=f"{clan.emoji} **{clan.clean_name}**",
                        value=f"{EmojisUI.SPACER}<a:barbarian_bored:1156458893900267520> *It's a little lonely... there's no one participating :(.*",
                        inline=False
                        )
        return embed