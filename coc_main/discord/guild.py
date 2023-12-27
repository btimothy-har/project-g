import asyncio
import discord

from typing import *

from redbot.core.utils import AsyncIter, bounded_gather

from .clan_link import ClanGuildLink
from .clan_panel import GuildClanPanel
from .application_panel import GuildApplicationPanel, ClanApplyMenu
from .clocks import aGuildClocks
from .helpers import guild_clan_panel_embed, guild_application_panel_embed

from ..cog_coc_client import ClashOfClansClient
from ..api_client import BotClashClient as client

from ..exceptions import InvalidGuild

bot_client = client()

##################################################
#####
##### CLASH SERVER
#####
##################################################
class aGuild():
    def __init__(self,guild_id:int):
        self.id = guild_id

        if not self.guild:
            raise InvalidGuild(guild_id)

        self._panel_channel = 0
        self._panel_message = 0
        self.blocklist = []
        
        # if self.guild.owner.id != 644530507505336330 and self.guild.owner.id not in self.blocklist:
        #     self.blocklist.append(self.guild.owner.id)
    
    @property
    def coc_client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
        
    ##################################################
    ### DISCORD GUILD ATTRIBUTES
    ##################################################
    @property
    def guild(self) -> discord.Guild:
        return bot_client.bot.get_guild(self.id)
    
    @property
    def name(self) -> str:
        return self.guild.name
    
    ##################################################
    ### CLAN PANELS
    ##################################################
    async def update_clan_panels(self):
        guild_panels = await GuildClanPanel.get_for_guild(self.id)
        linked_clans = await ClanGuildLink.get_for_guild(self.id)

        if len(guild_panels) == 0 or len(linked_clans) == 0:
            return
        fetch_clans = await self.coc_client.fetch_many_clans(*[c.tag for c in linked_clans])
        linked_clans = [c for c in fetch_clans if c.is_alliance_clan]
        
        embeds = []
        if self.id == 688449973553201335:
            arix_rank = {
                '#20YLR2LUJ':1,
                '#28VUPJRPU':2,
                '#2YL99GC9L':3,
                '#92G9J8CG':4
                }
            clans = sorted(
                linked_clans,
                key=lambda c:((arix_rank.get(c.tag,999)*-1),c.level,c.max_recruitment_level,c.capital_points),
                reverse=True
                )
        else:
            clans = sorted(
                linked_clans,
                key=lambda c:(c.level,c.max_recruitment_level,c.capital_points),
                reverse=True
                )
        
        async for clan in AsyncIter(clans):
            embed = await guild_clan_panel_embed(clan=clan)
            embeds.append({
                'clan':clan,
                'embed':embed
                }
            )
        # Overwrite for Alliance Home Server
        if self.id in [1132581106571550831,680798075685699691]:
            family_clans = await self.coc_client.get_alliance_clans()
            async for clan in AsyncIter(family_clans):
                if clan.tag not in [c.tag for c in clans]:
                    linked_servers = await ClanGuildLink.get_links_for_clan(clan.tag)
                    if len(linked_servers) == 0:
                        continue
                    embed = await guild_clan_panel_embed(
                        clan=clan,
                        guild=linked_servers[0].guild
                        )
                    embeds.append({
                        'clan':clan,
                        'embed':embed
                        }
                    )                
        async for panel in AsyncIter(guild_panels):
            await panel.send_to_discord(embeds)
        bot_client.coc_main_log.info(f"Clan Panels for {self.guild.name} ({self.id}) updated.")

    ##################################################
    ### APPLICATION PANELS
    ##################################################
    async def update_apply_panels(self):
        guild_panels = await GuildApplicationPanel.get_for_guild(self.id)
        linked_clans = await ClanGuildLink.get_for_guild(self.id)

        if len(guild_panels) == 0 or len(linked_clans) == 0:
            return
        fetch_clans = await self.coc_client.fetch_many_clans(*[c.tag for c in linked_clans])
        all_clans = [c for c in fetch_clans if c.is_alliance_clan]
        
        if self.id == 688449973553201335:
            arix_rank = {
                '#20YLR2LUJ':1,
                '#28VUPJRPU':2,
                '#2YL99GC9L':3,
                '#92G9J8CG':4
                }
            clans = sorted(
                all_clans,
                key=lambda c:((arix_rank.get(c.tag,999)*-1),c.level,c.max_recruitment_level,c.capital_points),
                reverse=True
                )
        else:
            clans = sorted(
                all_clans,
                key=lambda c:(c.level,c.max_recruitment_level,c.capital_points),
                reverse=True
                )

        embed = await guild_application_panel_embed(guild=self.guild,clans=clans)

        async for panel in AsyncIter(guild_panels):
            panel_view = ClanApplyMenu(
                panel=panel,
                list_of_clans=clans
                )
            await panel.send_to_discord(
                embed=embed,
                view=panel_view
                )
        bot_client.coc_main_log.info(f"Application Panels for {self.guild.name} ({self.id}) updated.")

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