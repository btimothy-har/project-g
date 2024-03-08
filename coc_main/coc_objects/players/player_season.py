import pendulum
import logging

from typing import *
from numerize import numerize
from async_property import AwaitLoader

from redbot.core.utils import AsyncIter

from .player_activity import aPlayerActivity

from ..season.season import aClashSeason
from ..clans.clan import BasicClan

from ...client.db_client import MotorClient
from ...utils.utils import check_rtl

LOG = logging.getLogger("coc.main")

##################################################
#####
##### PLAYER STAT
#####
##################################################
class aPlayerStat():
    __slots__ = [
        'tag',
        'season',
        'description',
        'season_total',
        'last_capture'
        ]
    
    def __init__(self,tag:str,season:aClashSeason,description:str):
        self.tag = tag
        self.season = season
        self.description = description
        
        self.season_total = 0
        self.last_capture = 0

    def __str__(self):
        if self.last_capture >= 2000000000:
            return "max"
        if self.season_total >= 100000:
            return f"{numerize.numerize(self.season_total,2)}"
        else:
            return f"{self.season_total:,}"
    
    def compute_stat(self,activities:List[aPlayerActivity]):
        if len(activities) == 0:
            return 0
        
        self.season_total = sum([activity.change for activity in activities])
        self.last_capture = activities[-1].new_value

##################################################
#####
##### CLAN GAMES
#####
##################################################    
class aPlayerClanGames():
    __slots__ = [
        'tag',
        'season',
        'clan_tag',
        'starting_time',
        '_score',
        '_ending_time'
        ]
    
    def __init__(self,tag:str,season:aClashSeason):
        self.tag = tag
        self.season = season
        
        self.clan_tag = None
        self.starting_time = None
        self._score = 0
        self._ending_time = None
    
    def compute_stat(self,activities:List[aPlayerActivity]) -> int:
        if len(activities) == 0:
            return 0
        first_entry = activities[0]
        last_entry = activities[-1]

        self.clan_tag = first_entry.clan_tag
        self.starting_time = first_entry.timestamp

        self._score = sum([activity.change for activity in activities if activity.activity == 'clan_games'])
        self._ending_time = last_entry.timestamp
    
    @property
    def games_start(self):
        return self.season.clangames_start
    @property
    def games_end(self):
        return self.season.clangames_end    
    @property
    def is_participating(self) -> bool:
        return self.clan_tag is not None    
    @property
    def is_completed(self) -> bool:
        return self.score >= self.season.clangames_max    
    @property
    def score(self) -> int:
        return min(self._score,self.season.clangames_max)    
    @property
    def ending_time(self) -> Optional[pendulum.DateTime]:
        if self.is_completed:
            return self._ending_time
        return None    
    @property
    def completion(self) -> Optional[pendulum.Duration]:
        if self.ending_time:
            return self.games_start.diff(self.ending_time)
        else:
            return None        
    @property
    def completion_seconds(self) -> int:
        if self.ending_time:
            return self.completion.in_seconds()
        else:
            return 0        
    @property
    def time_to_completion(self):
        if self.ending_time:
            if self.ending_time.int_timestamp - self.games_start.int_timestamp <= 50:
                return "Not Tracked"            
            completion_str = ""
            if self.completion.days > 0:
                completion_str += f"{self.completion.days}d"
            if self.completion.hours > 0:
                completion_str += f" {self.completion.hours}h"
            if self.completion.minutes > 0:
                completion_str += f" {self.completion.minutes}m"
            return completion_str
        else:
            return ""

