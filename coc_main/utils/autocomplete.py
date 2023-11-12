import discord
import pendulum
import random

from typing import *
from mongoengine import *

from redbot.core import app_commands
from redbot.core.bot import Red

from ..api_client import BotClashClient
from ..discord.guild import ClanGuildLink
from ..discord.member import aMember
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
    def _get_clans_for_guild(scope_clans):
        return [i for i in db_Clan.objects(tag__in=scope_clans)]
    
    def _get_clans_for_query(current):
        clans = db_Clan.objects(
            Q(tag__icontains=current) | Q(name__icontains=current) | Q(abbreviation=current.upper())
            )
        return [i for i in clans]
    
    try:
        if not current:
            clan_tags = [db.tag for db in await ClanGuildLink.get_for_guild(interaction.guild.id)]
            clans = await bot_client.run_in_thread(_get_clans_for_guild,clan_tags)
        else:
            clans = await bot_client.run_in_thread(_get_clans_for_query,current)
        
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
        client_cog = bot_client.bot.get_cog("ClashOfClansClient")
        league_clans = await client_cog.get_war_league_clans()

        if current:
            clans = [c for c in league_clans 
                if current.lower() in c.name.lower() 
                or current.lower() in c.tag.lower() 
                or current.lower() in c.abbreviation.lower()
                ]
        else:
            clans = league_clans
        
        lc = list(clans)    
        return [
            app_commands.Choice(
                name=f"{c.clean_name} | {c.tag}",
                value=c.tag)
            for c in random.sample(lc,min(len(lc),8))
            ]
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_war_league_clans")

async def autocomplete_clans_coleader(interaction:discord.Interaction,current:str):
    try:
        member = aMember(interaction.user.id,interaction.guild.id)
        coleader_clans = member.coleader_clans
        
        if current:
            clans = [c for c in coleader_clans
                if current.lower() in c.name.lower()
                or current.lower() in c.tag.lower()
                or current.lower() in c.abbreviation.lower()
                ]
        else:
            clans = coleader_clans
        
        lc = list(clans)
        return [
            app_commands.Choice(
                name=f"{c.clean_name} | {c.tag}",
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
    def _get_players_for_query(current):
        players = db_Player.objects(
            Q(tag__icontains=current) | Q(name__icontains=current)
            )
        return [i for i in players]
    
    def _get_players_for_user(user_id):
        players = db_Player.objects(
            Q(discord_user=user_id)
            )
        return [i for i in players]
    
    try:
        if current:
            players = await bot_client.run_in_thread(_get_players_for_query,current)
        else:
            players = await bot_client.run_in_thread(_get_players_for_user,interaction.user.id)

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
    def _get_players_for_query(current):
        players = db_Player.objects(
            (Q(is_member=True)) &
            (Q(tag__icontains=current) | Q(name__icontains=current))
            )
        return [i for i in players]
    
    def _get_players_for_user(user_id):
        players = db_Player.objects(
            Q(is_member=True) & Q(discord_user=user_id)
            )
        return [i for i in players]
    
    try:
        if current:
            players = await bot_client.run_in_thread(_get_players_for_query,current)
        else:
            players = await bot_client.run_in_thread(_get_players_for_user,interaction.user.id)
            
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