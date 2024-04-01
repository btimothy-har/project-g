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
        
    def to_json(self):
        return {
            'season_total':self.season_total,
            'last_capture':self.last_capture
            }
    
    def load_from_database(self,data:Dict):
        self.season_total = data.get('season_total',0)
        self.last_capture = data.get('last_capture',0)
    
    def compute_stat(self,activities:List[aPlayerActivity]) -> 'aPlayerStat':
        if len(activities) == 0:
            return self
        self.season_total = sum([activity.change for activity in activities])
        self.last_capture = activities[-1].new_value
        return self

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
        '_starting_time',
        '_score',
        '_ending_time'
        ]
    
    def __init__(self,tag:str,season:aClashSeason):
        self.tag = tag
        self.season = season
        
        self.clan_tag = None
        self._starting_time = None
        self._score = 0
        self._ending_time = None
    
    def to_json(self):
        return {
            'clan_tag':self.clan_tag,
            'starting_time':self._starting_time,
            'score':self._score,
            'ending_time':self._ending_time
            }
    
    def load_from_database(self,data:Dict):
        self.clan_tag = data.get('clan_tag',None)
        self._starting_time = data.get('starting_time',None)
        self._score = data.get('score',0)
        self._ending_time = data.get('ending_time',None)
    
    def compute_stat(self,activities:List[aPlayerActivity]) -> 'aPlayerClanGames':
        if len(activities) == 0:
            return self
        first_entry = activities[0]
        last_entry = activities[-1]

        self.clan_tag = first_entry.clan_tag
        self.starting_time = first_entry.timestamp.int_timestamp

        self._score = sum([activity.change for activity in activities if activity.activity == 'clan_games'])
        self._ending_time = last_entry.timestamp.int_timestamp
        return self
    
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
    def starting_time(self) -> Optional[pendulum.DateTime]:
        return pendulum.from_timestamp(self._starting_time) if self._starting_time else None 
    @property
    def ending_time(self) -> Optional[pendulum.DateTime]:
        if self.is_completed:
            return pendulum.from_timestamp(self._ending_time)
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
        mem_snapshot = await self.database.db_player_member_snapshot.find_one(self.snapshot_id)
        
        if mem_snapshot:
            self.name = mem_snapshot.get('name',None)
            self.town_hall = mem_snapshot.get('town_hall',0)
            self.is_member = mem_snapshot.get('is_member',False)
            self.home_clan_tag = mem_snapshot.get('home_clan_tag',None)
            self.home_clan = await BasicClan(tag=self.home_clan_tag) if self.home_clan_tag else None

        stats_snapshot = await self.database.db_player_seasonstats_snapshot.find_one(self.snapshot_id)

        if stats_snapshot:
            self.time_in_home_clan = stats_snapshot.get('time_in_home_clan',0)
            self.last_seen = [pendulum.from_timestamp(ts) for ts in stats_snapshot.get('last_seen',[])]

            self.attack_wins.load_from_database(stats_snapshot.get('attack_wins',{}))
            self.defense_wins.load_from_database(stats_snapshot.get('defense_wins',{}))
            self.donations_sent.load_from_database(stats_snapshot.get('donations_sent',{}))
            self.donations_rcvd.load_from_database(stats_snapshot.get('donations_received',{}))
            self.loot_gold.load_from_database(stats_snapshot.get('loot_gold',{}))
            self.loot_elixir.load_from_database(stats_snapshot.get('loot_elixir',{}))
            self.loot_darkelixir.load_from_database(stats_snapshot.get('loot_darkelixir',{}))
            self.capital_contribution.load_from_database(stats_snapshot.get('capital_contribution',{}))
            self.clan_games.load_from_database(stats_snapshot.get('clan_games',{}))
        
    @property
    def snapshot_id(self):
        return {
            'season':self.season.id,
            'tag':self.tag
            }    
    
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
    
    def member_json(self):
        return {
            'tag':self.tag,
            'season':self.season.id,
            'name':self.name,
            'town_hall':self.town_hall,
            'is_member':self.is_member,
            'home_clan_tag':self.home_clan_tag,
            }
    def stats_json(self):
        return {
            'time_in_home_clan':self.time_in_home_clan,
            'last_seen':[ts.int_timestamp for ts in self.last_seen],
            'attack_wins':self.attack_wins.to_json(),
            'defense_wins':self.defense_wins.to_json(),
            'donations_sent':self.donations_sent.to_json(),
            'donations_received':self.donations_rcvd.to_json(),
            'loot_gold':self.loot_gold.to_json(),
            'loot_elixir':self.loot_elixir.to_json(),
            'loot_darkelixir':self.loot_darkelixir.to_json(),
            'capital_contribution':self.capital_contribution.to_json(),
            'clan_games':self.clan_games.to_json()
            }
    
    @classmethod
    async def create_member_snapshot(cls,tag:str,season:aClashSeason):
        if season.is_current:
            player_season = await cls(tag,season)

            await player_season.database.db_player_member_snapshot.update_one(
                {'_id':player_season.snapshot_id},
                {'$set':player_season.member_json()},
                upsert=True
                )
    
    @classmethod
    async def create_stats_snapshot(cls,tag:str,season:aClashSeason):
        player_season = await cls(tag,season)
        season_entries = await aPlayerActivity.get_by_player_season(player_season.tag,player_season.season)
        
        player_season._activity_count = len(season_entries)
        
        if player_season._activity_count > 0:
            if player_season.home_clan:
                a_iter = AsyncIter([a for a in season_entries if not a._legacy_conversion])
                ts = None
                async for a in a_iter:
                    if not ts:
                        if a.clan_tag == player_season.home_clan_tag:
                            ts = a._timestamp
                    if ts:
                        if a.clan_tag == player_season.home_clan_tag:                   
                            player_season.time_in_home_clan += max(0,a._timestamp - ts)
                        ts = a._timestamp

            if player_season.is_member and len([a.new_value for a in season_entries if a.activity == 'time_in_home_clan']) > 0:
                player_season.time_in_home_clan += sum([a.new_value for a in season_entries if a.activity == 'time_in_home_clan'])

            player_season.last_seen = [a.timestamp for a in season_entries if a.is_online_activity]

            player_season.attack_wins.compute_stat([a for a in season_entries if a.activity == 'attack_wins'])
            player_season.defense_wins.compute_stat([a for a in season_entries if a.activity == 'defense_wins'])
            player_season.donations_sent.compute_stat([a for a in season_entries if a.activity == 'donations_sent'])
            player_season.donations_rcvd.compute_stat([a for a in season_entries if a.activity == 'donations_received'])
            player_season.loot_gold.compute_stat([a for a in season_entries if a.activity == 'loot_gold'])
            player_season.loot_elixir.compute_stat([a for a in season_entries if a.activity == 'loot_elixir'])
            player_season.loot_darkelixir.compute_stat([a for a in season_entries if a.activity == 'loot_darkelixir'])
            player_season.capital_contribution.compute_stat([a for a in season_entries if a.activity == 'capital_contribution'])
            player_season.clan_games.compute_stat([a for a in season_entries if a.activity == 'clan_games'])
        
            await player_season.database.db_player_seasonstats_snapshot.update_one(
                {'_id':player_season.snapshot_id},
                {'$set':player_season.stats_json()},
                upsert=True
                )