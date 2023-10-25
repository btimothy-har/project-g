import discord

from typing import *
from redbot.core import commands

from coc_main.utils.checks import is_coleader

def is_bank_admin(ctx:Union[discord.Interaction,commands.Context]):
    if isinstance(ctx,commands.Context):
        bot = ctx.bot
        guild = bot.get_guild(1132581106571550831) #assassins guild server
        user = guild.get_member(ctx.author.id) if guild else bot.get_user(ctx.author.id)
    elif isinstance(ctx,discord.Interaction):
        bot = ctx.client
        guild = bot.get_guild(1132581106571550831) #assassins guild server
        user = guild.get_member(ctx.user.id) if guild else bot.get_user(ctx.user.id)
    
    if user.id in bot.owner_ids:
        return True    
    if user.id in [664425813608759302,721330428111486996,632934232800362506]:
        return True
    if guild:    
        fin_role = guild.get_role(1136578130312695889) #fin ministry
        if fin_role in user.roles:
            return True    
    return False

def is_bank_server(ctx:Union[discord.Interaction,commands.Context]):
    if ctx.guild.id in [1132581106571550831,680798075685699691]:
        return True
    return False

def is_coleader_or_bank_admin(ctx:Union[discord.Interaction,commands.Context]):
    return is_coleader(ctx) or is_bank_admin(ctx)