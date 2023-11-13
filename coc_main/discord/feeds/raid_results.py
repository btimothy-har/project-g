import os
import discord
import pendulum
import urllib
import asyncio

from typing import *

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from .clan_feed import ClanDataFeed

from ...api_client import BotClashClient as client

from ...coc_objects.clans.clan import BasicClan, aClan
from ...coc_objects.events.raid_weekend import aRaidWeekend

from ...discord.mongo_discord import db_ClanDataFeed

from ...utils.constants.coc_emojis import EmojisClash
from ...utils.components import clash_embed, get_bot_webhook

bot_client = client()

type = 3

class RaidResultsFeed():
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
    
    def __init__(self,clan:aClan,raid_weekend:aRaidWeekend):
        self.clan = clan
        self.raid_weekend = raid_weekend

    @property
    def feeds(self) -> db_ClanDataFeed:
        return self.clan.capital_raid_results_feed
    
    @classmethod
    async def send_results(cls,clan:aClan,raid_weekend:aRaidWeekend):
        try:
            a = cls(clan,raid_weekend)
            image = await a.get_results_image()
            feeds = await a.feeds_for_clan(clan)

            await asyncio.gather(*(a.send_to_discord(feed,image) for feed in feeds))
        except Exception:
            bot_client.coc_main_log.exception(f"Error building Raid Results Feed for {clan.name} - {raid_weekend.start_time.format('DD MMM YYYY')}")
        
    async def send_to_discord(self,feed:db_ClanDataFeed,file:discord.File):
        try:
            channel = bot_client.bot.get_channel(feed.channel_id)
            if not channel:
                return

            webhook = await get_bot_webhook(bot_client.bot,channel)
            if isinstance(channel,discord.Thread):
                await webhook.send(
                    username=self.clan.name,
                    avatar_url=self.clan.badge,
                    file=file,
                    thread=channel
                    )
                
            else:
                await webhook.send(
                    username=self.clan.name,
                    avatar_url=self.clan.badge,
                    file=file
                    )
        except Exception:
            bot_client.coc_main_log.exception(f"Error sending Raid Results Feed for {self.clan.name} - {self.raid_weekend.start_time.format('DD MMM YYYY')}")
    
    async def get_results_image(self):
        base_path = str(Path(__file__).parent)
        font = base_path + '/ImgGen/SCmagic.ttf'
        background = Image.open(base_path + '/ImgGen/raidweek.png')
        arix_logo = Image.open(base_path + '/ImgGen/arix_logo_mid.PNG')

        clan_name = ImageFont.truetype(font, 30)
        total_medal_font = ImageFont.truetype(font, 60)
        trophy_font = ImageFont.truetype(font,45)
        boxes_font = ImageFont.truetype(font,30)
        split_medal_font = ImageFont.truetype(font, 25)

        draw = ImageDraw.Draw(background)
        stroke = 2

        if self.clan.abbreviation in ['AO9','PR','AS','PA','AX']:
            if self.clan.abbreviation == 'AO9':
                badge = Image.open(base_path + '/ImgGen/logo_ao9.png')
            elif self.clan.abbreviation == 'PR':
                badge = Image.open(base_path + '/ImgGen/logo_pr.png')
            elif self.clan.abbreviation == 'AS':
                badge = Image.open(base_path + '/ImgGen/logo_as.png')
            elif self.clan.abbreviation == 'PA':
                badge = Image.open(base_path + '/ImgGen/logo_pa.png')
            elif self.clan.abbreviation == 'AX':
                badge = Image.open(base_path + '/ImgGen/logo_ax.png')

            background.paste(badge, (115, 100), badge.convert("RGBA"))
            draw.text((500, 970), f"{self.clan.name}\n{self.raid_weekend.start_time.format('DD MMMM YYYY')}", anchor="lm", fill=(255, 255, 255), stroke_width=stroke, stroke_fill=(0, 0, 0), font=clan_name)

        else:
            badge_data = self.clan.badge
            with urllib.request.urlopen(badge_data) as image_data:
                badge = Image.open(image_data)

            background.paste(badge, (125, 135), badge.convert("RGBA"))
            draw.text((225, 110), f"{self.clan.name}", anchor="mm", fill=(255,255,255), stroke_width=stroke, stroke_fill=(0, 0, 0),font=clan_name)
            draw.text((500, 970), f"{self.raid_weekend.start_time.format('DD MMMM YYYY')}", anchor="lm", fill=(255, 255, 255), stroke_width=stroke, stroke_fill=(0, 0, 0), font=clan_name)

        # if clan.capital_league.name != 'Unranked':
        #     clan_league = await self.bot.coc_client.get_league_named(clan.capital_league.name)
        #     with urllib.request.urlopen(clan_league.icon.url) as image_data:
        #         league_badge = Image.open(image_data)
        #         league_badge = league_badge.resize((int(league_badge.width * 0.65), int(league_badge.height * 0.65)))
        #         background.paste(league_badge, (1120, 30), league_badge.convert("RGBA"))

        background.paste(arix_logo, (400, 920), arix_logo.convert("RGBA"))

        # trophy_delta = self.ending_trophies - self.starting_trophies
        # if trophy_delta >= 0:
        #     delta_str = f"+{trophy_delta}"
        # else:
        #     delta_str = f"-{trophy_delta}"

        draw.text((750, 250), f"{(self.raid_weekend.offensive_reward * 6) + self.raid_weekend.defensive_reward:,}", anchor="mm", fill=(255,255,255), stroke_width=4, stroke_fill=(0, 0, 0),font=total_medal_font)

        #draw.text((1155, 240), f"{self.ending_trophies:,}", anchor="lm", fill=(255,255,255), stroke_width=3, stroke_fill=(0, 0, 0),font=trophy_font)
        #draw.text((1155, 290), f"({delta_str})", anchor="lm", fill=(255,255,255), stroke_width=3, stroke_fill=(0, 0, 0),font=boxes_font)

        draw.text((155, 585), f"{self.raid_weekend.total_loot:,}", anchor="lm", fill=(255,255,255), stroke_width=stroke, stroke_fill=(0, 0, 0),font=boxes_font)
        draw.text((870, 585), f"{self.raid_weekend.offense_raids_completed}", anchor="lm", fill=(255,255,255), stroke_width=stroke, stroke_fill=(0, 0, 0),font=boxes_font)
        draw.text((1115, 585), f"{self.raid_weekend.defense_raids_completed}", anchor="lm", fill=(255,255,255), stroke_width=stroke, stroke_fill=(0, 0, 0),font=boxes_font)

        draw.text((155, 817), f"{self.raid_weekend.attack_count}", anchor="lm", fill=(255,255,255), stroke_width=stroke, stroke_fill=(0, 0, 0),font=boxes_font)
        draw.text((870, 817), f"{self.raid_weekend.destroyed_district_count}", anchor="lm", fill=(255,255,255), stroke_width=stroke, stroke_fill=(0, 0, 0),font=boxes_font)

        draw.text((550, 370), f"{self.raid_weekend.offensive_reward * 6}", anchor="lm", fill=(255, 255, 255), stroke_width=stroke,stroke_fill=(0, 0, 0), font=split_medal_font)
        draw.text((1245, 370), f"{self.raid_weekend.defensive_reward}", anchor="lm", fill=(255, 255, 255), stroke_width=stroke, stroke_fill=(0, 0, 0), font=split_medal_font)

        def save_im(background):            
            fp = bot_client.bot.coc_imggen_path + f"{self.clan.name} - {self.raid_weekend.start_time.format('DD MMM YYYY')}.png"
            background.save(fp, format="png", compress_level=1)
            file = discord.File(fp,filename="raid_image.png")
            return file

        file = await asyncio.to_thread(save_im,background)
        return file