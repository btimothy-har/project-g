import os
import discord
import pendulum
import urllib
import asyncio

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from redbot.core.utils import AsyncIter

from coc_client.api_client import BotClashClient

from ..objects.clans.clan import db_ClanDataFeed, aClan
from ..objects.events.raid_weekend import aRaidWeekend
from ..constants.coc_emojis import *

from ..utilities.utils import *
from ..utilities.components import *

bot_client = BotClashClient()

class RaidResultsFeed():
    def __init__(self,clan:aClan,feed:db_ClanDataFeed):
        self.clan = clan
        self.feed = feed
    
    @property
    def channel(self):
        return bot_client.bot.get_channel(self.feed.channel_id)
    
    @classmethod
    async def send_results(cls,clan:aClan,feed:db_ClanDataFeed,results_image):
        a = cls(clan,feed)

        if a.channel is None:
            return
        
        webhook = await get_bot_webhook(bot_client.bot,a.channel)
        if isinstance(a.channel,discord.Thread):
            await webhook.send(
                username=a.clan.name,
                avatar_url=a.clan.badge,
                file=results_image,
                thread=a.channel
                )
            
        else:
            await webhook.send(
                username=a.clan.name,
                avatar_url=a.clan.badge,
                file=results_image
                )