from .cog_utilities import GuildUtility

async def setup(bot):
    await bot.add_cog(GuildUtility(bot))