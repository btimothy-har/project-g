import discord
import pendulum
import asyncio

from redbot.core.utils import AsyncIter

from typing import *
from .clan_feed import ClanDataFeed
from ...api_client import BotClashClient as client
from ...coc_objects.clans.clan import BasicClan, aClan
from ...discord.mongo_discord import db_ClanDataFeed
from ...utils.constants.coc_emojis import EmojisClash
from ...utils.components import clash_embed, get_bot_webhook

bot_client = client()

type = 2

class MemberDonationDelta():
    def __init__(self,member,cached_member=None):
        self.member = member
        self.cached_member = cached_member
        self.donated_chg = 0
        self.received_chg = 0

        if self.cached_member:
            if self.member.donations > self.cached_member.donations:
                self.donated_chg = self.member.donations - self.cached_member.donations
            if self.member.received > self.cached_member.received:
                self.received_chg = self.member.received - self.cached_member.received

class ClanDonationFeed():

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
    
    def __init__(self,clan:aClan,cached_clan:aClan):
        self.clan = clan
        self.cached_clan = cached_clan
        self.raw_data = None
    
    @classmethod
    async def start_feed(cls,clan:aClan,cached_clan:aClan):
        try:
            clan_feeds = await cls.feeds_for_clan(clan)

            if len(clan_feeds) > 0:
                feed = cls(clan,cached_clan)
            
                calc_member_donation = []
                async for member in AsyncIter(feed.clan.members):
                    cached_member = feed.cached_clan.get_member(member.tag)
                    calc_member_donation.append(MemberDonationDelta(member,cached_member))
                
                feed.raw_data = calc_member_donation

                if len([m for m in feed.raw_data if (m.donated_chg + m.received_chg) > 0]) > 0:
                    embed = await feed.embed()
                    await asyncio.gather(*(feed.send_to_discord(embed,f) for f in clan_feeds))

        except Exception:
            bot_client.coc_main_log.exception(f"Error building Donation Feed.")
    
    async def embed(self):
        embed = await clash_embed(
            context=bot_client.bot,
            title=f"**{self.clan.name}** ({self.clan.tag})",
            show_author=False,
            embed_color=discord.Colour.default(),
            thumbnail=self.clan.badge,
            url=self.clan.share_link,
            timestamp=pendulum.now()
            )
        if len([m for m in self.raw_data if m.donated_chg]) > 0:
            embed.description += "\n**Donated**\n"
            embed.description += "\n".join([f"{EmojisClash.DONATIONSOUT} `{m.donated_chg:<3}` | **[{m.member.name}]({m.member.share_link})**" for m in self.raw_data if m.donated_chg > 0])

        if len([m for m in self.raw_data if m.received_chg]) > 0:
            embed.description += "\n**Received**\n"
            embed.description += "\n".join([f"{EmojisClash.DONATIONSRCVD} `{m.received_chg:<3}` | **[{m.member.name}]({m.member.share_link})**" for m in self.raw_data if m.received_chg > 0])
        return embed

    async def send_to_discord(self,embed,data_feed:db_ClanDataFeed):
        try:
            channel = bot_client.bot.get_channel(data_feed.channel_id)
            if channel:
                webhook = await get_bot_webhook(bot_client.bot,channel)
                if isinstance(channel,discord.Thread):
                    await webhook.send(
                        username=self.clan.name,
                        avatar_url=self.clan.badge,
                        embed=embed,
                        thread=channel
                        )
                else:
                    await webhook.send(
                        username=self.clan.name,
                        avatar_url=self.clan.badge,
                        embed=embed
                        )
        except Exception:
            bot_client.coc_main_log.exception(f"Error sending Donation Feed to Discord.")