import discord
import random
import logging

from typing import *

from redbot.core import app_commands
from redbot.core.utils import AsyncIter

from ..client.global_client import GlobalClient

from ..coc_objects.season.season import aClashSeason
from ..discord.clan_link import ClanGuildLink
from ..discord.member import aMember

LOG = logging.getLogger("coc.main")

async def autocomplete_seasons(interaction:discord.Interaction,current:str):
    try:
        seasons = aClashSeason.all_seasons()[:3]
        
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
        LOG.exception("Error in autocomplete_seasons")

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
                {'tag':{'$regex':f'^{current}',"$options":"i"}},
                {'name':{'$regex':f'^{current}',"$options":"i"}},
                {'abbreviation':{'$regex':f'^{current}',"$options":"i"}}
                ]
                }
        pipeline = [
            {'$match': q_doc},
            {'$sample': {'size': 8}}
            ]
        query = GlobalClient.database.db__clan.aggregate(pipeline)
        return [
            app_commands.Choice(
                name=f"{c.get('name','')} | {c['_id']}",
                value=c['_id'])
            async for c in query
            ]
    except Exception:
        LOG.exception("Error in autocomplete_clans")

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
        LOG.exception("Error in autocomplete_clans_coleader")

####################################################################################################
#####
##### PLAYER AUTOCOMPLETES
#####
####################################################################################################
async def autocomplete_players(interaction:discord.Interaction,current:str):
    try:
        if current:
            q_doc = {'$or':[
                {'tag':{'$regex':f'^{current}',"$options":"i"}},
                {'name':{'$regex':f'^{current}',"$options":"i"}}
                ]
                }
        else:
            q_doc = {'discord_user':interaction.user.id}

        pipeline = [
            {'$match': q_doc},
            {'$sample': {'size': 8}}
            ]
        query = GlobalClient.database.db__player.aggregate(pipeline)
        return [
            app_commands.Choice(
                name=f"{p.get('name','')} | TH{p.get('townhall',1)} | {p['_id']}",
                value=p['_id']
                )
            async for p in query
            ]
    except Exception:
        LOG.exception("Error in autocomplete_players")

async def autocomplete_players_members_only(interaction:discord.Interaction,current:str):
    try:
        if current:
            q_doc = {
                'is_member':True,
                '$or':[
                    {'tag':{'$regex':f'^{current}',"$options":"i"}},
                    {'name':{'$regex':f'^{current}',"$options":"i"}}
                    ]
                }
        else:
            q_doc = {'is_member':True,'discord_user':interaction.user.id}
        
        pipeline = [
            {'$match': q_doc},
            {'$sample': {'size': 8}}
            ]
        query = GlobalClient.database.db__player.aggregate(pipeline)
        return [
            app_commands.Choice(
                name=f"{p.get('name','')} | TH{p.get('townhall',1)} | {p['_id']}",
                value=p['_id']
                )
            async for p in query
            ]
    except Exception:
        LOG.exception("Error in autocomplete_players_members_only")