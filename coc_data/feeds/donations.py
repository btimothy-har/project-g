import discord
import pendulum
import asyncio

from redbot.core.utils import AsyncIter

from coc_client.api_client import BotClashClient

from ..objects.clans.clan import db_ClanDataFeed, aClan

from ..utilities.utils import *
from ..utilities.components import *
from ..constants.coc_emojis import *

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
    def __init__(self,clan:aClan,cached_clan:aClan):
        self.client = BotClashClient()
        self.bot = self.client.bot
        self.clan = clan
        self.cached_clan = cached_clan
        self.raw_data = None
    
    async def embed(self):
        embed = await clash_embed(
            context=self.bot,
            title=f"**{self.clan.name}** ({self.clan.tag})",
            show_author=False,
            embed_color=discord.Colour.default(),
            thumbnail=self.clan.badge,
            url=self.clan.share_link,
            timestamp=pendulum.now()
            )
        embed.add_field(
            name="Donated",
            value="\n".join([f"{EmojisClash.DONATIONSOUT} `{m.donated_chg:<3}` | **[{m.member.name}]({m.member.share_link})**" for m in self.raw_data if m.donated_chg > 0]),
            inline=False
            )
        embed.add_field(
            name="Received",
            value="\n".join([f"{EmojisClash.DONATIONSRCVD} `{m.received_chg:<3}` | **[{m.member.name}]({m.member.share_link})**" for m in self.raw_data if m.received_chg > 0]),
            inline=False
            )

    @classmethod
    async def start_feed(cls,clan:aClan,cached_clan:aClan):
        feed = cls(clan,cached_clan)

        if len(feed.clan.donation_feed) == 0:
            return
        
        calc_member_donation = []
        async for member in AsyncIter(feed.clan.members):
            cached_member = feed.cached_clan.get_member(member.tag)
            calc_member_donation.append(MemberDonationDelta(member,cached_member))
        
        feed.raw_data = calc_member_donation

        if len([m for m in feed.raw_data if (m.donated_chg + m.received_chg) > 0]) > 0:
            embed = await feed.embed()
            send_tasks = [asyncio.create_task(feed.send_to_discord(embed,feed_data)) for feed_data in feed.clan.donation_feed]
            await asyncio.gather(*send_tasks)
    
    async def send_to_discord(self,embed,data_feed:db_ClanDataFeed):
        channel = self.bot.get_channel(data_feed.channel_id)
        if channel:
            webhook = await get_bot_webhook(self.bot,channel)
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