import pendulum

from typing import *
from async_property import AwaitLoader
from redbot.core.utils import AsyncIter

from .player_stat import aPlayerStat, aPlayerActivity
from .player_clangames import aPlayerClanGames
from .season_lock import PlayerSeason

from ..season.season import aClashSeason
from ..clans.player_clan import aPlayerClan

from ...api_client import BotClashClient as client
from ...utils.utils import check_rtl

bot_client = client()

class aPlayerSeason(AwaitLoader):
    _cache = {}
    __slots__ = [
        'tag',
        'season',
        'name',
        'town_hall',
        'is_member',
        'home_clan_tag',
        'home_clan',
        'time_in_home_clan',
        'last_seen',
        'attack_wins',
        'defense_wins',
        'donations_sent',
        'donations_rcvd',
        'loot_gold',
        'loot_elixir',
        'loot_darkelixir',
        'capital_contribution',
        'clan_games'
        ]
    
    def __init__(self,tag:str,season:aClashSeason):
        self.tag = tag
        self.season = season

        self.name = None
        self.town_hall = 0
        self.is_member = False
        self.home_clan_tag = None
        self.time_in_home_clan = 0
        self.last_seen = []
        self.attack_wins = None
        self.defense_wins = None
        self.donations_sent = None
        self.donations_rcvd = None
        self.loot_gold = None
        self.loot_elixir = None
        self.loot_darkelixir = None
        self.capital_contribution = None
        self.clan_games = None
    
    def __str__(self):
        return f"Player Stats {self.season.id}: {self.name} ({self.tag})"
    
    def __eq__(self,other):
        return isinstance(other,aPlayerSeason) and self.tag == other.tag and self.season == other.season

    async def load(self):
        season_entries = await aPlayerActivity.get_by_player_season(self.tag,self.season)
        
        if len(season_entries) <= 0:
            return
            
        self.name = season_entries[-1].name
        self.town_hall = season_entries[-1].town_hall.level
        self.is_member = season_entries[-1].is_member
        
        self.home_clan_tag = season_entries[-1].home_clan_tag
        self.home_clan = await aPlayerClan(tag=self.home_clan_tag) if self.home_clan_tag else None

        if self.home_clan:
            a_iter = AsyncIter(season_entries)
            ts = self.season.season_start.int_timestamp
            async for a in a_iter:
                if a.clan_tag == a.home_clan_tag:
                    self.time_in_home_clan += a._timestamp - ts
                ts = a._timestamp
        
        if self.is_member:            
            self.time_in_home_clan += sum([a.new_value for a in season_entries if a.activity == 'time_in_home_clan'])

        self.last_seen = [a for a in season_entries if a.is_online_activity]

        self.attack_wins = aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='attack_wins',
            activities=[a for a in season_entries if a.activity == 'attack_wins']
            )
        self.defense_wins = aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='defense_wins',
            activities=[a for a in season_entries if a.activity == 'defense_wins']
            )
        self.donations_sent = aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='donations_sent',
            activities=[a for a in season_entries if a.activity == 'donations_sent']
            )
        self.donations_rcvd = aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='donations_received',
            activities=[a for a in season_entries if a.activity == 'donations_received']
            )
        self.loot_gold = aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='loot_gold',
            activities=[a for a in season_entries if a.activity == 'loot_gold']
            )
        self.loot_elixir = aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='loot_elixir',
            activities=[a for a in season_entries if a.activity == 'loot_elixir']
            )
        self.loot_darkelixir = aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='loot_darkelixir',
            activities=[a for a in season_entries if a.activity == 'loot_darkelixir']
            )
        self.capital_contribution = aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='capital_contribution',
            activities=[a for a in season_entries if a.activity == 'capital_contribution']
            )
        self.clan_games = aPlayerClanGames(
            tag=self.tag,
            season=self.season,
            activities=[a for a in season_entries if a.activity == 'clan_games']
            )
        
    @property
    def is_current_season(self) -> bool:
        return self.season.is_current    
    @property
    def clean_name(self) -> str:
        if check_rtl(self.name):
            return '\u200F' + self.name + '\u200E'
        return self.name 
    
    @property
    def attacks(self) -> aPlayerStat:
        return self.attack_wins
    @property
    def defenses(self) -> aPlayerStat:
        return self.defense_wins    
    @property
    def donations(self) -> aPlayerStat:
        return self.donations_sent
    @property
    def received(self) -> aPlayerStat:
        return self.donations_rcvd
    @property
    def capitalcontribution(self) -> aPlayerStat:
        return self.capital_contribution
    @property
    def clangames(self) -> aPlayerClanGames:
        return self.clan_games