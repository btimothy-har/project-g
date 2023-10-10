import discord
import pendulum
import random

from typing import *
from mongoengine import *

from redbot.core import app_commands
from redbot.core.bot import Red

from ..api_client import BotClashClient
from ..discord.mongo_discord import db_ClanGuildLink
from ..coc_objects.clans.mongo_clan import db_Clan, db_AllianceClan, db_WarLeagueClanSetup
from ..coc_objects.players.mongo_player import db_Player

bot_client = BotClashClient()

async def autocomplete_seasons(interaction:discord.Interaction,current:str):
    try:
        seasons = bot_client.tracked_seasons[:3]
        
        current_season = bot_client.current_season
        if current_season not in seasons:
            seasons.append(current_season)
        
        #sort seasons by startdate
        seasons.sort(key=lambda s: s.season_start,reverse=True)

        if not current:
            sel_seasons = seasons[:4]
        else:
            sel_seasons = [s for s in seasons if current.lower() in s.description.lower()][:4]
        
        return [
            app_commands.Choice(
                name=s.description,
                value=s.id
                )
            for s in sel_seasons
            ]
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_seasons")

####################################################################################################
#####
##### CLAN AUTOCOMPLETES
#####
####################################################################################################
async def autocomplete_clans(interaction:discord.Interaction,current:str):
    try:
        if not current:
            clan_tags = [db.tag for db in db_ClanGuildLink.objects(guild_id=interaction.guild.id)]
            clans = db_Clan.objects(tag__in=clan_tags)
        else:
            clans = db_Clan.objects(
                Q(tag__icontains=current) | Q(name__icontains=current) | Q(abbreviation=current.upper())
                )
        
        lc = list(clans)    
        return [
            app_commands.Choice(
                name=f"{c.name} | {c.tag}",
                value=c.tag)
            for c in random.sample(lc,min(len(lc),8))
            ]
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_clans")

async def autocomplete_war_league_clans(interaction:discord.Interaction,current:str):
    try:
        clan_tags = [db.tag for db in db_WarLeagueClanSetup.objects(is_active=True)]
        if current:
            clans = db_Clan.objects(
                (Q(tag__in=clan_tags)) &
                (Q(tag__icontains=current) | Q(name__icontains=current) | Q(abbreviation=current.upper()))
                )
        else:
            clans = db_Clan.objects(tag__in=clan_tags)
        
        lc = list(clans)    
        return [
            app_commands.Choice(
                name=f"{c.name} | {c.tag}",
                value=c.tag)
            for c in random.sample(lc,min(len(lc),8))
            ]
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_war_league_clans")

async def autocomplete_clans_coleader(interaction:discord.Interaction,current:str):
    try:
        clan_tags = [db.tag for db in db_AllianceClan.objects(Q(coleaders__contains=interaction.user.id) | Q(leader=interaction.user.id))]
        if current:
            clans = db_Clan.objects(
                (Q(tag__in=clan_tags)) &
                (Q(tag__icontains=current) | Q(name__icontains=current) | Q(abbreviation=current.upper()))
                )
        else:
            clans = db_Clan.objects(tag__in=clan_tags)
        
        lc = list(clans)
        return [
            app_commands.Choice(
                name=f"{c.name} | {c.tag}",
                value=c.tag)
            for c in random.sample(lc,min(len(lc),3))
            ]
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_clans_coleader")

####################################################################################################
#####
##### PLAYER AUTOCOMPLETES
#####
####################################################################################################
async def autocomplete_players(interaction:discord.Interaction,current:str):
    try:
        if current:
            players = db_Player.objects(
                Q(tag__icontains=current) | Q(name__icontains=current)
                )
        else:
            players = db_Player.objects(
                Q(discord_user=interaction.user.id)
                )
        sel_players = sorted(players,key=lambda p:(p.townhall,p.name),reverse=True)
        return [
            app_commands.Choice(
                name=f"{p.name} | TH{p.townhall} | {p.tag}",
                value=p.tag
                )
            for p in random.sample(sel_players,min(len(sel_players),8))
            ]
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_players")

async def autocomplete_players_members_only(interaction:discord.Interaction,current:str):
    try:
        if current:
            players = db_Player.objects(
                (Q(is_member=True)) &
                (Q(tag__icontains=current) | Q(name__icontains=current))
                )
        else:
            players = db_Player.objects(
                Q(is_member=True)
                )
        sel_players = sorted(players,key=lambda p:(p.townhall,p.name),reverse=True)
        return [
            app_commands.Choice(
                name=f"{p.name} | TH{p.townhall} | {p.tag}",
                value=p.tag
                )
            for p in random.sample(sel_players,min(len(sel_players),8))
            ]
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_players_members_only")