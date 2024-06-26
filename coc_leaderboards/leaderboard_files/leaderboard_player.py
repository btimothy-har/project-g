from typing import *

from redbot.core.utils import AsyncIter

from coc_main.client.global_client import GlobalClient

from coc_main.coc_objects.players.player import aPlayerSeason
from coc_main.coc_objects.clans.clan import aClan
from coc_main.coc_objects.events.clan_war_v2 import bClanWar, bWarAttack
from coc_main.coc_objects.events.war_summary import aClanWarSummary

from coc_main.utils.constants.coc_constants import ClanWarType
from coc_main.utils.utils import check_rtl

class ClanWarLeaderboardPlayer(GlobalClient):
    __slots__ = [
        'stats',
        'tag',
        'name',
        'for_th',
        'wars_participated',
        'total_attacks',
        'total_triples',
        'total_stars',
        'total_destruction',
        'hit_rate',
        'avg_stars'
        ]
    
    def __init__(self,player_season:aPlayerSeason,leaderboard_th:int):
        self.stats = player_season
        self.tag = player_season.tag
        self.name = player_season.name
        self.for_th = leaderboard_th

        self.wars_participated = 0
        self.total_attacks = 0
        self.total_triples = 0
        self.total_stars = 0
        self.total_destruction = 0.0

        self.hit_rate = 0
        self.avg_stars = 0.0
    
    @property
    def clean_name(self) -> str:
        if check_rtl(self.name):
            return '\u200F' + self.name + '\u200E'
        return self.name
    
    @classmethod
    async def calculate(cls,
        player_season:aPlayerSeason,
        leaderboard_th:int,
        eligible_clans:Optional[List[aClan]]=None):

        def predicate_war(clan_war:bClanWar):
            if eligible_clans:
                return getattr(clan_war,'type') == ClanWarType.RANDOM and getattr(clan_war,'is_alliance_war',False) and (clan_war.clan_1.tag in e_clans or clan_war.clan_2.tag in e_clans)
            else:
                return getattr(clan_war,'type') == ClanWarType.RANDOM and getattr(clan_war,'is_alliance_war',False)
        
        def predicate_lb_attack(attack:bWarAttack):
            return attack.attacker.town_hall <= attack.defender.town_hall
            
        lb_player = cls(player_season,leaderboard_th)
        if eligible_clans:
            e_clans = [c.tag for c in eligible_clans]
        else:
            e_clans = []

        war_log = await GlobalClient.coc_client.get_clan_wars_for_player(player_season.tag,player_season.season)
        war_stats = aClanWarSummary.for_player(
            player_tag=player_season.tag,
            war_log=war_log
            )

        participated_wars = AsyncIter(war_stats.war_log)
        async for war in participated_wars.filter(predicate_war):
            war_member = war.get_member(lb_player.tag)

            if war_member.town_hall == lb_player.for_th:
                lb_player.wars_participated += 1

                attacks = AsyncIter(war_member.attacks)
                async for att in attacks.filter(predicate_lb_attack):
                    lb_player.total_attacks += 1
                    lb_player.total_triples += 1 if att.is_triple else 0
                    lb_player.total_stars += att.stars
                    lb_player.total_destruction += att.destruction
        
        if lb_player.total_attacks > 0:
            lb_player.hit_rate = int(round((lb_player.total_triples / lb_player.total_attacks) * 100,0))
            lb_player.avg_stars = round(lb_player.total_stars / lb_player.total_attacks,1)        
        return lb_player

class ResourceLootLeaderboardPlayer():
    def __init__(self,player_season:aPlayerSeason,leaderboard_th:int):
        self.stats = player_season
        self.tag = player_season.tag
        self.name = player_season.name
        self.for_th = leaderboard_th

        self.loot_darkelixir = self.stats.loot_darkelixir.season_total
        self._loot_elixir = self.stats.loot_elixir
        self._loot_gold = self.stats.loot_gold
    
    @property
    def clean_name(self) -> str:
        if check_rtl(self.name):
            return '\u200F' + self.name + '\u200E'
        return self.name    
    @classmethod
    async def calculate(cls,player_season:aPlayerSeason,leaderboard_th:int):        
        lb_player = cls(player_season,leaderboard_th)
        return lb_player  
    @property
    def loot_elixir(self):
        return str(self._loot_elixir)    
    @property
    def loot_gold(self):
        return str(self._loot_gold)

class DonationsLeaderboardPlayer():
    def __init__(self,player_season:aPlayerSeason,leaderboard_th:int):
        self.stats = player_season
        self.tag = player_season.tag
        self.name = player_season.name
        self.for_th = leaderboard_th

        self.donations_sent = self.stats.donations_sent.season_total
        self.donations_rcvd = self.stats.donations_rcvd.season_total
    
    @property
    def clean_name(self) -> str:
        if check_rtl(self.name):
            return '\u200F' + self.name + '\u200E'
        return self.name
    
    @classmethod
    async def calculate(cls,player_season:aPlayerSeason,leaderboard_th:int):        
        lb_player = cls(player_season,leaderboard_th)
        return lb_player

class ClanGamesLeaderboardPlayer():
    def __init__(self,player_season:aPlayerSeason):
        self.stats = player_season
        self.tag = player_season.tag
        self.name = player_season.name

        self.score = self.stats.clangames.score
        self.clangames_clan_tag = self.stats.clangames.clan_tag
        self.time_to_completion = self.stats.clangames.time_to_completion
        self.completion_seconds = self.stats.clangames.completion_seconds
    
    @property
    def clean_name(self) -> str:
        if check_rtl(self.name):
            return '\u200F' + self.name + '\u200E'
        return self.name
    
    @classmethod
    async def calculate(cls,player_season:aPlayerSeason):
        lb_player = cls(player_season)
        return lb_player