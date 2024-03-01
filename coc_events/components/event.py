import coc
import asyncio
import discord
import pendulum
import bson

from typing import *
from collections import defaultdict
from async_property import AwaitLoader

from redbot.core.utils import AsyncIter

from coc_main.api_client import BotClashClient as client

from coc_main.coc_objects.players.player import aPlayer
from coc_main.discord.member import aMember

from ..exceptions import EventClosed, AlreadyRegistered, NotEligible

bot_client = client()

# Participant Document
# participant = {
#   '_id':ObjectId,
#   'event_id':str,
#   'discord_id':int,
#   'tag':str,
#   'timestamp':int,
# }
##################################################
#####
##### EVENT PARTICIPANT
#####
##################################################
class Participant(aPlayer,AwaitLoader):
    def __init__(self,**kwargs):
        self._id = None
        self.participant_id = 0
        self.registered_timestamp = None
        self.event_id = kwargs.get('event_id','')
        super().__init__(**kwargs)
    
    async def load(self):
        filter = {
            'event_id':self.event_id,
            'tag':self.tag
            }        
        get_db = await bot_client.coc_db.db__event_participant.find_one(filter)

        if get_db:
            self._id = get_db['_id']
            self.participant_id = self._id
            self.registered_timestamp = pendulum.from_timestamp(get_db['timestamp'])
        await aPlayer.load(self)

    @property
    def participant(self) -> Optional[discord.User]:
        return bot_client.bot.get_user(self.discord_id)

