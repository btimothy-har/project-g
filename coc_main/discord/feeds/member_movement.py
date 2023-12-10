import coc
import discord
import pendulum

from typing import *
from redbot.core.utils import AsyncIter, bounded_gather

from .clan_feed import ClanDataFeed

from ...api_client import BotClashClient as client
from ...cog_coc_client import ClashOfClansClient

from ...coc_objects.players.player import aPlayer
from ...coc_objects.clans.clan import BasicClan, aClan

from ...utils.constants.coc_emojis import EmojisClash, EmojisLeagues
from ...utils.components import clash_embed, get_bot_webhook

bot_client = client()
type = 1

class ClanMemberFeed(ClanDataFeed):

    def __init__(self,database:dict):
        super().__init__(database)
    
    @staticmethod
    def get_coc_client() -> ClashOfClansClient:
        return bot_client.bot.get_cog('ClashOfClansClient')

    @classmethod
    async def create_feed(cls,
        clan: BasicClan,
        channel:Union[discord.TextChannel,discord.Thread]) -> ClanDataFeed:

        return await ClanDataFeed.create_feed(clan,channel,type)

    @classmethod
    async def member_join(cls,clan:aClan,player:coc.ClanMember):
        try:
            clan_feeds = await cls.feeds_for_clan(clan,type=type)

            if len(clan_feeds) > 0:
                client = cls.get_coc_client()
                p = await client.fetch_player(player.tag)

                embed = await cls.join_embed(clan,p)
                a_iter = AsyncIter(clan_feeds)
                tasks = [feed.send_to_discord(clan,embed) async for feed in a_iter]
                await bounded_gather(*tasks,return_exceptions=True,limit=1)

        except Exception:
            bot_client.coc_main_log.exception(f"Error building Member Join Feed.")
    
    @classmethod
    async def join_embed(cls,clan:aClan,player:aPlayer):
        embed = await clash_embed(
            context=bot_client.bot,
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
            icon_url="https://i.imgur.com/TZF5r54.png"
            )
        return embed
    
    @classmethod
    async def member_leave(cls,clan:aClan,player:coc.ClanMember):
        try:
            clan_feeds = await cls.feeds_for_clan(clan,type=type)

            if len(clan_feeds) > 0:
                client = cls.get_coc_client() 
                p = await client.fetch_player(player.tag)

                embed = await cls.leave_embed(clan,p)
                a_iter = AsyncIter(clan_feeds)
                tasks = [feed.send_to_discord(clan,embed) async for feed in a_iter]
                await bounded_gather(*tasks,return_exceptions=True,limit=1)

        except Exception:
            bot_client.coc_main_log.exception(f"Error building Member Leave Feed.")
    
    @classmethod
    async def leave_embed(cls,clan:aClan,player:aPlayer):
        embed = await clash_embed(
            context=bot_client.bot,
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
            icon_url="https://i.imgur.com/TZF5r54.png"
            )
        return embed
    
    async def send_to_discord(self,clan,embed):
        try:
            if not self.channel:
                return
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
            bot_client.coc_main_log.exception(f"Error sending Member Feed to Discord.")