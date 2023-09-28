import asyncio

from redbot.core.bot import Red
from .cog_eclipse import ECLIPSE as eclipse

try_limit = 60
sleep_time = 5

async def setup(bot:Red):
    if bot.user.id not in [828838353977868368,1031240380487831664]:
        raise RuntimeError("You are not allowed to install this cog.")
    
    count = 0
    while True:
        count += 1
        api_client = bot.get_cog("ClashOfClansClient")
        if api_client:
            break
        if count > try_limit:
            raise RuntimeError("ClashOfClansClient is not installed.")
        await asyncio.sleep(sleep_time)
    
    count = 0
    while True:
        count += 1
        data_client = bot.get_cog("ClashOfClansData")
        if getattr(data_client,'ready',False):
            break
        if count > try_limit:
            raise RuntimeError("ClashOfClansData is not installed.")
        await asyncio.sleep(sleep_time)
    
    count = 0
    while True:
        count += 1
        if getattr(bot,'coc_commands_loaded',False):
            break
        if count > try_limit:
            raise RuntimeError("Clash Commands is not installed.")
        await asyncio.sleep(sleep_time)
    
    cog_lb = eclipse(bot)
    await bot.add_cog(cog_lb)