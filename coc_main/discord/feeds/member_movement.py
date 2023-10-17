import discord
import pendulum
import asyncio

from redbot.core.utils import AsyncIter

from ...api_client import BotClashClient as client
from ...cog_coc_client import ClashOfClansClient

from ...coc_objects.clans.clan import aClan, db_ClanDataFeed

from ...utils.constants.coc_emojis import EmojisClash, EmojisLeagues
from ...utils.components import clash_embed, get_bot_webhook

bot_client = client()

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

class ClanMemberFeed():
    def __init__(self,clan:aClan,player_tag:str):
        self.clan = clan
        self.player_tag = player_tag
        self.player = None
    
    @property
    def coc_client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    async def fetch_player(self):
        self.player = await self.coc_client.fetch_player(self.player_tag,no_cache=True)

    @classmethod
    async def member_join(cls,clan:aClan,player_tag:str):
        try:
            if len(clan.member_feed) == 0:
                return
            
            feed = cls(clan,player_tag)
            await feed.fetch_player()
            embed = await feed.join_embed()

            await asyncio.gather(*(feed.send_to_discord(embed, feed_data) for feed_data in clan.member_feed))
        except Exception:
            bot_client.coc_main_log.exception(f"Error building Member Join Feed.")
    
    async def join_embed(self):
        embed = await clash_embed(
            context=bot_client.bot,
            title=f"**{self.player.name}** ({self.player.tag})",
            message=(f"{self.player.discord_user_str}\n" if self.player.discord_user else "")
                + (f"{self.player.member_description}\n" if self.player.is_member else "")
                + f"{EmojisClash.EXP} {self.player.exp_level}\u3000{self.player.town_hall.emote} {self.player.town_hall.description}\u3000{EmojisLeagues.get(self.player.league.name)} {self.player.trophies}\n"
                + (f"{self.player.hero_description}" if self.player.town_hall.level >= 7 else ""),
            show_author=False,
            success=True,
            thumbnail=self.clan.badge,
            url=self.player.share_link,
            timestamp=pendulum.now())
        embed.set_footer(
            text=f"Joined {self.clan.name} [{self.clan.member_count}/50]",
            icon_url="https://i.imgur.com/TZF5r54.png"
            )
        return embed
    
    @classmethod
    async def member_leave(cls,clan:aClan,player_tag:str):
        try:
            if len(clan.member_feed) == 0:
                return
        
            feed = cls(clan,player_tag)
            await feed.fetch_player()
            embed = await feed.leave_embed()

            await asyncio.gather(*(feed.send_to_discord(embed, feed_data) for feed_data in clan.member_feed))
        except Exception:
            bot_client.coc_main_log.exception(f"Error building Member Leave Feed.")
    
    async def leave_embed(self):
        embed = await clash_embed(
            context=bot_client.bot,
            title=f"**{self.player.name}** ({self.player.tag})",
            message=(f"{self.player.discord_user_str}\n" if self.player.discord_user else "")
                + (f"{self.player.member_description}\n" if self.player.is_member else "")
                + f"{EmojisClash.EXP} {self.player.exp_level}\u3000{self.player.town_hall.emote} {self.player.town_hall.description}\u3000{EmojisLeagues.get(self.player.league.name)} {self.player.trophies}\n"
                + (f"{self.player.hero_description}" if self.player.town_hall.level >= 7 else ""),
            show_author=False,
            success=False,
            url=self.player.share_link,
            timestamp=pendulum.now())
        embed.set_footer(
            text=f"Left {self.clan.name} [{self.clan.member_count}/50] " + (f"and joined {self.player.clan.name}" if self.player.clan.tag and self.player.clan.tag != self.clan.tag else ""),
            icon_url="https://i.imgur.com/TZF5r54.png"
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
            bot_client.coc_main_log.exception(f"Error sending Member Feed to Discord.")