import asyncio

from redbot.core.bot import Red
from .cog_bank import Bank as bank

try_limit = 60
sleep_time = 1

async def setup(bot:Red):
    if bot.user.id not in [828838353977868368,1176156235167449139,1031240380487831664]:
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
    
    cog_bank = bank(bot)
    await bot.add_cog(cog_bank)