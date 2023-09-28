import discord
import asyncio

from redbot.core.utils import AsyncIter

from coc_client.api_client import BotClashClient

from ..objects.players.player import aPlayer
from ..objects.clans.clan import db_ClanDataFeed, aClan
from ..constants.coc_emojis import *

from ..utilities.utils import *
from ..utilities.components import *

class CapitalContributionFeed():
    def __init__(self,player:aPlayer,amount:int):
        self.client = BotClashClient()
        self.bot = self.client.bot

        self.player = player
        self.amount = amount

    async def embed(self):
        embed = await clash_embed(
            context=self.bot,
            message=f"**[{self.player.name}]({self.player.share_link})** donated {EmojisClash.CAPITALGOLD} {self.amount:,}.",
            )
        embed.set_footer(
            text=f"{self.player.clan.name} ({self.player.clan.tag})",
            icon_url=self.player.clan.badge
            )
    
    @classmethod
    async def send_feed_update(cls,player:aPlayer,amount:int):
        if not player.clan:
            return
        
        if len(player.clan.capital_contribution_feed) == 0:
            return
        
        feed = cls(player,amount)
        embed = await feed.embed()

        [asyncio.create_task(feed.send_to_discord(embed,feed_data)) for feed_data in player.clan.capital_contribution_feed]
    
    async def send_to_discord(self,embed,data_feed:db_ClanDataFeed):
        channel = self.bot.get_channel(data_feed.channel_id)
        if not channel:
            return
        webhook = await get_bot_webhook(self.bot,channel)
        if isinstance(channel,discord.Thread):
            await webhook.send(
                username=self.player.clan.name,
                avatar_url=self.player.clan.badge,
                embed=embed,
                thread=channel
                )
        else:
            await webhook.send(
                username=self.player.clan.name,
                avatar_url=self.player.clan.badge,
                embed=embed
                )