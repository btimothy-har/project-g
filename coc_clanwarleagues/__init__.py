import asyncio

from redbot.core.bot import Red
from .cog_clanwarleagues import ClanWarLeagues

try_limit = 60
sleep_time = 1

async def setup(bot):
    count = 0
    while True:
        count += 1
        coc_main = bot.get_cog("ClashOfClansMain")
        if getattr(coc_main.global_client,'_ready',False):
            break
        if count > try_limit:
            raise RuntimeError("ClashOfClansClient is not installed.")
        await asyncio.sleep(sleep_time)
    
    count = 0
    while True:
        count += 1
        coc_data = bot.get_cog("ClashOfClansData")
        if coc_data:
            break
        if count > try_limit:
            raise RuntimeError("ClashOfClansData is not installed.")
        await asyncio.sleep(sleep_time)
    
    cwl_cog = ClanWarLeagues()
    await bot.add_cog(cwl_cog)