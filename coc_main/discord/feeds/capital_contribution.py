import discord
import asyncio

from redbot.core.utils import AsyncIter

from ...api_client import BotClashClient as client

from ...coc_objects.players.base_player import BasicPlayer
from ...coc_objects.clans.clan import db_ClanDataFeed

from ...utils.constants.coc_emojis import EmojisClash
from ...utils.components import clash_embed, get_bot_webhook

bot_client = client()

class CapitalContributionFeed():
    def __init__(self,player:BasicPlayer,amount:int):
        self.player = player
        self.amount = amount

    async def embed(self):
        embed = await clash_embed(
            context=bot_client.bot,
            message=f"**[{self.player.name}]({self.player.share_link})** donated {EmojisClash.CAPITALGOLD} {self.amount:,}.",
            )
        embed.set_footer(
            text=f"{self.player.clan.name} ({self.player.clan.tag})",
            icon_url=self.player.clan.badge
            )
        return embed
    
    @classmethod
    async def send_feed_update(cls,player:BasicPlayer,amount:int):
        if not player.clan:
            return
        
        if len(player.clan.capital_contribution_feed) == 0:
            return        
        feed = cls(player,amount)
        embed = await feed.embed()

        await asyncio.gather(*(feed.send_to_discord(embed,feed_data) for feed_data in player.clan.capital_contribution_feed))
    
    async def send_to_discord(self,embed,data_feed:db_ClanDataFeed):
        channel = bot_client.bot.get_channel(data_feed.channel_id)
        if not channel:
            return
        webhook = await get_bot_webhook(bot_client.bot,channel)
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