import discord
import urllib
import asyncio

from typing import *

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from redbot.core.utils import AsyncIter, bounded_gather

from .clan_feed import ClanDataFeed

from ...api_client import BotClashClient as client

from ...coc_objects.clans.clan import BasicClan, aClan
from ...coc_objects.events.raid_weekend import aRaidWeekend

from ...utils.components import get_bot_webhook

bot_client = client()

type = 3

class RaidResultsFeed(ClanDataFeed):
    _global_lock = asyncio.Lock()

    def __init__(self,database:dict):
        super().__init__(database)
    
    async def send_to_discord(self,clan:aClan,raid_weekend:aRaidWeekend,file:discord.File):
        try:
            if self.channel:
                webhook = await get_bot_webhook(bot_client.bot,self.channel)
                if isinstance(self.channel,discord.Thread):
                    await webhook.send(
                        username=clan.name,
                        avatar_url=clan.badge,
                        file=file,
                        thread=self.channel
                        )
                    
                else:
                    await webhook.send(
                        username=clan.name,
                        avatar_url=clan.badge,
                        file=file
                        )
        except Exception:
            bot_client.coc_main_log.exception(f"Error sending Raid Results Feed for {clan.name} - {raid_weekend.start_time.format('DD MMM YYYY')}")
    
    @classmethod
    async def create_feed(cls,
        clan:BasicClan,
        channel:Union[discord.TextChannel,discord.Thread]) -> ClanDataFeed:

        return await ClanDataFeed.create_feed(clan,channel,type)
     
    @classmethod
    async def start_feed(cls,clan:aClan,raid_weekend:aRaidWeekend):
        try:
            clan_feeds = await cls.feeds_for_clan(clan,type)

            if len(clan_feeds) > 0:
                image = await cls.get_results_image(clan,raid_weekend)

                a_iter = AsyncIter(clan_feeds)
                tasks = [feed.send_to_discord(clan,raid_weekend,image) async for feed in a_iter]
                await bounded_gather(*tasks,return_exceptions=True,limit=1)

        except Exception:
            bot_client.coc_main_log.exception(f"Error building Raid Results Feed for {clan.name} - {raid_weekend.start_time.format('DD MMM YYYY')}")    
    
    @classmethod
    async def get_results_image(cls,clan:aClan,raid_weekend:aRaidWeekend):
        async with cls._global_lock:
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

            if clan.abbreviation in ['AO9','PR','AS','PA','AX']:
                if clan.abbreviation == 'AO9':
                    badge = Image.open(base_path + '/ImgGen/logo_ao9.png')
                elif clan.abbreviation == 'PR':
                    badge = Image.open(base_path + '/ImgGen/logo_pr.png')
                elif clan.abbreviation == 'AS':
                    badge = Image.open(base_path + '/ImgGen/logo_as.png')
                elif clan.abbreviation == 'PA':
                    badge = Image.open(base_path + '/ImgGen/logo_pa.png')
                elif clan.abbreviation == 'AX':
                    badge = Image.open(base_path + '/ImgGen/logo_ax.png')

                background.paste(badge, (115, 100), badge.convert("RGBA"))
                draw.text((500, 970), f"{clan.name}\n{raid_weekend.start_time.format('DD MMMM YYYY')}", anchor="lm", fill=(255, 255, 255), stroke_width=stroke, stroke_fill=(0, 0, 0), font=clan_name)

            else:
                badge_data = clan.badge
                with urllib.request.urlopen(badge_data) as image_data:
                    badge = Image.open(image_data)

                background.paste(badge, (125, 135), badge.convert("RGBA"))
                draw.text((225, 110), f"{clan.name}", anchor="mm", fill=(255,255,255), stroke_width=stroke, stroke_fill=(0, 0, 0),font=clan_name)
                draw.text((500, 970), f"{raid_weekend.start_time.format('DD MMMM YYYY')}", anchor="lm", fill=(255, 255, 255), stroke_width=stroke, stroke_fill=(0, 0, 0), font=clan_name)

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

            draw.text((750, 250), f"{(raid_weekend.offensive_reward * 6) + raid_weekend.defensive_reward:,}", anchor="mm", fill=(255,255,255), stroke_width=4, stroke_fill=(0, 0, 0),font=total_medal_font)

            #draw.text((1155, 240), f"{self.ending_trophies:,}", anchor="lm", fill=(255,255,255), stroke_width=3, stroke_fill=(0, 0, 0),font=trophy_font)
            #draw.text((1155, 290), f"({delta_str})", anchor="lm", fill=(255,255,255), stroke_width=3, stroke_fill=(0, 0, 0),font=boxes_font)

            draw.text((155, 585), f"{raid_weekend.total_loot:,}", anchor="lm", fill=(255,255,255), stroke_width=stroke, stroke_fill=(0, 0, 0),font=boxes_font)
            draw.text((870, 585), f"{raid_weekend.offense_raids_completed}", anchor="lm", fill=(255,255,255), stroke_width=stroke, stroke_fill=(0, 0, 0),font=boxes_font)
            draw.text((1115, 585), f"{raid_weekend.defense_raids_completed}", anchor="lm", fill=(255,255,255), stroke_width=stroke, stroke_fill=(0, 0, 0),font=boxes_font)

            draw.text((155, 817), f"{raid_weekend.attack_count}", anchor="lm", fill=(255,255,255), stroke_width=stroke, stroke_fill=(0, 0, 0),font=boxes_font)
            draw.text((870, 817), f"{raid_weekend.destroyed_district_count}", anchor="lm", fill=(255,255,255), stroke_width=stroke, stroke_fill=(0, 0, 0),font=boxes_font)

            draw.text((550, 370), f"{raid_weekend.offensive_reward * 6}", anchor="lm", fill=(255, 255, 255), stroke_width=stroke,stroke_fill=(0, 0, 0), font=split_medal_font)
            draw.text((1245, 370), f"{raid_weekend.defensive_reward}", anchor="lm", fill=(255, 255, 255), stroke_width=stroke, stroke_fill=(0, 0, 0), font=split_medal_font)

            def save_im(background):            
                fp = bot_client.bot.coc_imggen_path + f"{clan.name} - {raid_weekend.start_time.format('DD MMM YYYY')}_test.png"
                background.save(fp, format="png", compress_level=1)
                file = discord.File(fp,filename="raid_image.png")
                return file

            file = await bot_client.run_in_thread(save_im,background)
            return file