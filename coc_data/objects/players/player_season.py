import asyncio
import pendulum

from typing import *
from mongoengine import *

from redbot.core.utils import AsyncIter, deduplicate_iterables

from coc_client.api_client import BotClashClient

from ..clans.clan import aClan
from ..events.clan_war import aClanWar
from ..events.clan_war_summary import aSummaryWarStats
from ..events.raid_weekend import aRaidWeekend
from ..events.raid_weekend import aSummaryRaidStats

from .value_playerstats import aPlayerStat
from .value_clangames import aPlayerClanGames

from ...constants.coc_constants import *

##################################################
#####
##### DATABASE
#####
##################################################
class db_PlayerStats(Document):
    #ID using format {'season':'1-2023','tag':'#12345678'}
    stats_id = DictField(primary_key=True,required=True)
    season = StringField(required=True)
    tag = StringField(required=True)    
    timestamp = IntField(default=0)
    name = StringField(default="")
    town_hall = IntField(default=0)
    is_member = BooleanField(default=False)
    home_clan = StringField(default="")
    other_clans = ListField(StringField(),default=[])
    time_in_home_clan = IntField(default=0)        
    last_seen = ListField(IntField(),default=[])    
    attacks = DictField(default={})
    defenses = DictField(default={})
    donations_sent = DictField(default={})
    donations_rcvd = DictField(default={})
    loot_gold = DictField(default={})
    loot_elixir = DictField(default={})
    loot_darkelixir = DictField(default={})
    capitalcontribution = DictField(default={})
    clangames = DictField(default={})

