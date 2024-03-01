from .cog_clanwarleagues import ClanWarLeagues

async def setup(bot):        
    await bot.add_cog(ClanWarLeagues(bot))