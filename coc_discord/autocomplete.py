import discord
import random
import logging

from redbot.core import app_commands

from .panels.clan_panel import GuildClanPanel
from .panels.application_panel import GuildApplicationPanel

LOG = logging.getLogger("coc.discord")

async def autocomplete_guild_apply_panels(interaction:discord.Interaction,current:str):
    try:
        panels = await GuildApplicationPanel.get_for_guild(interaction.guild.id)
        if current:
            sel_panels = [p for p in panels if current.lower() in str(p).lower()]
        else:
            sel_panels = panels

        return [
            app_commands.Choice(
                name=str(panel),
                value=str(panel.channel_id))
            for panel in random.sample(sel_panels,min(5,len(sel_panels)))
            ]
    except:
        LOG.exception(f"Error in autocomplete_guild_apply_panels")

async def autocomplete_guild_clan_panels(interaction:discord.Interaction,current:str):
    try:
        panels = await GuildClanPanel.get_for_guild(interaction.guild.id)
        if current:
            sel_panels = [p for p in panels if current.lower() in str(p).lower()]
        else:
            sel_panels = panels

        return [
            app_commands.Choice(
                name=str(panel),
                value=str(panel.channel_id))
            for panel in random.sample(sel_panels,min(5,len(sel_panels)))
            ]
    except:
        LOG.exception(f"Error in autocomplete_guild_clan_panels")