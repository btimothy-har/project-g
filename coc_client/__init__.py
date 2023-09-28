from redbot.core.bot import Red
from .cog_coc_client import ClashOfClansClient as coc_client

async def setup(bot:Red):
    if bot.user.id not in [828838353977868368,1031240380487831664]:
        raise RuntimeError("You are not allowed to install this cog.")
    
    cog_client = coc_client(bot)
    await bot.add_cog(cog_client)