import discord

from typing import *
from redbot.core import commands

def is_events_admin(ctx:Union[discord.Interaction,commands.Context]):
    if not ctx.guild:
        return False
    if isinstance(ctx,commands.Context):
        bot = ctx.bot
        guild = bot.get_guild(1132581106571550831) #assassins guild server
        user = guild.get_member(ctx.author.id) if guild else bot.get_user(ctx.author.id)
    elif isinstance(ctx,discord.Interaction):
        bot = ctx.client
        guild = bot.get_guild(1132581106571550831) #assassins guild server
        user = guild.get_member(ctx.user.id) if guild else bot.get_user(ctx.user.id)

    events_admin_role = bot.get_cog("Events").admin_role
    
    if getattr(user,'id',0) in bot.owner_ids or getattr(user,'id',0) in [m.id for m in events_admin_role.members]:
        return True
    return False