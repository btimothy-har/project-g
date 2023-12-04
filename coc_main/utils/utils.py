import discord
import aiohttp
import unicodedata
import asyncio

from typing import *
from redbot.core.bot import Red

async def convert_seconds_to_str(seconds):
    dtime = seconds                      
    dtime_days,dtime = divmod(dtime,86400)
    dtime_hours,dtime = divmod(dtime,3600)
    dtime_minutes,dtime = divmod(dtime,60)

    return dtime_days, dtime_hours, dtime_minutes, dtime

def s_convert_seconds_to_str(seconds):
    dtime = seconds                      
    dtime_days,dtime = divmod(dtime,86400)
    dtime_hours,dtime = divmod(dtime,3600)
    dtime_minutes,dtime = divmod(dtime,60)

    return dtime_days, dtime_hours, dtime_minutes, dtime

async def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]
        await asyncio.sleep(0)

def check_rtl(text:str):
    def is_rtl(char):
        return unicodedata.bidirectional(char) in ['R', 'AL', 'RLE', 'RLO', 'RLI']
    if any(is_rtl(c) for c in text):
        return True
    else:
        return False

async def get_bot_webhook(bot:Red,channel):
    if isinstance(channel,discord.Thread):
        channel = channel.parent
    else:
        channel = channel
    
    channel_webhooks = await channel.webhooks()
    bot_webhook = [webhook for webhook in channel_webhooks if webhook.user == bot.user]
    
    if len(bot_webhook) > 0:
        webhook = bot_webhook[0]
    else:
        async with aiohttp.ClientSession() as session:
            async with session.get(bot.user.display_avatar.url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.read()
        webhook = await channel.create_webhook(
            name=f"{bot.user.name} Webhook",
            avatar=data,
            reason=f"Webhook for {bot.user.name}."
            )
    return webhook