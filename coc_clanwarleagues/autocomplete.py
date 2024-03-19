import discord
import random
import logging

from redbot.core import app_commands
from redbot.core.utils import AsyncIter

from coc_main.client.global_client import GlobalClient

LOG = logging.getLogger("coc.main")

async def autocomplete_all_league_clans(interaction:discord.Interaction,current:str):
    try:
        league_clans = await GlobalClient.coc_client.get_war_league_clans()

        if current:
            clans = [c for c in league_clans 
                if current.lower() in c.name.lower() 
                or current.lower() in c.tag.lower() 
                or current.lower() in c.abbreviation.lower()
                ]
        else:
            clans = league_clans

        a_iter = AsyncIter(random.sample(clans,min(len(clans),8)))
        return [
            app_commands.Choice(
                name=f"{c.clean_name} | {c.tag}",
                value=c.tag)
            async for c in a_iter
            ]
    except Exception:
        LOG.exception("Error in autocomplete_all_league_clans")

async def autocomplete_season_league_clans(interaction:discord.Interaction,current:str):
    try:
        cog = GlobalClient.bot.get_cog("ClanWarLeagues")
        if not cog:
            return []
        season = cog.active_war_league_season
        
        league_clans = await GlobalClient.coc_client.get_league_clans(season=season,participating=True)

        if current:
            clans = [c for c in league_clans 
                if current.lower() in c.name.lower() 
                or current.lower() in c.tag.lower() 
                or current.lower() in c.abbreviation.lower()
                ]
        else:
            clans = league_clans

        a_iter = AsyncIter(random.sample(clans,min(len(clans),8)))
        return [
            app_commands.Choice(
                name=f"{c.clean_name} | {c.tag}",
                value=c.tag)
            async for c in a_iter
            ]
    except Exception:
        LOG.exception("Error in autocomplete_season_league_clans")

async def autocomplete_season_league_participants(interaction:discord.Interaction,current:str):
    try:
        cog = GlobalClient.bot.get_cog("ClanWarLeagues")
        if not cog:
            return []
        season = cog.active_war_league_season

        participants = await GlobalClient.coc_client.get_league_players(season=season,registered=True)

        if current:
            players = [p for p in participants 
                if current.lower() in p.name.lower() 
                or current.lower() in p.tag.lower()
                ]
        else:
            players = participants

        a_iter = AsyncIter(random.sample(players,min(len(players),8)))
        return [
            app_commands.Choice(
                name=f"{p.name} | {p.tag}",
                value=p.tag)
            async for p in a_iter
            ]
    except Exception:
        LOG.exception("Error in autocomplete_season_league_participants")