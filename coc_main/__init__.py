import asyncio

from redbot.core.bot import Red
from .cog_coc_main import ClashOfClansMain as coc_main

async def setup(bot:Red):    
    cog_main = coc_main(bot)
    await bot.add_cog(cog_main)

    while True:
        cog = bot.get_cog("ClashOfClansMain")
        if cog.client._is_initialized:
            break
        await asyncio.sleep(1)
    
    from .cog_coc_client import ClashOfClansClient as coc_client
    cog_client = coc_client(bot)
    await bot.add_cog(cog_client)