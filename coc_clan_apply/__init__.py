from .cog_clan_apply import ClanApplications

async def setup(bot):
    if bot.user.id not in [828838353977868368,1176156235167449139,1031240380487831664,1204751022824886322]:
        raise RuntimeError("You are not allowed to install this cog.")
        
    await bot.add_cog(ClanApplications(bot))