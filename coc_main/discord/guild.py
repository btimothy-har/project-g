import discord

from typing import *

from redbot.core.utils import bounded_gather
from ..client.global_client import GlobalClient

from .clocks import aGuildClocks
from ..exceptions import InvalidGuild

##################################################
#####
##### CLASH SERVER
#####
##################################################
class aGuild(GlobalClient):
    def __init__(self,guild_id:int):
        self.id = guild_id

        if not self.guild:
            raise InvalidGuild(guild_id)

        self._panel_channel = 0
        self._panel_message = 0
        self.blocklist = []
        
    ##################################################
    ### DISCORD GUILD ATTRIBUTES
    ##################################################
    @property
    def guild(self) -> discord.Guild:
        return self.bot.get_guild(self.id)    
    @property
    def name(self) -> str:
        return self.guild.name

    ##################################################
    ### CLOCKS
    ##################################################    
    async def update_clocks(self):
        clock_config = await aGuildClocks.get_for_guild(self.id)
        tasks = []
        if getattr(clock_config,'use_channels',False):
            tasks.extend([
                clock_config.update_season_channel(),
                clock_config.update_raidweekend_channel(),
                clock_config.update_clangames_channel(),
                clock_config.update_warleagues_channel()
                ])
            
        if getattr(clock_config,'use_events',False):
            tasks.extend([
                clock_config.update_raidweekend_event(),
                clock_config.update_clangames_event(),
                clock_config.update_warleagues_event()
                ])
        
        if len(tasks) == 0:
            return
        await bounded_gather(*tasks,limit=1)