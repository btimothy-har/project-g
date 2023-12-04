import discord
import pendulum
import urllib
import asyncio

from typing import *
from mongoengine import *

from functools import cached_property
from collections import defaultdict

from redbot.core.utils import AsyncIter
from async_property import AwaitLoader

from coc_main.api_client import BotClashClient
from coc_main.utils.constants.coc_emojis import EmojisTroops, EmojisTownHall

from ..components import eclipse_embed

bot_client = BotClashClient()

max_th = 15

class dbWarBase(Document):
    base_id = StringField(primary_key=True,required=True)
    townhall = IntField(default=0)
    source = StringField(default="")
    builder = StringField(default="")
    added_on = IntField(default=0)
    base_type = StringField(default="")
    defensive_cc = StringField(default="")
    base_image = StringField(default="")
    builder_notes = StringField(default="")
    claims = ListField(IntField(),default=[])

class eWarBase(AwaitLoader):
    _locks = defaultdict(asyncio.Lock)    
    __slots__ = [
        'id',
        'base_link',
        'town_hall',        
        'defensive_cc',
        'source',
        'builder',
        'added_on',
        'base_type',
        'base_image',
        'notes',
        'claims'
        ]

    @classmethod
    async def by_user_claim(cls,user_id:int):
        query = bot_client.coc_db.db_war_base.find({'claims':user_id})
        bases = [await cls(q['_id']) async for q in query]
        return sorted(bases,key=lambda x:(x.added_on),reverse=True)

    @classmethod
    async def by_townhall_level(cls,townhall:int):
        if townhall == max_th:
            cutoff = pendulum.now().subtract(months=3).int_timestamp
        elif townhall == max_th - 1 or townhall == max_th - 2:
            cutoff = pendulum.now().subtract(months=6).int_timestamp
        else:
            cutoff = pendulum.now().subtract(months=12).int_timestamp

        query = bot_client.coc_db.db_war_base.find({
            'townhall':townhall,
            'added_on':{'$gte':cutoff}
            })
        bases = [await cls(q['_id']) async for q in query]
        return sorted(bases,key=lambda x:(x.added_on),reverse=True)
    
    def __init__(self,base_id:str):            
        self.id = base_id
        self.base_link = f"https://link.clashofclans.com/en?action=OpenLayout&id={self.id}"

        self.town_hall = 0
        self.defensive_cc = ""
        self.source = ""
        self.builder = None
        self.added_on = 0
        self.base_type = ""
        self.base_image = ""
        self.notes = ""
        self.claims = []
    
    async def load(self):
        query = await bot_client.coc_db.db_war_base.find_one({'_id':self.id})
        if query:
            self.town_hall = query['townhall']
            self.defensive_cc = query['defensive_cc']
            self.source = query['source']
            self.builder = query['builder']
            self.added_on = query['added_on']
            self.base_type = query['base_type']
            self.base_image = query['base_image']
            self.notes = query['builder_notes']
            self.claims = query.get('claims',[])
    
    @classmethod
    async def new_base(cls,base_link,source,base_builder,base_type,defensive_cc,notes,image_attachment):
        link_parse = urllib.parse.urlparse(base_link)
        cc_parse = urllib.parse.urlparse(defensive_cc)

        base_id = urllib.parse.quote_plus(urllib.parse.parse_qs(link_parse.query)['id'][0])
        try:
            base_town_hall = int(base_id.split('TH',1)[1][:2])
        except:
            base_town_hall = int(base_id.split('TH',1)[1][:1])
        
        defensive_troops = urllib.parse.quote_plus(urllib.parse.parse_qs(cc_parse.query)['army'][0])

        image_filename = base_id + '.' + image_attachment.filename.split('.')[-1]
        image_filepath = bot_client.bot.base_image_path + "/" + image_filename
        await image_attachment.save(image_filepath)

        await bot_client.coc_db.db_war_base.update_one(
            {'_id':base_id},
            {
                '$set': {
                    'townhall': base_town_hall,
                    'source': source,
                    'builder': base_builder if base_builder != "*" else "Not Specified",
                    'added_on': pendulum.now().int_timestamp,
                    'base_type': base_type,
                    'defensive_cc': defensive_troops,
                    'base_image': image_filename,
                    'builder_notes': notes if notes != "*" else None
                    }
                },
            upsert=True
            )        
        base = await cls(base_id)
        return base
    
    @cached_property
    def defensive_cc_link(self):
        return f"https://link.clashofclans.com/en?action=CopyArmy&army={self.defensive_cc}"    
    @cached_property
    def defensive_cc_str(self):
        parsed_cc = bot_client.coc.parse_army_link(self.defensive_cc_link)
        defensive_cc_str = ""
        for troop in parsed_cc[0]:
            if defensive_cc_str != "":
                defensive_cc_str += "\u3000"
            defensive_cc_str += f"{EmojisTroops.get(troop[0].name)} x{troop[1]}"
        return defensive_cc_str

    @property
    def lock(self):
        return self._locks[self.id]

    async def add_claim(self,user_id:int):
        async with self.lock:
            await bot_client.coc_db.db_war_base.update_one(
                {'_id':self.id},
                {'$addToSet': {
                    'claims': user_id
                    }
                }
            )
            await self.load()

    async def remove_claim(self,user_id:int):
        async with self.lock:
            await bot_client.coc_db.db_war_base.update_one(
                {'_id':self.id},
                {'$pull': {
                    'claims': user_id
                    }
                }
            )
            await self.load()

    async def base_embed(self):
        image_file_path = bot_client.bot.base_image_path + '/' + self.base_image
        image_file = discord.File(image_file_path,'image.png')

        base_text = (f"Date Added: {pendulum.from_timestamp(self.added_on).format('DD MMM YYYY')}"
                + f"\n\nFrom: **{self.source}**\nBuilder: **{self.builder}**"
                + f"\n\n**Recommended Clan Castle:**\n{self.defensive_cc_str}"
                )
        if self.notes:
            base_text += f"\n\n**Builder Notes**:\n{self.notes}"
        base_text += "\n\u200b"
        embed = await eclipse_embed(
            context=bot_client.bot,
            title=f"**TH{self.town_hall} {EmojisTownHall.get(int(self.town_hall))} {self.base_type}**",
            message=base_text)
        embed.set_image(url="attachment://image.png")
        return embed,image_file