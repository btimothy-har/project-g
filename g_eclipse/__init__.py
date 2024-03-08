import asyncio

from redbot.core.bot import Red
from .cog_eclipse import ECLIPSE as eclipse

try_limit = 60
sleep_time = 1

async def setup(bot:Red):
    count = 0
    while True:
        count += 1
        coc_main = bot.get_cog("ClashOfClansMain")
        if getattr(coc_main.global_client,'_ready',False):
            break
        if count > try_limit:
            raise RuntimeError("ClashOfClansClient is not installed.")
        await asyncio.sleep(sleep_time)
    
    cog_lb = eclipse(bot)
    await bot.add_cog(cog_lb)