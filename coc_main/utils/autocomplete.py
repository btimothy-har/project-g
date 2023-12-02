import discord
import random

from typing import *
from mongoengine import *

from redbot.core import app_commands
from redbot.core.utils import AsyncIter

from ..api_client import BotClashClient
from ..discord.guild import ClanGuildLink
from ..discord.member import aMember

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
            clan_tags = [db.tag for db in await ClanGuildLink.get_for_guild(interaction.guild.id)]            
            q_doc = {'_id':{'$in':clan_tags}}
        else:
            q_doc = {'$or':[
                {'tag':{'$regex':f'^{current}'}},
                {'name':{'$regex':f'^{current}'}},
                {'abbreviation':{'$regex':f'^{current.upper()}'}}
                ]
                }
        pipeline = [
            {'$match': q_doc},
            {'$sample': {'size': 8}}
            ]
        query = bot_client.coc_db.db__clan.aggregate(pipeline)
        return [
            app_commands.Choice(
                name=f"{c.get('name','')} | {c['_id']}",
                value=c['_id'])
            async for c in query
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

        a_iter = AsyncIter(random.sample(clans,min(len(clans),8)))
        return [
            app_commands.Choice(
                name=f"{c.clean_name} | {c.tag}",
                value=c.tag)
            async for c in a_iter
            ]
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_war_league_clans")

async def autocomplete_clans_coleader(interaction:discord.Interaction,current:str):
    try:
        member = await aMember(interaction.user.id,interaction.guild.id)
        coleader_clans = member.coleader_clans
        
        if current:
            clans = [c for c in coleader_clans
                if current.lower() in c.name.lower()
                or current.lower() in c.tag.lower()
                or current.lower() in c.abbreviation.lower()
                ]
        else:
            clans = coleader_clans
        
        a_iter = AsyncIter(random.sample(clans,min(len(clans),8)))
        return [
            app_commands.Choice(
                name=f"{c.clean_name} | {c.tag}",
                value=c.tag)
            async for c in a_iter
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
            q_doc = {'$or':[
                {'tag':{'$regex':f'^{current}'}},
                {'name':{'$regex':f'^{current}'}}
                ]
                }
        else:
            q_doc = {'discord_user':interaction.user.id}

        pipeline = [
            {'$match': q_doc},
            {'$sample': {'size': 8}}
            ]
        query = bot_client.coc_db.db__player.aggregate(pipeline)
        return [
            app_commands.Choice(
                name=f"{p.get('name','')} | TH{p.get('townhall',1)} | {p['_id']}",
                value=p['_id']
                )
            async for p in query
            ]
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_players")

async def autocomplete_players_members_only(interaction:discord.Interaction,current:str):
    try:
        if current:
            q_doc = {
                'is_member':True,
                '$or':[
                    {'tag':{'$regex':f'^{current}'}},
                    {'name':{'$regex':f'^{current}'}}
                    ]
                }
        else:
            q_doc = {'is_member':True,'discord_user':interaction.user.id}
        
        pipeline = [
            {'$match': q_doc},
            {'$sample': {'size': 8}}
            ]
        query = bot_client.coc_db.db__player.aggregate(pipeline)
        return [
            app_commands.Choice(
                name=f"{p.get('name','')} | TH{p.get('townhall',1)} | {p['_id']}",
                value=p['_id']
                )
            async for p in query
            ]
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_players_members_only")