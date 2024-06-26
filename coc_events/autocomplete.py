import discord
import random
import logging

from redbot.core import app_commands
from coc_main.client.global_client import GlobalClient

from .components.event import Event

LOG = logging.getLogger("coc.main")

async def autocomplete_active_events(interaction:discord.Interaction,current:str):
    try:
        events = await Event.get_all_active()
        if current:
            sel_events = [p for p in events if current.lower() in str(p.name).lower()]
        else:
            sel_events = events

        return [
            app_commands.Choice(
                name=str(event.name),
                value=str(event.id))
            for event in random.sample(sel_events,min(5,len(sel_events)))
            ]
    except:
        LOG.exception(f"Error in autocomplete_all_active_events")

async def autocomplete_user_players(interaction:discord.Interaction,current:str):
    try:
        if current:
            q_doc = {'$and': [
                {
                    '$or':[
                        {'tag':{'$regex':f'^{current}',"$options":"i"}},
                        {'name':{'$regex':f'^{current}',"$options":"i"}}
                    ]
                },
                {'discord_user':interaction.user.id}
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
        LOG.exception("Error in autocomplete_user_players")