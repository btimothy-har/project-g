import asyncio

from redbot.core.bot import Red
from .cog_coc_main import ClashOfClansMain as coc_main

async def setup(bot:Red):
    if bot.user.id not in [828838353977868368,1031240380487831664]:
        raise RuntimeError("You are not allowed to install this cog.")
    
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

    from .cog_coc_tasks import ClashOfClansTasks as coc_tasks
    cog_tasks = coc_tasks(bot)
    await bot.add_cog(cog_tasks)