class aPlayerSeason(MotorClient,AwaitLoader):
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

        self._activity_count = 0

        self.tag = tag
        self.season = season

        self.name = None
        self.town_hall = 0
        self.is_member = False
        self.home_clan_tag = None
        self.home_clan = None
        self.time_in_home_clan = 0
        self.last_seen = []
        self.attack_wins = aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='attack_wins'
            )
        self.defense_wins = aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='defense_wins'
            )
        self.donations_sent = aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='donations_sent'
            )
        self.donations_rcvd = aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='donations_received'
            )
        self.loot_gold = aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='loot_gold'
            )
        self.loot_elixir = aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='loot_elixir'
            )
        self.loot_darkelixir = aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='loot_darkelixir'
            )
        self.capital_contribution = aPlayerStat(
            tag=self.tag,
            season=self.season,
            description='capital_contribution'
            )
        self.clan_games = aPlayerClanGames(
            tag=self.tag,
            season=self.season
            )
    
    def __str__(self):
        return f"Player Stats {self.season.id}: {self.name} ({self.tag})"
    
    def __eq__(self,other):
        return isinstance(other,aPlayerSeason) and self.tag == other.tag and self.season == other.season

    async def load(self):
        season_entries = await aPlayerActivity.get_by_player_season(self.tag,self.season)

        self._activity_count = len(season_entries)        
        if self._activity_count <= 0:
            return
        
        LOG.info(f"Computing {self.tag} {season_entries}.")
            
        self.name = season_entries[-1].name
        self.town_hall = season_entries[-1].town_hall.level
        self.is_member = season_entries[-1].is_member
        
        self.home_clan_tag = season_entries[-1].home_clan_tag
        self.home_clan = await BasicClan(tag=self.home_clan_tag) if self.home_clan_tag else None

        if self.home_clan:
            a_iter = AsyncIter([a for a in season_entries if not a._legacy_conversion])
            ts = None
            async for a in a_iter:
                if not ts:
                    if a.clan_tag == a.home_clan_tag:
                        ts = a._timestamp
                if ts:
                    if a.clan_tag == a.home_clan_tag:                   
                        self.time_in_home_clan += max(0,a._timestamp - ts)
                    ts = a._timestamp
        
        if self.is_member and len([a.new_value for a in season_entries if a.activity == 'time_in_home_clan']) > 0:
            self.time_in_home_clan += sum([a.new_value for a in season_entries if a.activity == 'time_in_home_clan'])

        self.last_seen = [a.timestamp for a in season_entries if a.is_online_activity]

        self.attack_wins.compute_stat([a for a in season_entries if a.activity == 'attack_wins'])
        self.defense_wins.compute_stat([a for a in season_entries if a.activity == 'defense_wins'])
        self.donations_sent.compute_stat([a for a in season_entries if a.activity == 'donations_sent'])
        self.donations_rcvd.compute_stat([a for a in season_entries if a.activity == 'donations_received'])
        self.loot_gold.compute_stat([a for a in season_entries if a.activity == 'loot_gold'])
        self.loot_elixir.compute_stat([a for a in season_entries if a.activity == 'loot_elixir'])
        self.loot_darkelixir.compute_stat([a for a in season_entries if a.activity == 'loot_darkelixir'])
        self.capital_contribution.compute_stat([a for a in season_entries if a.activity == 'capital_contribution'])
        self.clan_games.compute_stat([a for a in season_entries if a.activity == 'clan_games'])
        
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
    
    async def create_member_snapshot(self):
        if self._activity_count <= 0:
            return
        
        snapshot_id = {
            'season':self.season.id,
            'tag':self.tag
            }
        
        if self.season.is_current:
            await self.database.db_player_member_snapshot.update_one(
                {'_id':snapshot_id},
                {'$set':{
                    'tag':self.tag,
                    'season':self.season.id,
                    'name':self.name,
                    'town_hall':self.town_hall,
                    'is_member':self.is_member,
                    'home_clan_tag':self.home_clan_tag,
                    }
                },
                upsert=True
                )
        
        else:
            find_existing = await self.database.db_player_member_snapshot.find_one(
                {'_id':snapshot_id}
                )
            if not find_existing:
                await self.database.db_player_member_snapshot.insert_one(
                    {
                        '_id':snapshot_id,
                        'tag':self.tag,
                        'season':self.season.id,
                        'name':self.name,
                        'town_hall':self.town_hall,
                        'is_member':self.is_member,
                        'home_clan_tag':self.home_clan_tag,
                        }
                    )
