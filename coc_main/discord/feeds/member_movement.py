import coc
import discord
import pendulum
import asyncio

from typing import *

from .clan_feed import ClanDataFeed
from ...api_client import BotClashClient as client
from ...cog_coc_client import ClashOfClansClient
from ...coc_objects.players.player import aPlayer
from ...coc_objects.clans.clan import BasicClan, aClan
from ...discord.mongo_discord import db_ClanDataFeed
from ...utils.constants.coc_emojis import EmojisClash, EmojisLeagues
from ...utils.components import clash_embed, get_bot_webhook

bot_client = client()
type = 1

class ClanMemberFeed():

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
    
    def __init__(self,clan:aClan,player:aPlayer):
        self.clan = clan
        self.player = player

    @staticmethod
    def get_coc_client() -> ClashOfClansClient:
        return bot_client.bot.get_cog('ClashOfClansClient')

    @classmethod
    async def member_join(cls,clan:aClan,player:coc.ClanMember):
        try:
            clan_feeds = await cls.feeds_for_clan(clan)

            if len(clan_feeds) > 0:
                coc_client = cls.get_coc_client() 
                p = await coc_client.fetch_player(player.tag)

                feed = cls(clan,p)
                embed = await feed.join_embed()

                await asyncio.gather(*(feed.send_to_discord(embed, f) for f in clan_feeds))

        except Exception:
            bot_client.coc_main_log.exception(f"Error building Member Join Feed.")
    
    @classmethod
    async def member_leave(cls,clan:aClan,player:coc.ClanMember):
        try:
            clan_feeds = await cls.feeds_for_clan(clan)

            if len(clan_feeds) > 0:
                coc_client = cls.get_coc_client() 
                p = await coc_client.fetch_player(player.tag)

                feed = cls(clan,p) 
                embed = await feed.leave_embed()

                await asyncio.gather(*(feed.send_to_discord(embed, f) for f in clan_feeds))

        except Exception:
            bot_client.coc_main_log.exception(f"Error building Member Leave Feed.")
    
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
            text=f"Left {self.clan.name} [{self.clan.member_count}/50] " + (f"and joined {self.player.clan.name}" if self.player.clan and getattr(self.player.clan,'tag',None) != self.clan.tag else ""),
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