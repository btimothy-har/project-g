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

    bank_admins = bot.get_cog("Bank").bank_admins
    
    if user.id in bot.owner_ids or user.id in bank_admins:
        return True
    return False

def is_payday_server(ctx:Union[discord.Interaction,commands.Context]):
    if ctx.guild.id in [1132581106571550831,680798075685699691]:
        return True
    return False

def is_bank_server(ctx:Union[discord.Interaction,commands.Context]):
    if ctx.guild.id in [1132581106571550831,680798075685699691]:
        return True
    return False

def is_coleader_or_bank_admin(ctx:Union[discord.Interaction,commands.Context]):
    return is_coleader(ctx) or is_bank_admin(ctx)