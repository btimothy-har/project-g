import discord
import pendulum
import re
import coc
import logging

from typing import *
from collections import Counter

from redbot.core import commands, app_commands
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter

from coc_main.client.global_client import GlobalClient
from coc_main.cog_coc_main import ClashOfClansMain as coc_main
from coc_main.coc_objects.season.season import aClashSeason
from coc_main.coc_objects.clans.clan import aClan

from coc_main.exceptions import InvalidRole

from coc_main.utils.components import clash_embed, MenuConfirmation, ClanLinkMenu
from coc_main.utils.utils import chunks
from coc_main.utils.autocomplete import autocomplete_clans, autocomplete_clans_coleader, autocomplete_seasons
from coc_main.utils.checks import is_admin, is_coleader, is_admin_or_leader, is_admin_or_coleader

from coc_main.utils.constants.coc_emojis import EmojisTownHall
from coc_main.utils.constants.ui_emojis import EmojisUI

from coc_main.discord.clan_link import ClanGuildLink

from .views.clan_settings import ClanSettingsMenu
from .views.clan_members import ClanMembersMenu
from .views.clan_warlog import ClanWarLog
from .excel.clan_export import ClanExcelExport

LOG = logging.getLogger("coc.main")

async def autocomplete_clan_settings(interaction:discord.Interaction,current:str):
    try:
        member = interaction.guild.get_member(interaction.user.id)
        if interaction.user.id in interaction.client.owner_ids or member.guild_permissions.administrator:
            return await autocomplete_clans(interaction,current)       
        else:
            return await autocomplete_clans_coleader(interaction,current)
        
    except Exception as exc:
        LOG.exception(f"Error in autocomplete_clan_settings: {exc}")
        return []

