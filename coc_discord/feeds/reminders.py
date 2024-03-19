import discord
import pendulum
import asyncio
import bson
import logging

from typing import *

from collections import defaultdict
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter

from coc_main.client.global_client import GlobalClient

from coc_main.coc_objects.players.player import aPlayer
from coc_main.coc_objects.clans.clan import aClan
from coc_main.coc_objects.events.clan_war_v2 import bClanWar
from coc_main.coc_objects.events.raid_weekend import aRaidWeekend

from coc_main.utils.components import get_bot_webhook, s_convert_seconds_to_str

LOG = logging.getLogger("coc.main")

reminder_type = {
    1: 'Clan War',
    2: 'Raid Weekend',
    }

class MemberReminder():
    def __init__(self,member:discord.Member):
        self.member = member
        self.accounts = []
    
    def add_account(self,account:aPlayer):
        self.accounts.append(account)

class EventReminder(GlobalClient):
    _locks = defaultdict(asyncio.Lock)
    __slots__ = [
        '_id',
        'id',
        'tag',
        '_type',
        'sub_type',
        'guild_id',
        'channel_id',
        'reminder_interval',
        'interval_tracker',
        'active_reminders'
        ]
    
    @staticmethod
    def remaining_time_str(reference_time:pendulum.DateTime) -> str:
        time_remaining = reference_time.int_timestamp - pendulum.now().int_timestamp
        rd, rh, rm, rs = s_convert_seconds_to_str(time_remaining)
        remain_str = ""
        if rd > 0:
            remain_str += f"{int(rd)}D "
        if rh > 0:
            remain_str += f"{int(rh)}H "
        remain_str += f"{int(rm)}M "
        return remain_str
    
    def __init__(self,database:dict):
        self._id = database['_id']
        self.id = str(self._id)

        self.tag = database.get('tag',None)
        self._type = database.get('type',None)
        self.sub_type = database.get('sub_type',[])
        self.guild_id = database.get('guild_id',None)
        self.channel_id = database.get('channel_id',None)
        self.reminder_interval = database.get('reminder_interval',[])
        self.interval_tracker = database.get('interval_tracker',[])

        self.active_reminders = {} 
    
    @property
    def _lock(self) -> asyncio.Lock:
        return self._locks[self._id]

    @property
    def bot(self) -> Red:
        return GlobalClient.bot    
    @property
    def guild(self) -> Optional[discord.Guild]:
        return self.bot.get_guild(self.guild_id)    
    @property
    def channel(self) -> Optional[Union[discord.TextChannel,discord.Thread]]:
        if not self.guild:
            return None
        return self.bot.get_channel(self.channel_id)
    
    @property
    def type(self) -> str:
        return reminder_type.get(self._type,'Unknown')
    
    @property
    def next_reminder(self) -> Optional[int]:
        return max(self.interval_tracker) if self.interval_tracker and len(self.interval_tracker) > 0 else None
    
    async def delete(self):
        await self.database.db__clan_event_reminder.delete_one({'_id':self._id})

    async def generate_reminder_text(self):
        reminder_text = ""
        members = AsyncIter(list(self.active_reminders.values()))
        async for m in members:
            account_str = [f"\n{a.title}" for a in m.accounts]
            reminder_text += f"{m.member.mention}" +', '.join(account_str) + '\n\n'
        return reminder_text
    
    async def refresh_intervals(self,time_reference):
        self.interval_tracker = [i for i in self.reminder_interval if i < (time_reference.total_seconds() / 3600)]
        await self.database.db__clan_event_reminder.update_one(
            {'_id':self._id},
            {'$set': {
                'interval_tracker':self.interval_tracker
                }
            }
        )
    
    async def send_reminder(self,event:Union[bClanWar,aRaidWeekend],*players):        
        time_remaining = event.end_time - pendulum.now()
        if self._lock.locked():
            return
        async with self._lock:
            if not self.channel:
                await self.delete()
                return
            
            if self.next_reminder and (time_remaining.total_seconds() / 3600) < self.next_reminder: 
                get_players = self.coc_client.get_players([p.tag for p in players])
                async for player in get_players:
                    try:
                        member = await self.bot.get_or_fetch_member(self.guild,player.discord_user)
                    except (discord.Forbidden,discord.NotFound):
                        member = None
                    if not member:
                        continue                    
                    try:
                        r = self.active_reminders[member.id]
                    except KeyError:
                        r = self.active_reminders[member.id] = MemberReminder(member)
                    r.add_account(player)
            
            if len(self.active_reminders) > 0:
                if self._type == 1:
                    await self.send_war_reminders(event)
                elif self._type == 2:
                    await self.send_raid_reminders(event)
            
            await self.refresh_intervals(time_remaining)
    
    async def send_war_reminders(self,clan_war:bClanWar):
        clan = await self.coc_client.get_clan(self.tag)
                
        reminder_text = f"You have **NOT** used all of your War Attacks. " 
        reminder_text += f"Clan War ends in **{EventReminder.remaining_time_str(clan_war.end_time)}** "
        reminder_text += f"(<t:{clan_war.end_time.int_timestamp}:f>)\n\n"
        reminder_text += await self.generate_reminder_text()

        webhook = await get_bot_webhook(self.bot,self.channel)
        if isinstance(self.channel,discord.Thread):
            r_msg = await webhook.send(
                username=clan.name,
                avatar_url=clan.badge,
                content=reminder_text,
                thread=self.channel,
                wait=True
                )
        else:
            r_msg = await webhook.send(
                username=clan.name,
                avatar_url=clan.badge,
                content=reminder_text,
                wait=True
                )
        LOG.info(f"Clan {clan}: Sent War Reminders to {len(self.active_reminders)} players. Reminder ID: {r_msg.id}")
        self.active_reminders = {}
    
    async def send_raid_reminders(self,raid_weekend:aRaidWeekend):
        clan = await self.coc_client.get_clan(self.tag)

        reminder_text = f"You started your Raid Weekend but **HAVE NOT** used all your Raid Attacks. "
        reminder_text += f"Raid Weekend ends in **{EventReminder.remaining_time_str(raid_weekend.end_time)}** "
        reminder_text += f"(<t:{raid_weekend.end_time.int_timestamp}:f>).\n\n"
        reminder_text += await self.generate_reminder_text()

        webhook = await get_bot_webhook(self.bot,self.channel)

        if isinstance(self.channel,discord.Thread):
            r_msg = await webhook.send(
                username=clan.name,
                avatar_url=clan.badge,
                content=reminder_text,
                thread=self.channel,
                wait = True
                )
        else:
            r_msg = await webhook.send(
                username=clan.name,
                avatar_url=clan.badge,
                content=reminder_text,
                wait = True
                )
        LOG.info(f"Clan {clan}: Sent Raid Reminders to {len(self.active_reminders)} players. Reminder ID: {r_msg.id}")
    
    @classmethod
    async def get_by_id(cls,id:str) -> 'EventReminder':
        query = await cls.database.db__clan_event_reminder.find_one({'_id':bson.ObjectId(id)})
        return cls(query) if query else None
    
    @classmethod
    async def get_all(cls) -> List['EventReminder']:
        query = cls.database.db__clan_event_reminder.find({})
        reminders = [cls(r) async for r in query]
        return reminders
    
    @classmethod
    async def get_war_reminders(cls) -> List['EventReminder']:
        query = cls.database.db__clan_event_reminder.find({'type':1})
        reminders = [cls(r) async for r in query]        
        return reminders
    
    @classmethod
    async def create_war_reminder(cls,
        clan:aClan,
        channel:Union[discord.TextChannel,discord.Thread],
        war_types:list[str],
        interval:list[int]) -> 'EventReminder':

        valid_types = ['random','cwl','friendly']
        wt = [w for w in war_types if w in valid_types]
        intv = sorted([int(i) for i in interval],reverse=True)

        new = await cls.database.db__clan_event_reminder.insert_one(
            {
                'tag':clan.tag,
                'type':1,
                'sub_type':wt,
                'guild_id':channel.guild.id,
                'channel_id':channel.id,
                'reminder_interval':intv
                }
            )
        reminder = await cls.get_by_id(new.inserted_id)        
        return reminder

    @classmethod
    async def create_raid_reminder(cls,
        clan:aClan,
        channel:Union[discord.TextChannel,discord.Thread],
        interval:list[int]) -> 'EventReminder':

        intv = sorted([int(i) for i in interval],reverse=True)
        new = await cls.database.db__clan_event_reminder.insert_one(
            {
                'tag':clan.tag,
                'type':2,
                'guild_id':channel.guild.id,
                'channel_id':channel.id,
                'reminder_interval':intv
                }
            )
        reminder = await cls.get_by_id(new.inserted_id)
        return reminder
    
    @classmethod
    async def war_reminders_for_clan(cls,clan:aClan) -> List['EventReminder']:
        query = cls.database.db__clan_event_reminder.find({'tag':clan.tag,'type':1})
        reminders = [cls(r) async for r in query]        
        return reminders
    
    @classmethod
    async def raid_reminders_for_clan(cls,clan:aClan) -> List['EventReminder']:
        query = cls.database.db__clan_event_reminder.find({'tag':clan.tag,'type':2})
        reminders = [cls(r) async for r in query]
        return reminders