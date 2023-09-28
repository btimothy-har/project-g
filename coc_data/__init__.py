import asyncio

from redbot.core.bot import Red
from .cog_coc_data import ClashOfClansData as data_client

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
    
    cog_client = data_client(bot)
    await bot.add_cog(cog_client)