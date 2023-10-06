import asyncio
import discord

from typing import *
from mongoengine import *

from coc_client.api_client import BotClashClient
from redbot.core.utils import AsyncIter

from ..clans.base_clan import BasicClan

from .clan_link import ClanGuildLink
from .clan_panel import GuildClanPanel
from .apply_panel import GuildApplicationPanel
from .clocks import aGuildClocks

from ...utilities.components import *

from ...constants.coc_constants import *
from ...constants.coc_emojis import *
from ...constants.ui_emojis import *
from ...exceptions import *

bot_client = BotClashClient()

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
    
    ##################################################
    ### DISCORD GUILD ATTRIBUTES
    ##################################################
    @property
    def guild(self):
        return bot_client.bot.get_guild(self.id)    
    @property
    def name(self):
        return self.guild.name
    
    ##################################################
    ### CLAN LINKS
    ##################################################
    @property
    def _links(self) -> List[ClanGuildLink]:
        return ClanGuildLink.get_guild_links(self.id)
    @property
    def clans(self) -> List[BasicClan]:
        return [BasicClan(tag=link.tag) for link in self._links]    
    @property
    def member_roles(self) -> List[discord.Role]:
        return [link.member_role for link in self._links if link.member_role]    
    @property
    def elder_roles(self) -> List[discord.Role]:
        return [link.elder_role for link in self._links if link.elder_role]    
    @property
    def coleader_roles(self) -> List[discord.Role]:
        return [link.coleader_role for link in self._links if link.coleader_role]
    
    ##################################################
    ### CLAN PANELS
    ##################################################
    @staticmethod
    async def clan_panel_embed(clan,guild_id=None):
        guild = bot_client.bot.get_guild(guild_id)
        if guild:
            if guild.vanity_url:
                invite = await guild.vanity_invite()                        
            else:
                normal_invites = await guild.invites()
                if len(normal_invites) > 0:
                    invite = normal_invites[0]
                else:
                    invite = await guild.channels[0].create_invite()

        embed = await clash_embed(
            context=bot_client.bot,
            title=f"**{clan.title}**",
            message=f"{EmojisClash.CLAN} Level {clan.level}\u3000"
                + f"{EmojisUI.MEMBERS}" + (f" {clan.alliance_member_count}" if clan.is_alliance_clan else f" {clan.member_count}") + "\u3000"
                + f"{EmojisUI.GLOBE} {clan.location.name}\n"
                + (f"{EmojisClash.CLANWAR} W{clan.war_wins}/D{clan.war_ties}/L{clan.war_losses} (Streak: {clan.war_win_streak})\n" if clan.public_war_log else "")
                + f"{EmojisClash.WARLEAGUES}" + (f"{EmojisLeagues.get(clan.war_league.name)} {clan.war_league.name}\n" if clan.war_league else "Unranked\n")
                + f"{EmojisCapitalHall.get(clan.capital_hall)} CH {clan.capital_hall}\u3000"
                + f"{EmojisClash.CAPITALTROPHY} {clan.capital_points}\u3000"
                + (f"{EmojisLeagues.get(clan.capital_league.name)} {clan.capital_league}" if clan.capital_league else f"{EmojisLeagues.UNRANKED} Unranked") #+ "\n"
                + (f"\n\n**Join this Clan at: [{guild.name}]({str(invite)})**" if guild and invite else "")
                + f"\n\n{clan.c_description}"
                + f"\n\n**Recruiting**"
                + f"\nTownhalls: {clan.recruitment_level_emojis}"
                + (f"\n\n{clan.recruitment_info}" if len(clan.recruitment_info) > 0 else ""),
            thumbnail=clan.badge,
            show_author=False
            )
        return embed

    @classmethod
    async def update_clan_panels(cls,guild_id:int):
        while True:
            try:
                guild = cls(guild_id)

                clan_panels = await GuildClanPanel.get_guild_panels(guild.id)
                if len(clan_panels) == 0 or len(guild.clans) == 0:
                    return                
                clans = [await clan.get_full_clan() for clan in guild.clans]
                embeds = []
                if guild.id == 688449973553201335:
                    arix_rank = {
                        '#20YLR2LUJ':1,
                        '#28VUPJRPU':2,
                        '#2YL99GC9L':3,
                        '#92G9J8CG':4
                        }
                    clans = sorted(clans,key=lambda c:(arix_rank.get(c.tag,999),c.level,c.max_recruitment_level,c.capital_points),reverse=True)
                else:
                    clans = sorted(clans,key=lambda c:(c.level,c.max_recruitment_level,c.capital_points),reverse=True)
                
                async for clan in AsyncIter(clans):
                    embed = await aGuild.clan_panel_embed(clan)
                    embeds.append({
                        'clan':clan,
                        'embed':embed
                        }
                    )

                # Overwrite for Alliance Home Server
                if guild.id in [1132581106571550831,680798075685699691]:
                    all_clans = bot_client.cog.get_alliance_clans()
                    async for cc in AsyncIter(all_clans):
                        if cc.tag not in [c.tag for c in clans]:
                            if len(cc.linked_servers) == 0:
                                continue
                            clan = await cc.get_full_clan()
                            embed = await aGuild.clan_panel_embed(clan,clan.linked_servers[0].guild_id)
                            embeds.append({
                                'clan':clan,
                                'embed':embed
                                }
                            )                
                async for panel in AsyncIter(clan_panels):
                    await panel.send_to_discord(embeds)
                break
        
            except CacheNotReady:
                bot_client.cog.coc_main_log.warning(f"Unable to update Clan Panels for {guild.name} ({guild.id}). Cache not ready. Re-attempting in 1 minute.")
                await asyncio.sleep(60)
        
        bot_client.cog.coc_main_log.info(f"Clan Panels for {guild.name} ({guild.id}) updated.")
        return

    async def create_clan_panel(self,channel:discord.TextChannel):
        await GuildClanPanel.create(self.id,channel.id)
        await aGuild.update_clan_panels(self.id)
    
    async def delete_clan_panel(self,channel:discord.TextChannel):
        panel = GuildClanPanel.get_panel(self.id,channel.id)
        if not panel:
            return
        message = await panel.fetch_message()
        if message:
            await message.delete()        
        panel.delete()

    ##################################################
    ### APPLICATION PANELS
    ##################################################    
    async def application_panel_embed(self):
        embed = await clash_embed(
            context=bot_client.bot,
            title=f"**Apply to Join!**",
            message=f"Thinking of joining {self.guild.name}? Get started by picking one or more Clans to apply to."
                + f"\n\n**Tip:** For a smoother experience, link your Clash accounts with `$profile` before applying."
                + f"\n\u200b",
            thumbnail=str(self.guild.icon),
            show_author=False
            )
        clans = [await clan.get_full_clan() for clan in self.clans]
        async for c in AsyncIter(clans):
            embed.add_field(
                name=f"**{c.title}**",
                value=f"{c.summary_description}"
                    + f"\nRecruiting: {c.recruitment_level_emojis}"
                    + f"\n\u200b",
                inline=False
                )
        return embed

    @classmethod
    async def update_apply_panels(cls,guild_id:int):
        while True:
            try:
                guild = cls(guild_id)

                apply_panels = await GuildApplicationPanel.get_guild_panels(guild.id)
                if len(apply_panels) == 0 or len(guild.clans) == 0:
                    return                
                cc = [await clan.get_full_clan() for clan in guild.clans]                
                if guild.id == 688449973553201335:
                    arix_rank = {
                        '#20YLR2LUJ':1,
                        '#28VUPJRPU':2,
                        '#2YL99GC9L':3,
                        '#92G9J8CG':4
                        }
                    clans = sorted(cc,key=lambda c:(arix_rank.get(c.tag,999),c.level,c.max_recruitment_level,c.capital_points),reverse=True)
                else:
                    clans = sorted(cc,key=lambda c:(c.level,c.max_recruitment_level,c.capital_points),reverse=True)

                embed = await guild.application_panel_embed()

                async for panel in AsyncIter(apply_panels):
                    await panel.send_to_discord(clans,embed)
                break
        
            except CacheNotReady:
                bot_client.cog.coc_main_log.warning(f"Unable to update Application Panels for {guild.name} ({guild.id}). Cache not ready. Re-attempting in 1 minute.")
                await asyncio.sleep(60)
            
        bot_client.cog.coc_main_log.info(f"Application Panels for {guild.name} ({guild.id}) updated.")
        return 

    async def create_apply_panel(self,channel:discord.TextChannel):
        return await GuildApplicationPanel.create(self.id,channel.id)
    
    async def delete_apply_panel(self,channel:discord.TextChannel):
        panel = GuildApplicationPanel.get_panel(self.id,channel.id)
        if not panel:
            return        
        message = await panel.fetch_message()
        if message:
            await message.delete()        
        panel.delete()

    ##################################################
    ### CLOCKS
    ##################################################
    @property
    def clock_config(self):
        return aGuildClocks(self.id)
    
    @classmethod
    async def update_clocks(cls,guild_id):
        guild = cls(guild_id)
        tasks = []
        if guild.clock_config.use_channels:
            tasks.append(asyncio.create_task(guild.clock_config.update_season_channel()))
            tasks.append(asyncio.create_task(guild.clock_config.update_raidweekend_channel()))
            tasks.append(asyncio.create_task(guild.clock_config.update_clangames_channel()))
            tasks.append(asyncio.create_task(guild.clock_config.update_warleagues_channel()))
        
        if guild.clock_config.use_events:
            tasks.append(asyncio.create_task(guild.clock_config.update_raidweekend_event()))
            tasks.append(asyncio.create_task(guild.clock_config.update_clangames_event()))
            tasks.append(asyncio.create_task(guild.clock_config.update_warleagues_event()))
        
        await asyncio.gather(*tasks)