############################################################
############################################################
#####
##### CLAN COMMANDS COG
#####
############################################################
############################################################
class Clans(commands.Cog,GlobalClient):
    """
    Clan Commands
    """

    __author__ = coc_main.__author__
    __version__ = coc_main.__version__

    def __init__(self):
        pass

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"
    
    @property
    def bot(self) -> Red:
        return GlobalClient.bot
    
    async def cog_command_error(self,ctx:commands.Context,error:discord.DiscordException):
        original_exc = getattr(error,'original',error)
        await GlobalClient.handle_command_error(original_exc,ctx)

    async def cog_app_command_error(self,interaction:discord.Interaction,error:discord.DiscordException):
        original_exc = getattr(error,'original',error)
        await GlobalClient.handle_command_error(original_exc,interaction)
    
    ############################################################
    #####
    ##### ASSISTANT FUNCTIONS
    #####
    ############################################################
    @commands.Cog.listener()
    async def on_assistant_cog_add(self,cog:commands.Cog):
        schemas = [
            {
                "name": "_assistant_get_clan_named",
                "description": "Searches the database for Clans by a given name or abbreviation string. Returns a list of matches.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "clan_name_or_abbreviation": {
                            "description": "Clan Name or Abbreviation. Not caps sensitive.",
                            "type": "string",
                            },
                        },
                    "required": ["clan_name_or_abbreviation"],
                    },
                },
            {
                "name": "_assistant_get_clan_information",
                "description": "Returns complete information about a Clan. An identifying Clan Tag must be provided as this only returns one clan.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "clan_tag": {
                            "description": "The Clan Tag to search for.",
                            "type": "string",
                            },
                        },
                    "required": ["clan_tag"],
                    },
                },
            ]
        await cog.register_functions(cog_name="Clans", schemas=schemas)
    
    async def _assistant_get_clan_named(self,clan_name_or_abbreviation:str,*args,**kwargs) -> str:
        q_doc = {
            '$or':[
                {'name':{'$regex':f'^{clan_name_or_abbreviation}',"$options":"i"}},
                {'abbreviation':{'$regex':f'^{clan_name_or_abbreviation}',"$options":"i"}}
                ]
            }
        pipeline = [
            {'$match': q_doc},
            {'$sample': {'size': 8}}
            ]
        query = self.database.db__clan.aggregate(pipeline)

        clan_tags = [c['_id'] async for c in query]
        clans = [p async for p in self.coc_client.get_clans(clan_tags)]
        ret_clans = [c.assistant_name_json() for c in clans]
        return f"Found {len(ret_clans)} Clans matching `{clan_name_or_abbreviation}`. Clans: {ret_clans}"

    async def _assistant_get_clan_information(self,clan_tag:str,*args,**kwargs) -> str:
        try:
            clan = await self.coc_client.get_clan(clan_tag)
        except Exception as exc:
            return self.get_exception_response(exc)
        
        ret_clan = clan.assistant_clan_information()
        return f"Found Clan: {ret_clan}"
    
    ############################################################
    #####
    ##### CLAN ABBREVIATION LISTENER
    #####
    ############################################################
    @commands.Cog.listener("on_message")
    async def clan_abbreviation_listener(self,message:discord.Message):

        found_clans = []
        chk = True

        if not message.guild:
            return        
        if message.author.bot:
            return
        
        valid_prefixes = await self.bot.get_valid_prefixes(guild=message.guild)
        if not message.content.startswith(tuple(valid_prefixes)):
            return
        
        content_text = message.content[1:]

        for text in content_text.split():
            try:
                clan = await self.coc_client.from_clan_abbreviation(text)                
            except:
                chk = False
            else:
                found_clans.append(clan)
        
        if chk and len(found_clans) > 0:
            context = await self.bot.get_context(message)
            view = ClanLinkMenu(found_clans)
            embeds = []
            async for clan in AsyncIter(found_clans):
                embed = await clash_embed(
                    context=context,
                    title=f"{clan.title}",
                    message=f"{clan.long_description}"
                        + (f"\n\n> **Recruiting:** {clan.recruitment_level_emojis}" if clan.is_alliance_clan else "")
                        + f"\n\n{clan.description}",
                    thumbnail=clan.badge,
                    show_author=False,
                    )
                embeds.append(embed)
            return await message.reply(embeds=embeds,view=view)
        
    ############################################################
    #####
    ##### COMMAND: FIND CLAN
    #####
    ############################################################
    async def helper_find_clan(self,context:Union[commands.Context,discord.Interaction],clan_tag:str) -> Tuple[discord.Embed,Optional[ClanLinkMenu]]:        
        clan = await self.coc_client.get_clan(clan_tag)
        if not clan:
            embed = await clash_embed(
            context=context,
            message=f"I couldn't find a Clan with the tag `{clan_tag}`.",
            )
            return embed,None

        view = ClanLinkMenu([clan])
        embed = await clash_embed(
            context=context,
            title=f"{clan.title}",
            message=f"{clan.long_description}"
                + (f"\n\n> **Recruiting:** {clan.recruitment_level_emojis}" if clan.is_alliance_clan else "")
                + f"\n\n{clan.description}",
            thumbnail=clan.badge,
            show_author=False,
            )
        return embed,view
    
    @commands.command(name="findclan")
    @commands.guild_only()
    async def cmd_findclan(self,ctx:commands.Context,clan_tag:str):
        """
        Gets information about an in-game Clan.

        This command accepts an in-game Clash Tag. To use Alliance abbreviations, simply use `[p][abbreviation]` instead.
        """

        embed, view = await self.helper_find_clan(ctx,clan_tag)
        await ctx.reply(embed=embed,view=view)
        
    @app_commands.command(
        name="find-clan",
        description="Gets information about a Clan.")
    @app_commands.guild_only()
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan or manually enter a Tag.")
    async def appcmd_findclan(self,interaction:discord.Interaction,clan:str):

        await interaction.response.defer()
        embed, view = await self.helper_find_clan(interaction,clan)
        await interaction.followup.send(embed=embed,view=view)

    ############################################################
    #####
    ##### COMMAND GROUP: CLAN
    #####
    ############################################################
    @commands.group(name="clan")
    @commands.guild_only()
    async def cmdgroup_clan(self,ctx:commands.Context):
        """
        Group for Clan-related commands.

        **This is a command group. To use the sub-commands below, follow the syntax: `[p]clan [sub-command]`.**
        """
        if not ctx.invoked_subcommand:
            pass

    appgrp_clan = app_commands.Group(
        name="clan",
        description="Group for Clan-related Commands. Equivalent to [p]clan.",
        guild_only=True
        )    

    ############################################################
    #####
    ##### COMMAND: CLAN INFO
    #####
    ############################################################
    @cmdgroup_clan.command(name="info",aliases=['profile'])
    @commands.guild_only()
    async def subcmd_clan_info(self,ctx:commands.Context,clan_tag:str):
        """
        Gets information about an in-game Clan.

        This command accepts an in-game Clash Tag. To use Alliance abbreviations, simply use `[p][abbreviation]` instead.
        """

        embed, view = await self.helper_find_clan(ctx,clan_tag)
        await ctx.reply(embed=embed,view=view)
        
    @appgrp_clan.command(
        name="info",
        description="Get information about a Clan.")
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan or manually enter a Tag.")
    async def appcmd_clan_info(self,interaction:discord.Interaction,clan:str):

        await interaction.response.defer()
        embed, view = await self.helper_find_clan(interaction,clan)
        await interaction.followup.send(embed=embed,view=view)
    
    ############################################################
    #####
    ##### COMMAND: CLAN EXPORT
    #####
    ############################################################
    async def _clan_export_helper(self,
        context:Union[commands.Context,discord.Interaction],
        clan_tag_or_abbreviation:str,
        season:Optional[aClashSeason]=None):

        clan = await self.coc_client.from_clan_abbreviation(clan_tag_or_abbreviation)        
        if not clan:
            embed = await clash_embed(
                context=context,
                message=f"I couldn't find a Clan with the input `{clan_tag_or_abbreviation}`.",
                success=False,
                )
            return embed, None

        if not clan.is_alliance_clan:
            embed = await clash_embed(
                context=context,
                message=f"Only Alliance Clans can be exported.",
                success=False,
                )
            return embed, None
        
        if not season:
            season = aClashSeason.current()
        rp_file = await ClanExcelExport.generate_report(clan,season)
        discord_file = discord.File(rp_file)

        message = f"Here is your Data for **{clan}**.\n\nSeason: {season.description}."
        return message,discord_file

    @cmdgroup_clan.command(name="export")
    @commands.guild_only()
    @commands.check(is_coleader)
    async def cmd_clan_export(self,ctx:commands.Context,clan_tag_or_abbreviation:str):
        """
        Exports a Clan's data to Excel.

        Only usable for Alliance clans. Defaults to current season. To export for different seasons, use the Slash command.
        """

        embed = await clash_embed(
            context=ctx,
            message=f"{EmojisUI.LOADING} Exporting data... please wait.",
            timestamp=pendulum.now(),
            )
        message = await ctx.reply(embed=embed)

        embed, discord_file = await self._clan_export_helper(ctx,clan_tag_or_abbreviation)
        attachments = [discord_file] if discord_file else []

        await message.edit(
            content=f'{ctx.author.mention} {embed}',
            embed=None,
            attachments=attachments
            )

    @appgrp_clan.command(name="export",
        description="Export seasonal Clan Data to an Excel file.")
    @app_commands.check(is_coleader)
    @app_commands.autocomplete(
        clan=autocomplete_clans_coleader,
        season=autocomplete_seasons)
    @app_commands.describe(
        clan="Select a Clan. Only Alliance Clans can be selected.",
        season="Select a Season to export.")
    async def appcmd_clan_export(self,interaction:discord.Interaction,clan:str,season:str):  
        
        await interaction.response.defer()

        get_season = aClashSeason(season)

        embed, discord_file = await self._clan_export_helper(interaction,clan,get_season)
        attachments = [discord_file] if discord_file else []

        await interaction.edit_original_response(
            content=f'{interaction.user.mention} {embed}',
            embed=None,
            attachments=attachments
            )
    
    ############################################################
    #####
    ##### COMMAND: CLAN COMPO
    #####
    ############################################################
    async def _clan_composition_helper(self,
        context:Union[commands.Context,discord.Interaction],
        clan_tag_or_abbreviation:str) -> discord.Embed:

        clan = await self.coc_client.from_clan_abbreviation(clan_tag_or_abbreviation)        
        if not clan:
            embed = await clash_embed(
                context=context,
                message=f"I couldn't find a Clan with the input `{clan_tag_or_abbreviation}`.",
                success=False,
                )
            return embed

        embed = await clash_embed(
            context=context,
            title=f"{clan.title}",
            message=f"**Clan Member Composition**",
            thumbnail=clan.badge,
            )
                   
        ingame_members = [p async for p in self.coc_client.get_players([m.tag for m in clan.members])]

        if clan.is_alliance_clan and clan.alliance_member_count > 0:
            clan_members = [p async for p in self.coc_client.get_players(clan.alliance_members)]
            townhall_levels = [member.town_hall.level for member in clan_members]
            townhall_levels.sort(reverse=True)

            average_townhall = round(sum(townhall_levels)/len(townhall_levels),2)
            townhall_counts = Counter(townhall_levels)
            
            embed.add_field(
                name="**Registered Members**",
                value=f"Total: {len(clan_members)} {EmojisUI.MEMBERS}\n"
                    + f"Average: {EmojisTownHall.get(int(average_townhall))} {average_townhall}\n\n"
                    + "\n".join([
                        f"{EmojisTownHall.get(th)} `TH{th:02}`: {(count/len(clan_members))*100:.1f}% ({count})"
                        for th, count in townhall_counts.items()
                        ])
                    + "\n\u200b",
                inline=False,
                )
            
        townhall_levels = [member.town_hall.level for member in ingame_members]
        townhall_levels.sort(reverse=True)
        average_townhall = round(sum(townhall_levels)/len(townhall_levels),2)
        townhall_counts = Counter(townhall_levels)

        embed.add_field(
            name="**In-Game Members**",
            value=f"Total: {len(ingame_members)} {EmojisUI.MEMBERS}\n"
                + f"Average: {EmojisTownHall.get(int(average_townhall))} {average_townhall}\n\n"
                + "\n".join([
                    f"{EmojisTownHall.get(th)} `TH{th:02}`: {(count/len(ingame_members))*100:.1f}% ({count})"
                    for th, count in townhall_counts.items()
                    ])
                + "\n\u200b",
            inline=False,
            )
        return embed

    @cmdgroup_clan.command(name="compo")
    @commands.guild_only()
    async def cmd_clan_compo(self,ctx:commands.Context,clan_tag_or_abbreviation:str):
        """
        View a Clan's Town Hall composition.

        For registered Alliance clans, returns registered and in-game compositions.
        """

        embed = await self._clan_composition_helper(ctx,clan_tag_or_abbreviation)
        await ctx.reply(embed=embed)

    @appgrp_clan.command(
        name="compo",
        description="View a Clan's Townhall composition.")
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan.")
    async def appcmd_clan_compo(self,interaction:discord.Interaction,clan:str):

        await interaction.response.defer()
        embed = await self._clan_composition_helper(interaction,clan)
        await interaction.followup.send(embed=embed)

    ##################################################
    ### CLANDATA / STRENGTH
    ##################################################
    async def _clan_strength_helper(self,
        context:Union[commands.Context,discord.Interaction],
        clan_tag_or_abbreviation:str) -> discord.Embed:

        clan = await self.coc_client.from_clan_abbreviation(clan_tag_or_abbreviation)        
        if not clan:
            embed = await clash_embed(
                context=context,
                message=f"I couldn't find a Clan with the input `{clan_tag_or_abbreviation}`.",
                success=False,
                )
            return embed
        
        if clan.is_alliance_clan and clan.alliance_member_count > 0:
            showing_registered = True
            clan_members = [p async for p in self.coc_client.get_players(clan.alliance_members)]
        else:
            showing_registered = False
            clan_members = [p async for p in self.coc_client.get_players([m.tag for m in clan.members])]
        
        townhall_levels = list(set([member.town_hall.level for member in clan_members]))
        townhall_levels.sort(reverse=True)
        average_th = round(sum([member.town_hall.level for member in clan_members])/len([member.town_hall.level for member in clan_members]),2)

        embed = await clash_embed(
            context=context,
            title=f"{clan.title}",
            message=f"**Clan Offensive Strength**\n"
                + f"**Average TH: {EmojisTownHall.get(round(average_th))} {average_th}**\n\n"
                + (f"*Showing registered members only.*\n" if showing_registered else "*Showing in-game members only.*\n")
                + (f"The {EmojisUI.LOGOUT} emoji denotes a registered member who is currently not in the clan.\n" if clan.is_alliance_clan and clan.alliance_member_count > 0 else "")
                + f"\n`{'BK':^2}{'':^2}{'AQ':^2}{'':^2}{'GW':^2}{'':^2}{'RC':^2}{'':^2}{'Troops':>7}{'':^2}{'Spells':>7}{'':^2}`",
            thumbnail=clan.badge,
            )

        async for th in AsyncIter(townhall_levels):
            th_members = [member for member in clan_members if member.town_hall.level == th]
            th_members.sort(key=lambda member:(member.hero_strength,member.troop_strength,member.spell_strength),reverse=True)
            
            chunked_members = [c async for c in chunks(th_members,10)]
            a_iter = AsyncIter(chunked_members)

            async for i, members_chunk in a_iter.enumerate():
                embed.add_field(
                    name=f"{EmojisTownHall.get(th)} **TH{th}**"
                        + (f" - ({i+1}/{len(chunked_members)})" if len(chunked_members) > 1 else ""),
                    value="\n".join([
                        f"`"
                        + f"{getattr(member.barbarian_king,'level',''):^2}{'':^2}"
                        + f"{getattr(member.archer_queen,'level',''):^2}{'':^2}"
                        + f"{getattr(member.grand_warden,'level',''):^2}{'':^2}"
                        + f"{getattr(member.royal_champion,'level',''):^2}{'':^2}"
                        + f"{str(round(member.troop_strength_pct))+'%':>7}{'':^2}"
                        + f"{str(round(member.spell_strength_pct))+'%':>7}{'':^2}"
                        + "`"
                        + f"\u3000{re.sub('[_*/]','',member.clean_name)}"
                        + (f" {EmojisUI.LOGOUT}" if clan.is_alliance_clan and member.tag not in clan.members_dict else "")
                        for member in members_chunk
                        ]),
                    inline=False,
                    )
        return embed

    @cmdgroup_clan.command(name="strength")
    @commands.guild_only()
    async def subcmd_clan_strength(self,ctx:commands.Context,clan_tag_or_abbreviation:str):
        """
        View a Clan's overall Offensive Strength.

        For registered Alliance clans, returns only registered members.
        """
        
        embed = await self._clan_strength_helper(ctx,clan_tag_or_abbreviation)
        await ctx.reply(embed=embed)
    
    @appgrp_clan.command(
        name="strength",
        description="View a Clan's Offensive strength.")
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan.")
    async def appcmd_clan_strength(self,interaction:discord.Interaction,clan:str):

        await interaction.response.defer()
        embed = await self._clan_strength_helper(interaction,clan)
        await interaction.followup.send(embed=embed)
    
    ############################################################
    #####
    ##### COMMAND: CLAN MEMBERS
    #####
    ############################################################
    @cmdgroup_clan.command(name="members")
    @commands.guild_only()
    async def subcmd_clan_members(self,ctx:commands.Context,clan_tag_or_abbreviation:str):
        """
        Display info on a Clan's Members.

        Contains menus for Discord Links, Rank Status, and War Opt-Ins.

        By default, this shows all in-game members. For Alliance Clans, this will also return registered members who are not in the in-game clan.
        """
  
        clan = await self.coc_client.from_clan_abbreviation(clan_tag_or_abbreviation)
        if not clan:
            embed = await clash_embed(
                context=ctx,
                message=f"I couldn't find a Clan with the input `{clan_tag_or_abbreviation}`.",
                success=False,
                )
            return await ctx.reply(embed=embed)
        
        menu = ClanMembersMenu(ctx,clan)
        await menu.start()

    @appgrp_clan.command(name="members",
        description="View Clan Member information.")
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(
        clan="Select a Clan.") 
    async def appcmd_clan_members(self,interaction:discord.Interaction,clan:str):

        await interaction.response.defer()

        get_clan = await self.coc_client.get_clan(clan)
        if not clan:
            embed = await clash_embed(
                context=interaction,
                message=f"I couldn't find a Clan with the input `{clan}`.",
                success=False,
                )
            return await interaction.edit_original_response(embed=embed)

        menu = ClanMembersMenu(interaction,get_clan)
        await menu.start()
    
    ############################################################
    #####
    ##### COMMAND: CLAN WARLOG
    #####
    ############################################################
    @cmdgroup_clan.command(name="warlog")
    @commands.guild_only()
    async def subcmd_clan_warlog(self,ctx:commands.Context,clan_tag_or_abbreviation:str):
        """
        View a Clan's War Log.

        Only usable for Alliance clans.
        """

        clan = await self.coc_client.from_clan_abbreviation(clan_tag_or_abbreviation)
        if not clan.is_alliance_clan:
            embed = await clash_embed(
                context=ctx,
                message=f"Only Clan Wars for Alliance Clans are tracked.",
                success=False,
                )
            return await ctx.reply(embed=embed)

        menu = ClanWarLog(ctx,clan)
        await menu.start()

    @appgrp_clan.command(
        name="war-log",
        description="View a Clan's Townhall composition.")
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan.")
    async def appcmd_clan_warlog(self,interaction:discord.Interaction,clan:str):

        await interaction.response.defer()
        get_clan = await self.coc_client.get_clan(clan)
        if not get_clan.is_alliance_clan:
            embed = await clash_embed(
                context=interaction,
                message=f"Only Clan Wars for Alliance Clans are tracked.",
                success=False,
                )
            return await interaction.followup.send(embed=embed)

        menu = ClanWarLog(interaction,get_clan)
        await menu.start()
    
    ############################################################
    #####
    ##### COMMAND: CLAN REGISTER
    #####
    ############################################################
    async def helper_register_clan(self,
        context:Union[commands.Context,discord.Interaction],
        clan_tag:str,
        emoji:str,
        unicode_emoji:str,
        abbreviation:str):

        clan = await self.coc_client.get_clan(clan_tag)
        await clan.register(abbreviation=abbreviation,emoji=emoji,unicode_emoji=unicode_emoji)
        embed = await clash_embed(
            context=context,
            title=f"Registered: {clan.title}",
            message=clan.long_description,
            thumbnail=clan.badge,
            success=True
            )
        return embed

    @cmdgroup_clan.command(name="register")
    @commands.guild_only()
    @commands.admin()
    async def subcmd_clan_register(self,ctx:commands.Context,clan_tag:str,emoji:str,unicode_emoji:str,abbreviation:str):
        """
        Registers an in-game Clan to the bot.

        Assigns:
        > - Clan Emoji
        > - Clan Abbreviation
        """
        
        embed = await self.helper_register_clan(ctx,clan_tag,emoji,unicode_emoji,abbreviation)
        await ctx.reply(embed=embed)
    
    @appgrp_clan.command(
        name="register",
        description="Register an in-game Clan to the bot.")
    @app_commands.check(is_admin)
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(
        clan="Select a Clan, or enter a Clan Tag.",
        emoji="Provide the Emoji to use for the Clan.",
        unicode_emoji="Provide the Unicode Emoji to use for the Clan.",
        abbreviation="Provide the Clan's abbreviation.")
    async def appcmd_clan_register(self,interaction:discord.Interaction,
        clan:str,
        emoji:str,
        unicode_emoji:str,
        abbreviation:str):
        
        await interaction.response.defer()
        embed = await self.helper_register_clan(interaction,clan,emoji,unicode_emoji,abbreviation)
        await interaction.followup.send(embed=embed)
    
    ############################################################
    #####
    ##### COMMAND: CLAN UNREGISTER
    #####
    ############################################################
    async def helper_unregister_clan(self,
        context:Union[commands.Context,discord.Interaction],clan_tag:str):

        clan = await self.coc_client.get_clan(clan_tag)
        await clan.unregister()
        embed = await clash_embed(
            context=context,
            title=f"Unregistered: {clan.title}",
            message=clan.long_description,
            thumbnail=clan.badge,
            success=True
            )
        return embed

    @appgrp_clan.command(name="unregister")
    @commands.guild_only()
    @commands.is_owner()
    async def subcommand_unregister_clan(self,ctx:commands.Context,clan_tag:str):
        """
        Removes an in-game Clan from the bot.
        """
        
        embed = await self.helper_unregister_clan(ctx,clan_tag)
        await ctx.reply(embed=embed)
    
    ############################################################
    #####
    ##### COMMAND: CLAN LINK
    #####
    ############################################################
    @cmdgroup_clan.command(name="link")
    @commands.guild_only()
    @commands.admin()
    async def subcmd_clan_link(self,ctx:commands.Context,clan_tag:str,coleader_role_id:int,elder_role_id:int,member_role_id:int):
        """
        Links a Clan to this Discord Server.

        Linked Clans have linked Discord Roles, and will be synced based on membership status.
        > - Co-Leader Role
        > - Elder Role
        > - Member Role

        This command requires you to provide Co-Leader, Elder, and Member roles. To add a Visitor or Clan War Role, use the Slash command.
        """
        
        clan = await self.coc_client.get_clan(clan_tag)

        coleader_role = ctx.guild.get_role(coleader_role_id)
        if not coleader_role:
            raise InvalidRole(f"Co-Leader Role ID `{coleader_role_id}` is not valid.")
        
        elder_role = ctx.guild.get_role(elder_role_id)
        if not elder_role:
            raise InvalidRole(f"Elder Role ID `{elder_role_id}` is not valid.")
        
        member_role = ctx.guild.get_role(member_role_id)
        if not member_role:
            raise InvalidRole(f"Member Role ID `{member_role_id}` is not valid.")
        
        embed = await clash_embed(
            context=ctx,
            title=f"Link Clan: **{clan.title}**",
            message=f"**Co-Leader Role:** {getattr(coleader_role,'mention','Not Set')}"
                + f"\n**Elder Role:** {getattr(elder_role,'mention','Not Set')}"
                + f"\n**Member Role:** {getattr(member_role,'mention','Not Set')}",
            thumbnail=clan.badge)
        confirm_view = MenuConfirmation(ctx)
        
        message = await ctx.reply(
            content=f"{ctx.author.mention}, please confirm the below action.",
            embed=embed,
            view=confirm_view
            )        
        view_timed_out = await confirm_view.wait()

        if view_timed_out:
            timeout_embed = await clash_embed(
                context=ctx,
                message=f"Confirmation timed out. Please try again.",
                success=False)
            return await message.edit(content=None,embed=[embed,timeout_embed],view=None)
    
        if not confirm_view.confirmation:
            cancel_embed = await clash_embed(
                context=ctx,
                message=f"Task cancelled.",
                success=False)
            return await message.edit(content=None,embed=[embed,cancel_embed],view=None)

        if confirm_view.confirmation:
            await clan._sync_cache()

            await ClanGuildLink.link_member_role(clan_tag=clan.tag,guild=ctx.guild,member_role=member_role)
            await ClanGuildLink.link_elder_role(clan_tag=clan.tag,guild=ctx.guild,elder_role=elder_role)
            await ClanGuildLink.link_coleader_role(clan_tag=clan.tag,guild=ctx.guild,coleader_role=coleader_role)

            link = await ClanGuildLink.get_link(clan.tag,ctx.guild.id)
            complete_embed = await clash_embed(
                context=ctx,
                title=f"Clan Linked: **{clan.title}**",
                message=f"**Co-Leader Role:** {getattr(link.coleader_role,'mention','Not Set')}"
                    + f"\n**Elder Role:** {getattr(link.elder_role,'mention','Not Set')}"
                    + f"\n**Member Role:** {getattr(link.member_role,'mention','Not Set')}",
                url=clan.share_link,
                success=True,
                thumbnail=clan.badge)
            return await message.edit(content=None,embed=complete_embed,view=None)

    @appgrp_clan.command(
        name="link",
        description="Links a Clan to this Discord Server.")
    @app_commands.check(is_admin)
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(
        clan="Select a Clan.",
        coleader_role="The Role to assign to Co-Leaders and Leaders.",
        elder_role="The Role to assign to Elders and above.",
        member_role="The Role to assign to registered Members. Only applicable if this is a Guild Clan.",
        visitor_role="The Role to assign to all in-game members, if linked to a Discord user.",
        clan_war_role="The Role to assign to all in-game members who are participating in the current Clan War.")
    async def appcmd_clan_link(self,
        interaction:discord.Interaction,
        clan:str,
        coleader_role:Optional[discord.Role]=None,
        elder_role:Optional[discord.Role]=None,
        member_role:Optional[discord.Role]=None,
        visitor_role:Optional[discord.Role]=None,
        clan_war_role:Optional[discord.Role]=None):
        
        await interaction.response.defer()
        
        select_clan = await self.coc_client.get_clan(clan)
        embed = await clash_embed(
            context=interaction,
            title=f"Link Clan: **{select_clan.title}**",
            message=(f"**Co-Leader Role:** {coleader_role.mention}\n" if coleader_role else "")
                + (f"**Elder Role:** {elder_role.mention}\n" if elder_role else "")
                + (f"**Member Role:** {member_role.mention}\n" if member_role else "")
                + (f"**Visitor Role:** {visitor_role.mention}\n" if visitor_role else "")
                + (f"**Clan War Role:** {clan_war_role.mention}" if clan_war_role else ""),
            thumbnail=select_clan.badge)
        confirm_view = MenuConfirmation(interaction)

        await interaction.followup.send(
            content=f"{interaction.user.mention}, please confirm the below action.",
            embed=embed,
            view=confirm_view,
            wait=True
            )
        view_timed_out = await confirm_view.wait()

        if view_timed_out:
            timeout_embed = await clash_embed(
                context=interaction,
                message=f"Confirmation timed out. Please try again.",
                success=False)
            return await interaction.edit_original_response(content=None,embeds=[embed,timeout_embed],view=None)
    
        if not confirm_view.confirmation:
            cancel_embed = await clash_embed(
                context=interaction,
                message=f"Task cancelled.",
                success=False)
            return await interaction.edit_original_response(content=None,embeds=[embed,cancel_embed],view=None)

        if confirm_view.confirmation:
            await select_clan._sync_cache()

            if member_role:
                await ClanGuildLink.link_member_role(clan_tag=select_clan.tag,guild=interaction.guild,member_role=member_role)
            if elder_role:
                await ClanGuildLink.link_elder_role(clan_tag=select_clan.tag,guild=interaction.guild,elder_role=elder_role) 
            if coleader_role:
                await ClanGuildLink.link_coleader_role(clan_tag=select_clan.tag,guild=interaction.guild,coleader_role=coleader_role)
            if visitor_role:
                await ClanGuildLink.link_visitor_role(clan_tag=select_clan.tag,guild=interaction.guild,visitor_role=visitor_role)
            if clan_war_role:
                await ClanGuildLink.link_clan_war_role(clan_tag=select_clan.tag,guild=interaction.guild,clan_war_role=clan_war_role)

            link = await ClanGuildLink.get_link(select_clan.tag,interaction.guild.id) 
            complete_embed = await clash_embed(
                context=interaction,
                title=f"Link Clan: **{select_clan.title}**",
                message=f"**Co-Leader Role:** {getattr(link.coleader_role,'mention','Not Set')}"
                    + f"\n**Elder Role:** {getattr(link.elder_role,'mention','Not Set')}"
                    + f"\n**Member Role:** {getattr(link.member_role,'mention','Not Set')}"
                    + f"\n**Visitor Role:** {getattr(link.visitor_role,'mention','Not Set')}"
                    + f"\n**Clan War Role:** {getattr(link.clan_war_role,'mention','Not Set')}",
                success=True,
                thumbnail=select_clan.badge)
            return await interaction.edit_original_response(content=None,embed=complete_embed,view=None)
    
    ############################################################
    #####
    ##### COMMAND: CLAN UNLINK
    #####
    ############################################################
    @cmdgroup_clan.command(name="unlink")
    @commands.guild_only()
    @commands.admin()
    async def subcmd_clan_unlink(self,ctx:commands.Context,clan_tag:str):
        """
        Unlinks a Clan from this Discord Server.
        """
        clan = await self.coc_client.get_clan(clan_tag)
        link = await ClanGuildLink.get_link(clan.tag,ctx.guild.id)
        
        embed = await clash_embed(
            context=ctx,
            title=f"Unlink Clan: **{clan.title}**",
            message=f"**Co-Leader Role:** {getattr(link.coleader_role,'mention','Not Set')}"
                + f"\n**Elder Role:** {getattr(link.elder_role,'mention','Not Set')}"
                + f"\n**Member Role:** {getattr(link.member_role,'mention','Not Set')}"
                + f"\n**Visitor Role:** {getattr(link.visitor_role,'mention','Not Set')}"
                + f"\n**Clan War Role:** {getattr(link.clan_war_role,'mention','Not Set')}",
            thumbnail=clan.badge)
        confirm_view = MenuConfirmation(ctx)
        
        message = await ctx.reply(
            content=f"{ctx.author.mention}, please confirm the below action.",
            embed=embed,
            view=confirm_view
            )        
        view_timed_out = await confirm_view.wait()

        if view_timed_out:
            timeout_embed = await clash_embed(
                context=ctx,
                message=f"Confirmation timed out. Please try again.",
                success=False)
            return await message.edit(content=None,embed=[embed,timeout_embed],view=None)
    
        if not confirm_view.confirmation:
            cancel_embed = await clash_embed(
                context=ctx,
                message=f"Task cancelled.",
                success=False)
            return await message.edit(content=None,embed=[embed,cancel_embed],view=None)

        if confirm_view.confirmation:
            await ClanGuildLink.delete(clan.tag,ctx.guild)
            complete_embed = await clash_embed(
                context=ctx,
                message=f"**{clan.title}** has been unlinked from {ctx.guild.name}.",
                success=True,
                thumbnail=clan.badge)
            return await message.edit(content=None,embed=complete_embed,view=None)

    @appgrp_clan.command(
        name="unlink",
        description="Unlinks a Clan from this Discord Server.")
    @app_commands.check(is_admin)
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan.")
    async def appcmd_clan_unlink(self,interaction:discord.Interaction,clan:str):
        
        await interaction.response.defer()
        
        select_clan = await self.coc_client.get_clan(clan)
        link = await ClanGuildLink.get_link(select_clan.tag,interaction.guild.id)

        if not link:
            embed = await clash_embed(
                context=interaction,
                message=f"**{select_clan.title}** is not linked to {interaction.guild.name}.",
                success=False,
                thumbnail=select_clan.badge)
            return await interaction.edit_original_response(embed=embed,view=None)

        embed = await clash_embed(
            context=interaction,
            title=f"Unink Clan: **{select_clan.title}**",
            message=f"**Co-Leader Role:** {getattr(link.coleader_role,'mention','Not Set')}"
                + f"\n**Elder Role:** {getattr(link.elder_role,'mention','Not Set')}"
                + f"\n**Member Role:** {getattr(link.member_role,'mention','Not Set')}"
                + f"\n**Visitor Role:** {getattr(link.visitor_role,'mention','Not Set')}"
                + f"\n**Clan War Role:** {getattr(link.clan_war_role,'mention','Not Set')}",
            thumbnail=select_clan.badge)
        confirm_view = MenuConfirmation(interaction)

        await interaction.followup.send(
            content=f"{interaction.user.mention}, please confirm the below action.",
            embed=embed,
            view=confirm_view,
            wait=True
            )
        view_timed_out = await confirm_view.wait()

        if view_timed_out:
            timeout_embed = await clash_embed(
                context=interaction,
                message=f"Confirmation timed out. Please try again.",
                success=False)
            return await interaction.edit_original_response(content=None,embeds=[embed,timeout_embed],view=None)
    
        if not confirm_view.confirmation:
            cancel_embed = await clash_embed(
                context=interaction,
                message=f"Task cancelled.",
                success=False)
            return await interaction.edit_original_response(content=None,embeds=[embed,cancel_embed],view=None)

        if confirm_view.confirmation:
            await ClanGuildLink.delete(select_clan.tag,interaction.guild)
            complete_embed = await clash_embed(
                context=interaction,
                message=f"**{select_clan.title}** has been unlinked from {interaction.guild.name}.",
                success=True,
                thumbnail=select_clan.badge)
            return await interaction.edit_original_response(content=None,embed=complete_embed,view=None)
    
    ############################################################
    #####
    ##### COMMAND: CLAN SETLEADER
    #####
    ############################################################
    def check_change_leader(self,guild:discord.Guild,clan:aClan,user_id:int):
        if user_id in self.bot.owner_ids:
            return True
        if user_id == clan.leader:
            return True
        member = guild.get_member(user_id)
        if clan.leader == 0 and member.guild_permissions.administrator:
            return True
        return False
        
    @cmdgroup_clan.command(name="changeleader")
    @commands.guild_only()
    @commands.check(is_admin_or_leader)
    async def subcmd_clan_change_leader(self,ctx:commands.Context,clan_abbreviation:str,new_leader:discord.Member):
        """
        Change the Leader of a registered Clan.

        Only the current Leader, or a Server Admin can use this Command.
        """

        clan = await self.coc_client.from_clan_abbreviation(clan_abbreviation)

        if not self.check_change_leader(ctx.guild,clan,ctx.author.id):
            embed = await clash_embed(
                context=ctx,
                message=f"You do not have permission to change the Leader of **{clan.title}**.",
                success=False,
                )
            return await ctx.reply(embed=embed)
        
        embed = await clash_embed(
            context=ctx,
            title=f"Change Leader: **{clan.title}**",
            message=f"**Current Leader:** " + (f"<@{clan.leader}>" if clan.leader else "None Assigned")
                + f"\n**New Leader:** {new_leader.mention}"
                + f"\n\n{clan.long_description}"
                + f"\n\n>>> {clan.description}",
            thumbnail=clan.badge)
        confirm_view = MenuConfirmation(ctx)

        message = await ctx.reply(
            content=f"{ctx.author.mention}, please confirm the below action.",
            embed=embed,
            view=confirm_view
            )
        view_timed_out = await confirm_view.wait()

        if view_timed_out:
            timeout_embed = await clash_embed(
                context=ctx,
                message=f"Confirmation timed out. Please try again.",
                success=False)
            return await message.edit(content=None,embeds=[embed,timeout_embed],view=None)

        if not confirm_view.confirmation:
            cancel_embed = await clash_embed(
                context=ctx,
                message=f"Task cancelled.",
                success=False)
            return await message.edit(content=None,embeds=[embed,cancel_embed],view=None)
        
        if confirm_view.confirmation:
            await clan.new_leader(new_leader.id)
            complete_embed = await clash_embed(
                context=ctx,
                title=f"Change Leader: **{clan.title}**",
                message=f"New Leader: <@{clan.leader}>"
                    + f"\n\n{clan.long_description}"
                    + f"\n\n>>> {clan.description}",
                url=clan.share_link,
                success=True,
                thumbnail=clan.badge)
            return await message.edit(
                content=None,
                embed=complete_embed,
                view=None
                )

    @appgrp_clan.command(
        name="change-leader",
        description="Change the Leader of a registered Clan.")
    @app_commands.check(is_admin_or_leader)
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan.")
    async def subcmd_clan_change_leader(self,interaction:discord.Interaction,clan:str,new_leader:discord.Member):

        await interaction.response.defer()

        select_clan = await self.coc_client.get_clan(clan)

        if not self.check_change_leader(interaction.guild,select_clan,interaction.user.id):
            embed = await clash_embed(
                context=interaction,
                message=f"You do not have permission to change the Leader of **{clan.title}**.",
                success=False,
                )
            return await interaction.edit_original_response(embed=embed)
        
        embed = await clash_embed(
            context=interaction,
            title=f"Change Leader: **{select_clan.title}**",
            message=f"**Current Leader:** " + (f"<@{clan.leader}>" if clan.leader else "None Assigned")
                + f"\n**New Leader:** {new_leader.mention}"
                + f"\n\n{select_clan.long_description}"
                + f"\n\n>>> {select_clan.description}",
            thumbnail=select_clan.badge)
        confirm_view = MenuConfirmation(interaction)

        await interaction.followup.send(
            content=f"{interaction.user.mention}, please confirm the below action.",
            embed=embed,
            view=confirm_view,
            wait=True
            )        
        view_timed_out = await confirm_view.wait()

        if view_timed_out:
            timeout_embed = await clash_embed(
                context=interaction,
                message=f"Confirmation timed out. Please try again.",
                success=False)            
            return await interaction.edit_original_response(content=None,embeds=[embed,timeout_embed],view=None)

        if not confirm_view.confirmation:
            cancel_embed = await clash_embed(
                context=interaction,
                message=f"Task cancelled.",
                success=False)
            return await interaction.edit_original_response(content=None,embeds=[embed,cancel_embed],view=None)
        
        if confirm_view.confirmation:
            await select_clan.new_leader(new_leader.id)
            complete_embed = await clash_embed(
                context=interaction,
                title=f"Leader Changed: **{select_clan.title}**",
                message=f"New Leader: <@{select_clan.leader}>"
                    + f"\n\n{select_clan.long_description}"
                    + f"\n\n>>> {select_clan.c_description}",
                url=select_clan.share_link,
                success=True,
                thumbnail=select_clan.badge)
            return await interaction.edit_original_response(content=None,embed=complete_embed,view=None)
    
    ############################################################
    #####
    ##### COMMAND: CLAN SETTINGS
    #####
    ############################################################
    @cmdgroup_clan.command(name="settings")
    @commands.guild_only()
    @commands.check(is_admin_or_coleader)
    async def subcmd_clan_settings(self,ctx:commands.Context,clan_tag_or_abbreviation:str):
        """
        Show/change Clan Configuration Options.

        Allows Co-Leaders to set up Recruitment Levels, Custom Clan Descriptions, War/Raid Reminders.
        """

        clan = await self.coc_client.from_clan_abbreviation(clan_tag_or_abbreviation)
        menu = ClanSettingsMenu(ctx,clan)
        await menu.start() 
    
    @appgrp_clan.command(
        name="settings",
        description="Show/change Clan Configuration Options.")
    @app_commands.check(is_admin_or_coleader)
    @app_commands.autocomplete(clan=autocomplete_clan_settings)
    @app_commands.describe(clan="Select a Clan. You must be a Server Admin or Leader/Co-Leader for the Clan.")
    async def app_command_clan_settings(self,interaction:discord.Interaction,clan:str):
        
        await interaction.response.defer()
        get_clan = await self.coc_client.get_clan(clan)
        menu = ClanSettingsMenu(interaction,get_clan)
        await menu.start()
    
    ############################################################
    #####
    ##### COMMAND GROUP: FAMILY
    #####
    ############################################################
    @commands.group(name="family")
    @commands.guild_only()
    async def cmdgroup_family(self,ctx):
        """
        Group for Clan Family-related commands.

        **This is a command group. To use the sub-commands below, follow the syntax: `[p]family [sub-command]`.**
        """
        if not ctx.invoked_subcommand:
            pass

    appgrp_family = app_commands.Group(
        name="family",
        description="Group for Clan Family-related commands. Equivalent to [p]family.",
        guild_only=True
        )    
    
    ############################################################
    #####
    ##### COMMAND: FAMILY CLANS
    #####
    ############################################################    
    async def helper_family_clans(self,context:Union[commands.Context,discord.Interaction],only_server:bool):
        if only_server:
            clan_links = await ClanGuildLink.get_for_guild(context.guild.id)
            embed = await clash_embed(
                context=context,
                title=f"**Linked Clans: {context.guild.name}**"
                )
            
            iter = AsyncIter(clan_links)            
            async for link in iter:
                try:
                    clan = await self.coc_client.get_clan(link.tag)
                except:
                    continue

                embed.add_field(
                    name=f"**{clan.title}**",
                    value=f"Co-Leader Role: {getattr(link.coleader_role,'mention','None')}"
                        + f"\nElder Role: {getattr(link.elder_role,'mention','None')}"
                        + f"\nMember Role: {getattr(link.member_role,'mention','None')}",
                    inline=False
                    )
            return embed

        else:
            clans = await self.coc_client.get_registered_clans()
            a_iter = AsyncIter(clans)
            embed = await clash_embed(
                context=context,
                title=f"**{self.bot.user.name} Registered Clans**",
                message='\n'.join([f"{clan.emoji} {clan.abbreviation} {clan.clean_name} ({clan.tag})" async for clan in a_iter]),
                )
            return embed

    @cmdgroup_family.command(name="clans")
    @commands.guild_only()
    async def subcmd_family_clans(self,ctx:commands.Context,only_server:Optional[bool]=True):
        """
        Displays all Clans registered to the bot.
        """
        embed = await self.helper_family_clans(ctx,only_server)
        await ctx.reply(embed=embed)
        
    @appgrp_clan.command(
        name="clans",
        description="Displays all Clans registered to the bot.")
    @app_commands.describe(only_server="Only show Clans registered to this server.")
    @app_commands.guild_only()
    async def appcmd_family_clan(self,interaction:discord.Interaction,only_server:Optional[bool]=True):

        await interaction.response.defer()
        embed = await self.helper_family_clans(interaction,only_server)
        await interaction.followup.send(embed=embed)