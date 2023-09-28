import discord
import pendulum

from typing import *

from redbot.core import app_commands

from coc_client.api_client import BotClashClient
from coc_data.exceptions import CacheNotReady
from coc_data.objects.discord.clan_panel import GuildClanPanel
from coc_data.objects.discord.apply_panel import GuildApplicationPanel
from coc_data.objects.discord.recruiting_reminder import RecruitingReminder

from coc_data.objects.discord.member import aMember

async def autocomplete_seasons(interaction:discord.Interaction,current:str):
    client = BotClashClient()
    seasons = client.cog.tracked_seasons[:3]
    
    current_season = client.cog.current_season
    if current_season not in seasons:
        seasons.append(current_season)
    
    #sort seasons by startdate
    seasons.sort(key=lambda s: s.season_start,reverse=True)

    if not current:
        sel_seasons = seasons
    else:
        sel_seasons = [s for s in seasons if current.lower() in s.description.lower()]
    
    return [
        app_commands.Choice(
            name=s.description,
            value=s.id
            )
        for s in sel_seasons
        ]

####################################################################################################
#####
##### CLAN AUTOCOMPLETES
#####
####################################################################################################
async def autocomplete_clans(interaction:discord.Interaction,current:str):
    client = BotClashClient()
    clans = client.cog.clan_cache.values

    if not current:
        sel_clans = [c for c in clans if c.is_registered_clan][:10]
    else:
        sel_clans = [c for c in clans if 
            current.lower() in c.name.lower() or
            current.lower() in c.tag.lower() or
            current.lower() in c.abbreviation.lower()
            ]
    return [
        app_commands.Choice(
            name=f"{getattr(c,'abbreviation','')}{' ' if getattr(c,'abbreviation',None) else ''}{c.name} | {c.tag}",
            value=c.tag
            )
        for c in sel_clans
        ]

async def autocomplete_clans_only_registered(interaction:discord.Interaction,current:str):
    client = BotClashClient()
    clans = [c for c in client.cog.clan_cache.values if c.is_registered_clan]

    if not current:
        sel_clans = clans[:10]
    else:
        sel_clans = [c for c in clans if 
            current.lower() in c.name.lower() or
            current.lower() in c.tag.lower() or
            current.lower() in c.abbreviation.lower()
            ]
    return [
        app_commands.Choice(
            name=f"{getattr(c,'abbreviation','')}{' ' if getattr(c,'abbreviation',None) else ''}{c.name} | {c.tag}",
            value=c.tag
            )
        for c in sel_clans
        ]
async def autocomplete_clans_only_cwl(interaction:discord.Interaction,current:str):
    client = BotClashClient()
    clans = client.cog.get_cwl_clans()

    if not current:
        sel_clans = clans[:10]
    else:
        sel_clans = [c for c in clans if 
            current.lower() in c.name.lower() or
            current.lower() in c.tag.lower() or
            current.lower() in c.abbreviation.lower()
            ]
    return [
        app_commands.Choice(
            name=f"{getattr(c,'abbreviation','')}{' ' if getattr(c,'abbreviation',None) else ''}{c.name} | {c.tag}",
            value=c.tag
            )
        for c in sel_clans
        ]

async def autocomplete_clans_coleader(interaction:discord.Interaction,current:str):
    member = aMember(interaction.user.id,interaction.guild.id)
    try:
        coleader_clans = member.coleader_clans
    except CacheNotReady:
        coleader_clans = []
    if not current:
        sel_clans = coleader_clans[:10]
    else:
        sel_clans = [c for c in coleader_clans if
            current.lower() in c.name.lower() or
            current.lower() in c.tag.lower() or
            current.lower() in c.abbreviation.lower()
            ]
    return [
        app_commands.Choice(
            name=f"{getattr(c,'abbreviation','')}{' ' if getattr(c,'abbreviation',None) else ''}{c.name} | {c.tag}",
            value=c.tag
            )
        for c in sel_clans
        ]

####################################################################################################
#####
##### PLAYER AUTOCOMPLETES
#####
####################################################################################################
async def autocomplete_players(interaction:discord.Interaction,current:str):
    client = BotClashClient()
    players = client.cog.player_cache.values
    if not current:
        sel_players = [p for p in players if p.discord_user == interaction.user.id][:10]
    else:
        sel_players = [p for p in players if
            current.lower() in p.name.lower() or
            current.lower() in p.tag.lower()
            ]        
    return [
        app_commands.Choice(
            name=f"{p.name} | TH{p.town_hall.level} | {p.tag}",
            value=p.tag
            )
        for p in sel_players
        ]

async def autocomplete_players_members_only(interaction:discord.Interaction,current:str):
    try:
        client = BotClashClient()
        players = client.cog.get_members_by_season()
    except CacheNotReady:
        players = []

    if not current:
        sel_players = [p for p in players if p.discord_user == interaction.user.id][:10]
    else:
        sel_players = [p for p in players if
            current.lower() in p.name.lower() or
            current.lower() in p.tag.lower()
            ]
    return [
        app_commands.Choice(
            name=f"{getattr(p.home_clan,'abbreviation','')}{' ' if getattr(p.home_clan,'abbreviation',None) else ''}{p.name} | TH{p.town_hall.level} | {p.tag}",\
            value=p.tag
            )
        for p in sel_players
        ]

####################################################################################################
#####
##### CONFIG AUTOCOMPLETES
#####
####################################################################################################
async def autocomplete_guild_clan_panels(interaction:discord.Interaction,current:str):
    panels = GuildClanPanel.get_guild_panels(interaction.guild.id)

    return [
        app_commands.Choice(name=str(panel),value=str(panel.channel_id)) for panel in panels
        ]

async def autocomplete_guild_apply_panels(interaction:discord.Interaction,current:str):
    panels = GuildApplicationPanel.get_guild_panels(interaction.guild.id)

    return [
        app_commands.Choice(name=str(panel),value=str(panel.channel_id)) for panel in panels
        ]

async def autocomplete_guild_recruiting_reminders(interaction:discord.Interaction,current:str):
    panels = RecruitingReminder.get_by_guild(interaction.guild.id)

    return [
        app_commands.Choice(name=str(panel),value=str(panel.id)) for panel in panels
        ]