import discord

from typing import *
from redbot.core import commands

from coc_main.discord.member import aMember

##################################################
### INTERACTION CHECKS
##################################################
def is_admin(interaction:discord.Interaction):
    bot = interaction.client
    if interaction.user.id in bot.owner_ids:
        return True    
    if interaction.guild:
        member = interaction.guild.get_member(interaction.user.id)
        if member.guild_permissions.administrator:
            return True    
    return False

def has_manage_roles(interaction:discord.Interaction):
    bot = interaction.client
    if interaction.user.id in bot.owner_ids:
        return True    
    if interaction.guild:
        member = interaction.guild.get_member(interaction.user.id)
        if member.guild_permissions.manage_roles:
            return True    
    return False

def is_bot_owner_or_guild_owner(interaction:discord.Interaction):
    bot = interaction.client
    if interaction.user.id in bot.owner_ids:
        return True    
    if interaction.guild:
        member = interaction.guild.get_member(interaction.user.id)
        if member.guild_permissions.administrator:
            return True
    return False

##################################################
### COMMAND CHECKS
##################################################
def has_manage_server(ctx:Union[discord.Interaction,commands.Context]):
    if not ctx.guild:
        return False
    if isinstance(ctx,commands.Context):
        bot = ctx.bot
        guild = ctx.guild
        user = guild.get_member(ctx.author.id) if guild else bot.get_user(ctx.author.id)
    elif isinstance(ctx,discord.Interaction):
        bot = ctx.client
        guild = ctx.guild
        user = guild.get_member(ctx.user.id) if guild else bot.get_user(ctx.user.id)

    if user.id in bot.owner_ids:
        return True    
    if user.guild_permissions.manage_guild:
        return True
    return False

def is_coleader(ctx:Union[discord.Interaction,commands.Context]):
    if not ctx.guild:
        return False
    if isinstance(ctx,commands.Context):
        bot = ctx.bot
        guild = ctx.guild
        user = guild.get_member(ctx.author.id) if guild else bot.get_user(ctx.author.id)
    elif isinstance(ctx,discord.Interaction):
        bot = ctx.client
        guild = ctx.guild
        user = guild.get_member(ctx.user.id) if guild else bot.get_user(ctx.user.id)

    if user.id in bot.owner_ids:
        return True
    
    if guild.id == 1132581106571550831:
        member = aMember(user.id)
    else:
        member = aMember(user.id,guild.id)
    if member.is_coleader:
        return True
    return False

def is_admin_or_leader(ctx:Union[discord.Interaction,commands.Context]):
    if not ctx.guild:
        return False
    if isinstance(ctx,commands.Context):
        bot = ctx.bot
        guild = ctx.guild
        user = guild.get_member(ctx.author.id) if guild else bot.get_user(ctx.author.id)
    elif isinstance(ctx,discord.Interaction):
        bot = ctx.client
        guild = ctx.guild
        user = guild.get_member(ctx.user.id) if guild else bot.get_user(ctx.user.id)

    if user.id in bot.owner_ids:
        return True
    member = guild.get_member(user.id)
    if member.guild_permissions.administrator:
        return True
    
    if guild.id == 1132581106571550831:
        member = aMember(user.id)
    else:
        member = aMember(user.id,guild.id)
    if member.is_leader:
        return True
    return False

def is_admin_or_coleader(ctx:Union[discord.Interaction,commands.Context]):
    if not ctx.guild:
        return False
    if isinstance(ctx,commands.Context):
        bot = ctx.bot
        guild = ctx.guild
        user = guild.get_member(ctx.author.id) if guild else bot.get_user(ctx.author.id)
    elif isinstance(ctx,discord.Interaction):
        bot = ctx.client
        guild = ctx.guild
        user = guild.get_member(ctx.user.id) if guild else bot.get_user(ctx.user.id)

    if user.id in bot.owner_ids:
        return True
    member = guild.get_member(user.id)
    if member.guild_permissions.administrator:
        return True
    
    if guild.id == 1132581106571550831:
        member = aMember(user.id)
    else:
        member = aMember(user.id,guild.id)
    if member.is_coleader:
        return True
    return False

def is_member(ctx:Union[discord.Interaction,commands.Context]):
    if not ctx.guild:
        return False
    if isinstance(ctx,commands.Context):
        bot = ctx.bot
        guild = ctx.guild
        user = guild.get_member(ctx.author.id) if guild else bot.get_user(ctx.author.id)
    elif isinstance(ctx,discord.Interaction):
        bot = ctx.client
        guild = ctx.guild
        user = guild.get_member(ctx.user.id) if guild else bot.get_user(ctx.user.id)

    if user.id in bot.owner_ids:
        return True
    
    if guild.id == 1132581106571550831:
        member = aMember(user.id)
    else:
        member = aMember(user.id,guild.id)
    if member.is_member:
        return True
    return False