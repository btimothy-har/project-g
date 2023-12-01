from typing import Union
import discord
import pendulum
import asyncio

from redbot.core.utils import AsyncIter, bounded_gather

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

class ClanDonationFeed(ClanDataFeed):

    def __init__(self,database:dict):
        super().__init__(database)
    
    @classmethod
    async def create_feed(cls,
        clan: BasicClan,
        channel:Union[discord.TextChannel,discord.Thread]) -> ClanDataFeed:

        return await ClanDataFeed.create_feed(clan,channel,type)

    @classmethod
    async def start_feed(cls,clan:aClan,cached_clan:aClan):
        try:
            clan_feeds = await cls.feeds_for_clan(clan,type)

            if len(clan_feeds) > 0:            
                calc_member_donation = []

                async for member in AsyncIter(clan.members):
                    cached_member = cached_clan.get_member(member.tag)
                    calc_member_donation.append(MemberDonationDelta(member,cached_member))

                if len([m for m in calc_member_donation if (m.donated_chg + m.received_chg) > 0]) > 0:
                    embed = await cls.donation_embed(clan,calc_member_donation)
                    a_iter = AsyncIter(clan_feeds)
                    tasks = [feed.send_to_discord(clan,embed) async for feed in a_iter]
                    await bounded_gather(*tasks,return_exceptions=True,limit=1)

        except Exception:
            bot_client.coc_main_log.exception(f"Error building Donation Feed.")
    
    @classmethod
    async def donation_embed(cls,clan,donation_delta):
        embed = await clash_embed(
            context=bot_client.bot,
            title=f"**{clan.name}** ({clan.tag})",
            show_author=False,
            embed_color=discord.Colour.default(),
            thumbnail=clan.badge,
            url=clan.share_link,
            timestamp=pendulum.now()
            )
        if len([m for m in donation_delta if m.donated_chg]) > 0:
            embed.description += "\n**Donated**\n"
            embed.description += "\n".join([f"{EmojisClash.DONATIONSOUT} `{m.donated_chg:<3}` | **[{m.member.name}]({m.member.share_link})**" for m in donation_delta if m.donated_chg > 0])

        if len([m for m in donation_delta if m.received_chg]) > 0:
            embed.description += "\n**Received**\n"
            embed.description += "\n".join([f"{EmojisClash.DONATIONSRCVD} `{m.received_chg:<3}` | **[{m.member.name}]({m.member.share_link})**" for m in donation_delta if m.received_chg > 0])
        return embed
    
    async def send_to_discord(self,clan,embed):
        try:
            if self.channel:
                webhook = await get_bot_webhook(bot_client.bot,self.channel)
                if isinstance(self.channel,discord.Thread):
                    await webhook.send(
                        username=clan.name,
                        avatar_url=clan.badge,
                        embed=embed,
                        thread=self.channel
                        )
                else:
                    await webhook.send(
                        username=clan.name,
                        avatar_url=clan.badge,
                        embed=embed
                        )
        except Exception:
            bot_client.coc_main_log.exception(f"Error sending Donation Feed to Discord.")