##################################################
#####
##### PLAYER SEASON STATS OBJECT
#####
##################################################
class aPlayerSeason():
    _cache = {}

    def __new__(cls,player,season):
        if (player.tag,season.id) not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[(player.tag,season.id)] = instance
        return cls._cache[(player.tag,season.id)]
    
    def __init__(self,player,season):
        self.client = BotClashClient()
        self.bot = self.client.bot
        
        self.tag = player.tag
        self.season = season

        if self.is_current_season:
            self.name = player.name
            self.home_clan_tag = player._attributes._home_clan_tag
            self.is_member = player.is_member
               
        if self._is_new:
            self._update_lock = asyncio.Lock()

            stats = {}
            try:
                stats = db_PlayerStats.objects.get(
                    stats_id=self.season_db_id
                    ).to_mongo().to_dict()
            except DoesNotExist:
                stats = {}

            self.update_time = pendulum.from_timestamp(stats.get('timestamp',0)) if stats.get('timestamp',0) > 0 else player.timestamp

            if not self.is_current_season:
                self.name = stats.get('name','') if len(stats.get('name','')) > 0 else player.name
                self.home_clan_tag = stats.get('home_clan',None) if stats.get('home_clan',None) else None
                self.is_member = stats.get('is_member',False)

            self.town_hall = stats.get('town_hall',0) if stats.get('town_hall',0) > 0 else player.town_hall.level            
                
            self.other_clan_tags = stats.get('other_clans',[])
            self.time_in_home_clan = stats.get('time_in_home_clan',0)
            self.last_seen = [pendulum.from_timestamp(x) for x in stats.get('last_seen',[])]            

            self.attacks = aPlayerStat(
                tag=self.tag,
                season=self.season,
                stat_name='attack_wins',
                api_value=player.attack_wins,
                dict_value=stats.get('attacks',{})
                )
            self.defenses = aPlayerStat(
                tag=self.tag,
                season=self.season,
                stat_name='defense_wins',
                api_value=player.attack_wins,
                dict_value=stats.get('defenses',{})
                )
            self.donations_sent = aPlayerStat(
                tag=self.tag,
                season=self.season,
                stat_name='donations_sent',
                api_value=player.donations,
                dict_value=stats.get('donations_sent',{})
                )                
            self.donations_rcvd = aPlayerStat(
                tag=self.tag,
                season=self.season,
                stat_name='donations_rcvd',
                api_value=player.received,
                dict_value=stats.get('donations_rcvd',{})
                )                
            self.loot_gold = aPlayerStat(
                tag=self.tag,
                season=self.season,
                stat_name='loot_gold',
                api_value=getattr(player.get_achievement('Gold Grab'),'value',0),
                dict_value=stats.get('loot_gold',{})
                )                
            self.loot_elixir = aPlayerStat(
                tag=self.tag,
                season=self.season,
                stat_name='loot_elixir',
                api_value=getattr(player.get_achievement('Elixir Escapade'),'value',0),
                dict_value=stats.get('loot_elixir',{})
                )                
            self.loot_darkelixir = aPlayerStat(
                tag=self.tag,
                season=self.season,
                stat_name='loot_darkelixir',
                api_value=getattr(player.get_achievement('Heroic Heist'),'value',0),
                dict_value=stats.get('loot_darkelixir',{})
                )                
            self.capitalcontribution = aPlayerStat(
                tag=self.tag,
                season=self.season,
                stat_name='capitalcontribution',
                api_value=getattr(player.get_achievement('Most Valuable Clanmate'),'value',0),
                dict_value=stats.get('capitalcontribution',{})
                )                
            self.clangames = aPlayerClanGames(
                tag=self.tag,
                season=self.season,
                api_value=getattr(player.get_achievement('Games Champion'),'value',0),
                dict_value=stats.get('clangames',{})
                )
            
            self.compute_war_stats()
            self.compute_raid_stats()

            self.player = player
            
        self._is_new = False
    
    def __str__(self):
        return f"Player Stats {self.season.id}: {self.name} ({self.tag})"    
    def __eq__(self,other):
        return isinstance(other,aPlayerSeason) and self.tag == other.tag and self.season == other.season
    @property
    def season_db_id(self):
        return {'season': self.season.id,'tag': self.tag}    
    @property
    def is_current_season(self):
        return self.season.is_current
    @property
    def home_clan(self):
        return aClan.from_cache(self.home_clan_tag)
    
    @property
    def war_stats(self):
        if self.is_current_season and (pendulum.now().int_timestamp - self._war_stats.timestamp.int_timestamp) >= 3600:
            self.compute_war_stats()
        return self._war_stats
    def compute_war_stats(self):
        self._war_stats = aSummaryWarStats.for_player(
            player_tag=self.tag,
            war_log=aClanWar.for_player(self.tag,self.season)
            )
    
    @property
    def raid_stats(self):
        if self.is_current_season and (pendulum.now().int_timestamp - self._raid_stats.timestamp.int_timestamp) >= 3600:
            self.compute_raid_stats()
        return self._raid_stats
    def compute_raid_stats(self):
        self._raid_stats = aSummaryRaidStats(
            player_tag=self.tag,
            raid_log=aRaidWeekend.for_player(self.tag,self.season)
            )

    def save(self):
        if not self.is_current_season:
            return
        db = db_PlayerStats(
            stats_id=self.season_db_id,
            season=self.season.id,
            tag=self.tag,
            timestamp=self.update_time.int_timestamp,
            name=self.name,
            town_hall=self.town_hall,
            is_member=self.is_member,
            home_clan=self.home_clan_tag,
            other_clans=self.other_clan_tags,
            time_in_home_clan=self.time_in_home_clan,
            last_seen=[x.int_timestamp for x in self.last_seen],
            attacks=self.attacks.json,
            defenses=self.defenses.json,
            donations_sent=self.donations_sent.json,
            donations_rcvd=self.donations_rcvd.json,
            loot_gold=self.loot_gold.json,
            loot_elixir=self.loot_elixir.json,
            loot_darkelixir=self.loot_darkelixir.json,
            capitalcontribution=self.capitalcontribution.json,
            clangames=self.clangames.json
            )
        db.save()    

    async def update_data(self,player):
        updated = 0
        bank_cog = player.bot.get_cog('Bank')        
        
        if player.timestamp >= self.season.cwl_end:            
            if player.is_member and player.clan.tag == self.home_clan_tag:
                if max((player.timestamp.int_timestamp - self.update_time.int_timestamp),0) > 0:
                    self.time_in_home_clan += max((player.timestamp.int_timestamp - self.update_time.int_timestamp),0)
                    self.client.cog.coc_data_log.debug(
                        f'{self}: time in home clan updated to {self.time_in_home_clan}.'
                        )
                    updated += 1                    

        if player.clan.tag not in self.other_clan_tags and player.clan.tag != None:
            self.other_clan_tags.append(player.clan.tag)            
            self.client.cog.coc_data_log.debug(
                f'{self}: other clan {player.clan.tag} {player.clan.name} added.'
                )
            updated += 1
        
        if bank_cog and player.town_hall.level > self.town_hall:
            asyncio.create_task(bank_cog.member_th_progress_reward(
                player=player,
                cached_value=self.town_hall
                ))
        self.town_hall = player.town_hall.level
            
        if bank_cog and player.hero_strength > self.player.hero_strength:
            asyncio.create_task(bank_cog.member_hero_upgrade_reward(
                player=player,
                cached_value=self.player.hero_strength
                ))

        updated += await self.attacks.update_stat(
            player=player,
            new_value=player.attack_wins
            )
        updated += await self.defenses.update_stat(
            player=player,
            new_value=player.defense_wins
            )
        updated += await self.donations_sent.update_stat(
            player=player,
            new_value=player.donations
            )
        updated += await self.donations_rcvd.update_stat(
            player=player,
            new_value=player.received
            )
        updated += await self.loot_gold.update_stat(
            player=player,
            new_value=getattr(player.get_achievement('Gold Grab'),'value',0),
            only_incremental=True
            )
        updated += await self.loot_elixir.update_stat(
            player=player,
            new_value=getattr(player.get_achievement('Elixir Escapade'),'value',0),
            only_incremental=True
            )
        updated += await self.loot_darkelixir.update_stat(
            player=player,
            new_value=getattr(player.get_achievement('Heroic Heist'),'value',0),
            only_incremental=True
            )
        cap_contri = await self.capitalcontribution.update_stat(
            player=player,
            new_value=getattr(player.get_achievement('Most Valuable Clanmate'),'value',0),
            only_incremental=True
            )   
        updated += cap_contri     
        updated += await self.clangames.calculate_clangames(player)

        if cap_contri > 0:
            if bank_cog and getattr(player.clan,'is_alliance_clan',False):
                asyncio.create_task(bank_cog.capital_contribution_rewards(player,cap_contri))            
            await self.client.cog.capital_contribution_feed(player,cap_contri)

        return updated
    
    async def compute_last_seen(self,new_player):
        updated = 0
        if new_player.name != self.player.name or new_player.war_opted_in != self.player.war_opted_in or len([l.id for l in new_player.labels if l.id not in [l.id for l in self.player.labels]]) > 0:
            self.last_seen.append(new_player.timestamp)
            updated += 1
            self.client.cog.coc_data_log.debug(
                f'{self}: added {new_player.timestamp} to last_seen.'
                )
        else:
            async for achievement in AsyncIter(new_player.achievements):
                if achievement.name in activity_achievements:
                    if achievement.value != self.player.get_achievement(achievement.name).value:
                        self.last_seen.append(new_player.timestamp)
                        updated += 1
                        self.client.cog.coc_data_log.debug(
                            f'{self}: added {new_player.timestamp} to last_seen.'
                            )
                        break
        self.last_seen = deduplicate_iterables(self.last_seen)
        self.last_seen.sort(key=lambda x:x.int_timestamp)
        return updated