# Event Document
# event = {
#   '_id':ObjectId,
#   'name':str,
#   'description':str,
#   'max_participants':int,
#   'members_only':bool,
#   'start_time':int,
#   'duration':int,
#   'prize_pool':int,
#   'status':[open,closed],
#   'discord_id':int,
#   'role_id':int,
#   'channel_id':int
# }
##################################################
#####
##### EVENT
#####
##################################################
class Event():
    _locks = defaultdict(asyncio.Lock)
    
    @classmethod
    async def get_event(cls,event_id:str) -> Optional['Event']:
        db = await bot_client.coc_db.db__event.find_one({'_id':bson.ObjectId(event_id)})
        if db:
            return cls(db)
        return None
    
    @classmethod
    async def get_by_channel(cls,channel_id:int) -> Optional['Event']:
        filter = {'channel_id':channel_id}
        db = await bot_client.coc_db.db__event.find_one(filter)
        if db:
            return cls(db)
        return None
    
    @classmethod
    async def get_all_active(cls) -> List['Event']:
        pipeline = [
        {
            "$addFields": {
                "end_time": {
                    "$add": [
                        "$start_time",
                        {"$multiply": ["$duration",3600]}
                    ]
                }
            }
        },
        {
            "$match": {"end_time": {"$lte": pendulum.now().int_timestamp},
            }
        }
        ]
        query = bot_client.coc_db.db__event.aggregate(pipeline)
        return [cls(event) async for event in query]
    
    @classmethod
    async def get_participating_for_user(cls,user:int) -> List['Event']:
        filter = {'discord_id':user}
        query = bot_client.coc_db.db__event_participant.find(filter)
        events = [await cls.get_event(participant['event_id']) async for participant in query]
        return [event for event in events if event.end_time > pendulum.now()]

    def __init__(self,database:dict):        
        self._id = database.get('_id',None)
        self.id = str(self._id)

        self.name = database.get('name','Unknown')
        self.description = database.get('description','')

        self.tags_per_participant = database.get('tags_per_participant',1)
        self.max_participants = database.get('max_participants',0)
        self.members_only = database.get('members_only',False)

        self.duration = database.get('duration',24)

        ts_start_time = database.get('start_time',0)
        self.start_time = pendulum.from_timestamp(ts_start_time) if ts_start_time else None
        self.end_time = self.start_time.add(hours=self.duration) if self.start_time else None

        self.prize_pool = database.get('prize_pool',0)

        self.status = database.get('status','closed')

        self.discord_id = database.get('discord_id',0)
        self.role_id = database.get('role_id',0)
        self.channel_id = database.get('channel_id',0)
    
    @property
    def lock(self) -> asyncio.Lock:
        return self._locks[self.id]
    
    @property
    def guild(self) -> Optional[discord.Guild]:
        cog = bot_client.bot.get_cog('Events')
        if cog:
            return cog.events_guild
        return None
    
    @property
    def master_role(self) -> Optional[discord.Role]:
        cog = bot_client.bot.get_cog('Events')
        if cog:
            return cog.events_role
        return None
    
    @property
    def event_role(self) -> Optional[discord.Role]:
        if self.guild and self.role_id:
            return self.guild.get_role(self.role_id)
        return None
    @property
    def event_channel(self) -> Optional[discord.TextChannel]:
        if self.guild and self.channel_id:
            return self.guild.get_channel(self.channel_id)
        return None    

    @classmethod
    async def create(cls,name:str,max_participants:int,start_time:pendulum.DateTime,**kwargs):
        new_event = await bot_client.coc_db.db__event.insert_one(
            {
            'name':name,
            'description':kwargs.get('description',''),
            'tags_per_participant':kwargs.get('tags_per_participant',1),
            'max_participants':max_participants,
            'members_only':kwargs.get('members_only',False),
            'start_time':start_time.int_timestamp,
            'duration':kwargs.get('duration',24),
            'prize_pool':kwargs.get('prize_pool',0),            
            'status':'closed'
            }
            )
        return await cls.get_event(str(new_event.inserted_id))
    
    async def edit(self,**kwargs) -> 'Event':
        async with self.lock:
            await bot_client.coc_db.db__event.update_one(
                {'_id':self._id},
                {'$set':kwargs}
                )
            return await Event.get_event(self.id)
    
    async def delete(self) -> None:
        async with self.lock:
            await bot_client.coc_db.db__event.delete_one({'_id':self._id})

    ##################################################
    ##### EVENT FUNCTIONS
    ##################################################    
    async def open_event(self) -> None:
        async with self.lock:
            await bot_client.coc_db.db__event.update_one(
                {'_id':self._id},
                {'$set':{'status':'open'}}
                )
            self.status = 'open'
    
    async def close_event(self) -> None:
        async with self.lock:
            await bot_client.coc_db.db__event.update_one(
                {'_id':self._id},
                {'$set':{'status':'closed'}}
                )
            self.status = 'closed'
    
    async def create_discord_event(self) -> discord.ScheduledEvent:
        async with self.lock:
            if self.discord_id:
                try:
                    event = await self.guild.fetch_scheduled_event(self.discord_id)
                    return event
                except discord.NotFound:
                    event = None
            
            event = await self.guild.create_scheduled_event(
                name=self.name,
                description=self.description,
                start_time=self.start_time,
                end_time=self.end_time,
                privacy_level=discord.PrivacyLevel.guild_only,
                entity_type=discord.EntityType.external,
                location="Clash of Clans"
                )
            await bot_client.coc_db.db__event.update_one(
                {'_id':self._id},
                {'$set':{'discord_id':event.id}}
                )
            self.discord_id = event.id
            return event
    
    async def create_discord_role(self) -> discord.Role:
        async with self.lock:
            if self.role_id:
                role = self.guild.get_role(self.role_id)
                if role:
                    return role
            
            role = await self.guild.create_role(
                name=self.name,
                reason="Create event role.",)
            await bot_client.coc_db.db__event.update_one(
                {'_id':self._id},
                {'$set':{'role_id':role.id}}
                )
            self.role_id = role.id

            if self.master_role:
                await role.edit(position=self.master_role.position-1)
            return role
    
    async def set_discord_channel(self,channel:discord.TextChannel) -> None:
        async with self.lock:
            await bot_client.coc_db.db__event.update_one(
                {'_id':self._id},
                {'$set':{'channel_id':channel.id}}
                )
            self.channel_id = channel.id
    
    async def sync_role(self) -> None:
        async with self.lock:
            if not self.event_role:
                return
            
            await self.event_role.edit(name=self.name)            
            participant_ids = list(set([p.participant_id for p in await self.get_all_participants()]))

            remove_role = [m for m in self.event_role.members if m.id not in participant_ids]
            add_role = [i for i in participant_ids if i not in [m.id for m in self.event_role.members]]

            rem_iter = AsyncIter(remove_role)
            async for member in rem_iter:
                await member.remove_roles(self.event_role)
            
            add_iter = AsyncIter(add_role)
            async for member_id in add_iter:
                member = self.guild.get_member(member_id)
                if member:
                    await member.add_roles(self.event_role)

    
    ##################################################
    ##### PARTICIPANT FUNCTIONS
    ##################################################
    async def register_participant(self,tag:str,user:int) -> Participant:
        async with self.lock:
            tag = coc.utils.correct_tag(tag)

            event = await Event.get_event(self.id)
            if event.status == 'closed':
                raise EventClosed()
            
            user_registrations = await self.get_participants_for_user(user)
            if len(user_registrations) >= self.max_participants:
                raise AlreadyRegistered()
            
            existing_participant = await self.get_participant(tag)
            if existing_participant:
                return existing_participant
            
            if self.members_only:
                member = await aMember(user)
                if not member.is_member:
                    raise NotEligible()
            
            filter = {'event_id':self.id,'tag':tag}
            update = {
                'event_id':self.id,
                'tag':tag,
                'discord_id':user,
                'timestamp':pendulum.now().int_timestamp
                }
            await bot_client.coc_db.db__event_participant.update_one(
                filter,
                {'$set':update},
                upsert=True
                )
            return await self.get_participant(tag)
    
    async def withdraw_participant(self,tag:str) -> None:
        async with self.lock:
            tag = coc.utils.correct_tag(tag)

            event = await Event.get_event(self.id)
            if event.status == 'closed':
                raise EventClosed()
            
            filter = {'event_id':self.id,'tag':tag}
            await bot_client.coc_db.db__event_participant.delete_one(filter)

    async def get_participant_count(self) -> int:
        query = await bot_client.coc_db.db__event_participant.find({'event_id':self.id}).to_list(None)
        return len(query)
    
    async def get_all_participants(self) -> List[Participant]:
        query = bot_client.coc_db.db__event_participant.find({'event_id':self.id})        
        get_players = bot_client.coc.get_players(
            [participant['tag'] async for participant in query],
            cls=Participant,
            event_id=self.id)
        return [p async for p in get_players]
    
    async def get_participants_for_user(self,user:int) -> List[Participant]:
        filter = {'event_id':self.id,'discord_id':user}
        query = bot_client.coc_db.db__event_participant.find(filter)
        get_players = bot_client.coc.get_players(
            [participant['tag'] async for participant in query],
            cls=Participant,
            event_id=self.id)
        return [p async for p in get_players]
    
    async def get_participant(self,tag:str) -> Optional[Participant]:
        tag = coc.utils.correct_tag(tag)
        filter = {'event_id':self.id,'tag':tag}
        query = await bot_client.coc_db.db__event_participant.find_one(filter)
        if query:
            return await bot_client.coc.get_player(tag,cls=Participant,event_id=self.id)
        return None