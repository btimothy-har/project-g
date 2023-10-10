import asyncio
import discord

from typing import *
from mongoengine import *

from ..cog_coc_client import ClashOfClansClient
from ..api_client import BotClashClient as client

from redbot.core.utils import AsyncIter

from .clan_link import ClanGuildLink, db_ClanGuildLink
from .clan_panel import GuildClanPanel, db_GuildClanPanel
from .application_panel import GuildApplicationPanel, ClanApplyMenu, db_GuildApplyPanel
from .clocks import aGuildClocks
from .helpers import guild_clan_panel_embed, guild_application_panel_embed

from ..coc_objects.clans.clan import aClan, db_Clan, db_AllianceClan

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
    ### CLAN LINKS
    ##################################################
    @property
    def clan_links(self) -> List[ClanGuildLink]:
        return [ClanGuildLink(db) for db in db_ClanGuildLink.objects(guild_id=self.id)]
    
    ##################################################
    ### CLAN PANELS
    ##################################################
    @property
    def clan_panels(self) -> List[GuildClanPanel]:
        return [GuildClanPanel(db) for db in db_GuildClanPanel.objects(server_id=self.id)]

    async def create_clan_panel(self,channel:discord.TextChannel):
        await GuildClanPanel.create(self.id,channel.id)
        #await aGuild.update_clan_panels(self.id)
    
    async def delete_clan_panel(self,channel:discord.TextChannel):
        panel = GuildClanPanel.get_panel(self.id,channel.id)
        if not panel:
            return
        await panel.delete()

    async def update_clan_panels(self):
        while True:
            if len(self.clan_panels) == 0 or len(self.clan_links) == 0:
                return
            linked_clans = await asyncio.gather(*(self.coc_client.fetch_clan(c.tag) for c in self.clan_links))
            embeds = []
            if self.id == 688449973553201335:
                arix_rank = {
                    '#20YLR2LUJ':1,
                    '#28VUPJRPU':2,
                    '#2YL99GC9L':3,
                    '#92G9J8CG':4
                    }
                clans = sorted(linked_clans,key=lambda c:((arix_rank.get(c.tag,999)*-1),c.level,c.max_recruitment_level,c.capital_points),reverse=True)
            else:
                clans = sorted(linked_clans,key=lambda c:(c.level,c.max_recruitment_level,c.capital_points),reverse=True)
            
            async for clan in AsyncIter(clans):
                embed = await guild_clan_panel_embed(clan=clan)
                embeds.append({
                    'clan':clan,
                    'embed':embed
                    }
                )
            # Overwrite for Alliance Home Server
            if self.id in [1132581106571550831,680798075685699691]:
                family_clans = [c.tag for c in db_AllianceClan.objects()]
                async for c in AsyncIter(family_clans):
                    if c not in [c.tag for c in clans]:
                        clan = await self.coc_client.fetch_clan(c)
                        if len(clan.linked_servers) == 0:
                            continue
                        embed = await guild_clan_panel_embed(
                            clan=clan,
                            guild=clan.linked_servers[0]
                            )
                        embeds.append({
                            'clan':clan,
                            'embed':embed
                            }
                        )                
            async for panel in AsyncIter(self.clan_panels):
                await panel.send_to_discord(embeds)
            break
        
        bot_client.coc_main_log.info(f"Clan Panels for {self.guild.name} ({self.id}) updated.")

    ##################################################
    ### APPLICATION PANELS
    ##################################################    
    @property
    def apply_panels(self) -> List[GuildApplicationPanel]:
        return [GuildApplicationPanel(db) for db in db_GuildApplyPanel.objects(server_id=self.id)]
    
    async def create_apply_panel(self,channel:discord.TextChannel):
        return await GuildApplicationPanel.create(self.id,channel.id)
    
    async def delete_apply_panel(self,channel:discord.TextChannel):
        panel = GuildApplicationPanel.get_panel(self.id,channel.id)
        if not panel:
            return
        await panel.delete()

    async def update_apply_panels(self):
        if len(self.apply_panels) == 0 or len(self.clan_links) == 0:
            return
        all_clans = await asyncio.gather(*(self.coc_client.fetch_clan(c.tag) for c in self.clan_links))
        if self.id == 688449973553201335:
            arix_rank = {
                '#20YLR2LUJ':1,
                '#28VUPJRPU':2,
                '#2YL99GC9L':3,
                '#92G9J8CG':4
                }
            clans = sorted(all_clans,key=lambda c:((arix_rank.get(c.tag,999)*-1),c.level,c.max_recruitment_level,c.capital_points),reverse=True)
        else:
            clans = sorted(all_clans,key=lambda c:(c.level,c.max_recruitment_level,c.capital_points),reverse=True)

        embed = await guild_application_panel_embed(guild=self.guild,clans=clans)

        async for panel in AsyncIter(self.apply_panels):
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
    @property
    def clock_config(self) -> aGuildClocks:
        return aGuildClocks(self.id)    
    
    async def update_clocks(self):
        if self.clock_config.use_channels:
            await asyncio.gather(
                self.clock_config.update_season_channel(),
                self.clock_config.update_raidweekend_channel(),
                self.clock_config.update_clangames_channel(),
                self.clock_config.update_warleagues_channel()
                )        
        if self.clock_config.use_events:
            await asyncio.gather(
                self.clock_config.update_raidweekend_event(),
                self.clock_config.update_clangames_event(),
                self.clock_config.update_warleagues_event()
                )
