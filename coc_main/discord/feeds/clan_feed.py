import discord
from typing import *
from ...api_client import BotClashClient as client
from ...coc_objects.clans.clan import BasicClan
from ...discord.mongo_discord import db_ClanDataFeed

bot_client = client()

feed_description = {
    1: "Member Join/Leave",
    2: "Donation Log",
    3: "Raid Weekend Results",
    4: "Capital Contribution"
    }

class ClanDataFeed():

    @staticmethod
    async def feeds_for_clan(clan:BasicClan) -> List[db_ClanDataFeed]:
        def _get_from_db():
            return db_ClanDataFeed.objects(tag=clan.tag)
        
        feeds = await bot_client.run_in_thread(_get_from_db)
        return feeds
    
    @staticmethod
    async def delete_feed(feed_id:str):
        def _delete_from_db():
            db_ClanDataFeed.objects(id=feed_id).delete()
        
        await bot_client.run_in_thread(_delete_from_db)
        return