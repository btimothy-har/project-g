import discord
import asyncio

from redbot.core.utils import AsyncIter

from typing import *

from .clan_feed import ClanDataFeed

from ...api_client import BotClashClient as client

from ...coc_objects.players.player import aPlayer
from ...coc_objects.clans.clan import BasicClan

from ...discord.mongo_discord import db_ClanDataFeed

from ...utils.constants.coc_emojis import EmojisClash
from ...utils.components import clash_embed, get_bot_webhook

bot_client = client()

type = 4

class CapitalContributionFeed():

    @staticmethod
    async def feeds_for_clan(clan:BasicClan) -> List[db_ClanDataFeed]:
        def _get_from_db():
            return db_ClanDataFeed.objects(tag=clan.tag,type=type)
        
        feeds = await bot_client.run_in_thread(_get_from_db)
        return feeds
    
    @staticmethod
    async def create_feed(clan:BasicClan,channel:Union[discord.TextChannel,discord.Thread]) -> db_ClanDataFeed:
        def _create_in_db():
            feed = db_ClanDataFeed(
                tag=clan.tag,
                type=type,
                guild_id=channel.guild.id,
                channel_id=channel.id
                )
            feed.save()
            return feed
        
        feed = await bot_client.run_in_thread(_create_in_db)
        return feed
    
    @staticmethod
    async def delete_feed(feed_id:str):
        await ClanDataFeed.delete_feed(feed_id)
            
    def __init__(self,player:aPlayer,amount:int):
        self.player = player
        self.amount = amount

    @classmethod
    async def send_feed_update(cls,player:aPlayer,amount:int):
        try:
            if not player.clan:
                return
            
            clan_feeds = await cls.feeds_for_clan(player.clan)

            if len(clan_feeds) > 0:
                feed = cls(player,amount)
                embed = await feed.embed()
                
                await asyncio.gather(*(feed.send_to_discord(embed,f) for f in clan_feeds))

        except Exception:
            bot_client.coc_main_log.exception(f"Error building Capital Contribution Feed.")

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
    
    async def send_to_discord(self,embed,data_feed:db_ClanDataFeed):
        try:
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
        except Exception:
            bot_client.coc_main_log.exception(f"Error sending Capital Contribution Feed to Discord.")