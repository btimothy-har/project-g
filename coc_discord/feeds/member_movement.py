import coc
import discord
import pendulum
import logging

from typing import *
from redbot.core.utils import AsyncIter, bounded_gather

from coc_main.coc_objects.players.player import aPlayer
from coc_main.coc_objects.clans.clan import aClan

from coc_main.utils.constants.coc_emojis import EmojisClash, EmojisLeagues
from coc_main.utils.components import clash_embed, get_bot_webhook

from .clan_feed import ClanDataFeed

LOG = logging.getLogger("coc.discord")
type = 1

class ClanMemberFeed(ClanDataFeed):

    @classmethod
    async def create_feed(cls,
        clan:aClan,
        channel:Union[discord.TextChannel,discord.Thread]) -> ClanDataFeed:

        return await ClanDataFeed.create_feed(clan,channel,type)

    @classmethod
    async def member_join(cls,clan:aClan,player:coc.ClanMember):
        try:
            clan_feeds = await cls.feeds_for_clan(clan,type=type)

            if len(clan_feeds) > 0:
                p = await cls.coc_client.get_player(player.tag)

                embed = await cls.join_embed(clan,p)
                a_iter = AsyncIter(clan_feeds)
                tasks = [feed.send_to_discord(clan,embed) async for feed in a_iter]
                await bounded_gather(*tasks,return_exceptions=True,limit=1)

        except Exception:
            LOG.exception(f"Error building Member Join Feed.")
    
    @classmethod
    async def join_embed(cls,clan:aClan,player:aPlayer):
        embed = await clash_embed(
            context=cls.bot,
            title=f"**{player.name}** ({player.tag})",
            message=(f"{player.discord_user_str}\n" if player.discord_user else "")
                + (f"{player.member_description}\n" if player.is_member else "")
                + f"{EmojisClash.EXP} {player.exp_level}\u3000{player.town_hall.emote} {player.town_hall.description}\u3000{EmojisLeagues.get(player.league.name)} {player.trophies}\n"
                + (f"{player.hero_description}" if player.town_hall.level >= 7 else ""),
            show_author=False,
            success=True,
            thumbnail=clan.badge,
            url=player.share_link,
            timestamp=pendulum.now())
        embed.set_footer(
            text=f"Joined {clan.name} [{clan.member_count}/50]",
            icon_url=cls.bot.user.display_avatar.url
            )
        return embed
    
    @classmethod
    async def member_leave(cls,clan:aClan,player:coc.ClanMember):
        try:
            clan_feeds = await cls.feeds_for_clan(clan,type=type)

            if len(clan_feeds) > 0:
                p = await cls.coc_client.get_player(player.tag)

                embed = await cls.leave_embed(clan,p)
                a_iter = AsyncIter(clan_feeds)
                tasks = [feed.send_to_discord(clan,embed) async for feed in a_iter]
                await bounded_gather(*tasks,return_exceptions=True,limit=1)

        except Exception:
            LOG.exception(f"Error building Member Leave Feed.")
    
    @classmethod
    async def leave_embed(cls,clan:aClan,player:aPlayer):
        embed = await clash_embed(
            context=cls.bot,
            title=f"**{player.name}** ({player.tag})",
            message=(f"{player.discord_user_str}\n" if player.discord_user else "")
                + (f"{player.member_description}\n" if player.is_member else "")
                + f"{EmojisClash.EXP} {player.exp_level}\u3000{player.town_hall.emote} {player.town_hall.description}\u3000{EmojisLeagues.get(player.league.name)} {player.trophies}\n"
                + (f"{player.hero_description}" if player.town_hall.level >= 7 else ""),
            show_author=False,
            success=False,
            url=player.share_link,
            timestamp=pendulum.now())
        embed.set_footer(
            text=f"Left {clan.name} [{clan.member_count}/50] " + (f"and joined {player.clan.name}" if player.clan and getattr(player.clan,'tag',None) != clan.tag else ""),
            icon_url=cls.bot.user.display_avatar.url
            )
        return embed

    def __init__(self,database:dict):
        super().__init__(database)

    async def send_to_discord(self,clan,embed):
        try:
            if not self.channel:
                return
            webhook = await get_bot_webhook(self.bot,self.channel)
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
            LOG.exception(f"Error sending Member Feed to Discord.")