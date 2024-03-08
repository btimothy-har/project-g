import asyncio
import coc

from typing import *

from coc_main.client.global_client import GlobalClient
from coc_main.coc_objects.clans.clan import aClan

############################################################
############################################################
#####
##### DEFAULT CLAN TASKS
#####
############################################################
############################################################
class ClanTasks():

    @coc.ClanEvents.member_count()
    @coc.ClanEvents.total_clan_donations()
    async def on_clan_activity(old_clan:aClan,new_clan:aClan):
        return
        # await new_clan._sync_cache(force=True)
    
    @coc.ClanEvents.member_join()
    async def on_clan_member_join_capture(member:coc.ClanMember,clan:aClan):
        if GlobalClient.coc_client._use_discovery:
            await GlobalClient.coc_client._player_discovery.put(member.tag)

    @coc.ClanEvents.member_leave()
    async def on_clan_member_leave_capture(member:coc.ClanMember,clan:aClan):
        if GlobalClient.coc_client._use_discovery:
            await GlobalClient.coc_client._player_discovery.put(member.tag)