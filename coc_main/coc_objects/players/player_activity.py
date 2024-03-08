import bson
import pendulum

from typing import *

from ...client.db_client import MotorClient

from .townhall import aTownHall
from ..season.season import aClashSeason

valid_activity_types = [
    'snapshot',
    'time_in_home_clan',
    'change_name',
    'change_war_option',
    'change_label',
    'upgrade_townhall',
    'upgrade_townhall_weapon',
    'upgrade_hero',
    'upgrade_troop',
    'upgrade_spell',
    'leave_clan',
    'join_clan',
    'trophies',
    'attack_wins',
    'defense_wins',
    'war_stars',
    'donations_sent',
    'donations_received',
    'capital_contribution',
    'loot_capital_gold',
    'loot_gold',
    'loot_elixir',
    'loot_darkelixir',    
    'clan_games'
    ]

class aPlayerActivity(MotorClient):
    __slots__ = [
        '_id',
        '_timestamp',
        '_read_by_bank',
        '_legacy_conversion',
        'tag',
        'name',
        'is_member',
        'discord_user',
        'town_hall',
        'home_clan_tag',
        'clan_tag',
        'activity',
        'stat',
        'change',      
        'new_value'        
        ]
    
    @classmethod
    async def get_by_id(cls,aid:str) -> Optional['aPlayerActivity']:
        entry = await cls.database.db__player_activity.find_one({'_id':bson.ObjectId(aid)})
        if entry:
            return cls(entry)
        return None

    @classmethod
    async def get_last_for_player_by_type(cls,tag:str,activity:str) -> Optional['aPlayerActivity']:
        filter_criteria = {
            'tag':tag,
            'activity':activity,
            'legacy_conversion':{"$exists": False}
            }
        query = cls.database.db__player_activity.find(filter_criteria).sort('timestamp',-1).limit(1)
        entry = await query.to_list(1)
        s = sorted(entry,key=lambda x: x['timestamp'],reverse=True)
        if len(s) > 0:
            return cls(s[0])
        return None
    
    @classmethod
    async def get_by_player_season(cls,tag:str,season:aClashSeason) -> List[Optional['aPlayerActivity']]:
        filter_criteria = {
            'tag':tag,
            'timestamp': {
                '$gt':season.season_start.int_timestamp,
                '$lte':season.season_end.int_timestamp
                }
            }
        
        query = cls.database.db__player_activity.find(filter_criteria).sort('timestamp',-1)
        entries = [cls(entry) async for entry in query]
        return sorted(entries,key=lambda x: x._timestamp)

    @classmethod
    async def get_by_player_datetime(cls,tag:str,start:pendulum.DateTime,end:pendulum.DateTime) -> List[Optional['aPlayerActivity']]:
        filter_criteria = {
            'tag':tag,
            'timestamp': {
                '$gt':start.int_timestamp,
                '$lte':end.int_timestamp
                }
            }
        
        query = cls.database.db__player_activity.find(filter_criteria).sort('timestamp',-1)
        entries = [cls(entry) async for entry in query]
        return sorted(entries,key=lambda x: x._timestamp)
    
    @classmethod
    async def get_by_type_for_bank(cls,activity:str) -> List[Optional['aPlayerActivity']]:
        filter_criteria = {
            'activity':activity,
            'read_by_bank':False
            }
        query = cls.database.db__player_activity.find(filter_criteria).sort('timestamp',1)
        entries = [cls(entry) async for entry in query]
        return entries

    @classmethod
    async def create_new(cls,player,timestamp:pendulum.DateTime,activity:str,**kwargs) -> 'aPlayerActivity':
        activity = activity.lower()
        if activity not in valid_activity_types:
            raise ValueError(f"Invalid activity type: {activity}.")

        await player._sync_cache(force=True)
        new_entry = await cls.database.db__player_activity.insert_one(
            {
                'tag':player.tag,
                'name':player.name,
                'is_member':player.is_member,
                'discord_user':player.discord_user,
                'townhall':player.town_hall.json(),
                'home_clan':getattr(player.home_clan,'tag','None'),
                'clan':getattr(player.clan,'tag','None'),
                'activity':activity,
                'stat':kwargs.get('stat',''),
                'change':kwargs.get('change',0),
                'new_value':kwargs.get('new_value',''),
                'timestamp':timestamp.int_timestamp,
                'read_by_bank':False
                }
            )
        entry = await cls.get_by_id(str(new_entry.inserted_id))
        return entry
    
    def __init__(self,database:dict):
        self._id = str(database['_id'])
        self.tag = database['tag']
        self.name = database['name']

        self.is_member = database['is_member']
        self.discord_user = database['discord_user']

        self.town_hall = aTownHall(
            level=database['townhall']['level'],
            weapon=database['townhall']['weapon']
            )
        
        self.home_clan_tag = database['home_clan'] if database['home_clan'] != 'None' else None
        self.clan_tag = database['clan'] if database['clan'] != 'None' else None

        self.activity = database['activity']
        self.stat = database['stat'] if database['stat'] != '' else None
        self.change = database['change'] if database['change'] != 0 else 0
        self.new_value = database['new_value'] if database['new_value'] != '' else None

        self._timestamp = database['timestamp']
        self._read_by_bank = database.get('read_by_bank',False)
        self._legacy_conversion = database.get('legacy_conversion',False)
    
    async def mark_as_read(self) -> None:
        await self.database.db__player_activity.update_one(
            {'_id':bson.ObjectId(self._id)},
            {'$set':{'read_by_bank':True}}
            )
        self._read_by_bank = True
    
    async def mark_as_unread(self) -> None:
        await self.database.db__player_activity.update_one(
            {'_id':bson.ObjectId(self._id)},
            {'$set':{'read_by_bank':False}}
            )
        self._read_by_bank = False

    @property
    def timestamp(self) -> pendulum.DateTime:
        return pendulum.from_timestamp(self._timestamp)
    
    @property
    def is_online_activity(self) -> bool:
        online_events = [        
            'change_name',
            'change_war_option',
            'change_label',
            'attack_wins',
            'war_stars',
            'donations_sent',
            'loot_gold',
            'loot_elixir',
            'loot_darkelixir',
            'capital_contribution',
            'loot_capital_gold',
            'clan_games'
            ]        
        return self.activity in online_events
