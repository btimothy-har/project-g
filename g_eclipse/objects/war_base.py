import discord
import pendulum
import urllib

from redbot.core.utils import AsyncIter

from coc_client.api_client import BotClashClient
from coc_data.constants.coc_emojis import *

from typing import *
from mongoengine import *

from ..components import *

bot_client = BotClashClient()

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

class eWarBase():
    _cache = {}

    @classmethod
    async def by_user_claim(cls,user_id:int):
        bases = []
        async for base in AsyncIter(dbWarBase.objects(claims__in=[user_id])):
            bases.append(await cls.from_base_id(base.base_id))        
        return sorted(bases,key=lambda x: (x.town_hall,x.added_on),reverse=True)

    @classmethod
    async def by_townhall_level(cls,townhall:int):
        bases = []
        async for base in AsyncIter(dbWarBase.objects(townhall=townhall)):
            bases.append(await cls.from_base_id(base.base_id))
        return sorted(bases,key=lambda x: x.added_on,reverse=True)

    def __new__(cls,base_link,defensive_cc_link):
        link_parse = urllib.parse.urlparse(base_link)
        base_id = urllib.parse.quote_plus(urllib.parse.parse_qs(link_parse.query)['id'][0])

        if base_id not in cls._cache:
            instance = super().__new__(cls)
            cls._cache[base_id] = instance
            instance._is_new = True
        return cls._cache[base_id]

    def __init__(self,base_link,defensive_cc_link):
        if self._is_new:
            link_parse = urllib.parse.urlparse(base_link)
            cc_parse = urllib.parse.urlparse(defensive_cc_link)
            self.id = urllib.parse.quote_plus(urllib.parse.parse_qs(link_parse.query)['id'][0])

            try:
                self.town_hall = int(self.id.split('TH',1)[1][:2])
            except:
                self.town_hall = int(self.id.split('TH',1)[1][:1])

            self.base_link = f"https://link.clashofclans.com/en?action=OpenLayout&id={urllib.parse.quote_plus(self.id)}"

            self.defensive_cc_id = urllib.parse.quote(urllib.parse.parse_qs(cc_parse.query)['army'][0])
            self.defensive_cc_link = f"https://link.clashofclans.com/en?action=CopyArmy&army={urllib.parse.quote_plus(self.defensive_cc_id)}"

            parsed_cc = bot_client.coc.parse_army_link(self.defensive_cc_link)
            self.defensive_cc_str = ""
            for troop in parsed_cc[0]:
                if self.defensive_cc_str != "":
                    self.defensive_cc_str += "\u3000"
                self.defensive_cc_str += f"{EmojisTroops.get(troop[0].name)} x{troop[1]}"

            self.source = ""
            self.builder = None
            self.added_on = 0
            self.base_type = ""
            self.base_image = ""
            self.notes = ""
            self.claims = []

    @classmethod
    async def from_base_id(cls,b_id):

        try:
            base_data = dbWarBase.objects.get(base_id=b_id).to_mongo().to_dict()
        except DoesNotExist:
            return None

        base_link = f"https://link.clashofclans.com/en?action=OpenLayout&id={b_id}"
        defensive_cc_link = f"https://link.clashofclans.com/en?action=CopyArmy&army={base_data['defensive_cc']}"

        base = eWarBase(base_link,defensive_cc_link)

        base.base_link = base_link
        base.defensive_cc_link = defensive_cc_link

        base.source = base_data['source']
        base.builder = base_data['builder']

        base.added_on = base_data['added_on']
        base.base_type = base_data['base_type']

        base.base_image = base_data['base_image']
        base.notes = base_data['builder_notes']
        base.claims = base_data['claims']
        return base

    @classmethod
    async def new_base(cls,base_link,source,base_builder,base_type,defensive_cc,notes,image_attachment):
        
        base = eWarBase(base_link,defensive_cc)
        base.base_link = f"https://link.clashofclans.com/en?action=OpenLayout&id={base.id}"

        base.source = source
        if base_builder == "*":
            base.builder = "Not Specified"
        else:
            base.builder = base_builder

        if notes == "*":
            base.notes = None
        else:
            base.notes = notes

        base.added_on = pendulum.now().int_timestamp
        base.base_type = base_type

        image_filename = base.id + '.' + image_attachment.filename.split('.')[-1]
        image_filepath = bot_client.bot.get_cog("ECLIPSE").base_image_path + "/" + image_filename

        await image_attachment.save(image_filepath)
        base.base_image = image_filename

        base.save_base()
        return base

    def save_base(self):
        db_base = dbWarBase(
            base_id = self.id,
            townhall = self.town_hall,
            source = self.source,
            builder = self.builder,
            added_on = self.added_on,
            base_type = self.base_type,
            defensive_cc = self.defensive_cc_id,
            base_image = self.base_image,
            builder_notes = self.notes,
            claims = self.claims
            )
        db_base.save()

    def add_claim(self,user_id:int):
        if user_id not in self.claims:
            self.claims.append(user_id)
            self.save_base()

    def remove_claim(self,user_id:int):
        try:
            self.claims.remove(user_id)
        except ValueError:
            pass
        else:
            self.save_base()

    async def base_embed(self):
        image_file_path = bot_client.get_cog('ECLIPSE').base_image_path + '/' + self.base_image
        image_file = discord.File(image_file_path,'image.png')

        base_text = (f"Date Added: {pendulum.from_timestamp(self.added_on).format('DD MMM YYYY')}"
                + f"\n\nFrom: **{self.source}**\nBuilder: **{self.builder}**"
                + f"\n\n**Recommended Clan Castle:**\n{self.defensive_cc_str}"
                )
        if self.notes:
            base_text += f"\n\n**Builder Notes**:\n{self.notes}"
        base_text += "\n\u200b"
        embed = await eclipse_embed(
            context=self.bot,
            title=f"**TH{self.town_hall} {EmojisTownHall.get(int(self.town_hall))} {self.base_type}**",
            message=base_text)
        embed.set_image(url="attachment://image.png")
        return embed,image_file