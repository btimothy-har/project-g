import asyncio
import discord
import pendulum
import re
import random

from typing import *
from mongoengine import *

from collections import Counter

from redbot.core import commands, app_commands
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter

from coc_main.api_client import BotClashClient, aClashSeason, ClashOfClansError, InvalidAbbreviation, InvalidRole
from coc_main.cog_coc_client import ClashOfClansClient, aClan, db_Clan, db_AllianceClan, aClanWar, aPlayer

from coc_main.utils.components import clash_embed, MenuConfirmation, ClanLinkMenu
from coc_main.utils.utils import chunks
from coc_main.utils.autocomplete import autocomplete_clans, autocomplete_clans_coleader, autocomplete_seasons
from coc_main.utils.checks import is_admin, is_coleader, is_admin_or_leader, is_admin_or_coleader

from coc_main.utils.constants.coc_emojis import EmojisTownHall, EmojisClash
from coc_main.utils.constants.ui_emojis import EmojisUI

from coc_main.discord.clan_link import db_ClanGuildLink, ClanGuildLink
from coc_main.coc_objects.players.mongo_player import db_PlayerStats

from .views.clan_settings import ClanSettingsMenu
from .views.clan_members import ClanMembersMenu
from .excel.clan_export import ClanExcelExport

from coc_main.discord.feeds.raid_results import RaidResultsFeed

bot_client = BotClashClient()

async def autocomplete_clan_settings(interaction:discord.Interaction,current:str):
    try:
        member = interaction.guild.get_member(interaction.user.id)
        
        if interaction.user.id in interaction.client.owner_ids or member.guild_permissions.administrator:
            return await autocomplete_clans(interaction,current)
        
        else:
            clan_tags = [db.tag for db in db_AllianceClan.objects(Q(coleaders__contains=interaction.user.id) | Q(leader=interaction.user.id))]
            
            if current:
                clans = list(db_Clan.objects(
                    (Q(tag__in=clan_tags)) &
                    (Q(tag__icontains=current) | Q(name__icontains=current) | Q(abbreviation=current.upper()))
                    ))
            else:
                clans = list(db_Clan.objects(tag__in=clan_tags))

            return [
                app_commands.Choice(
                    name=f"{c.name} | {c.tag}",
                    value=c.tag)
                for c in random.sample(clans,min(len(clans),3))
                ]
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_clan_settings")

############################################################
############################################################
#####
##### CLIENT COG
#####
############################################################
############################################################
class Clans(commands.Cog):
    """
    Clan Commands
    """

    __author__ = bot_client.author
    __version__ = bot_client.version

    def __init__(self,bot:Red,version:int):
        self.bot = bot
        self.sub_v = version

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}.{self.sub_v}"
    
    @property
    def bot_client(self) -> BotClashClient:
        return BotClashClient()

    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    async def cog_command_error(self,ctx,error):
        if isinstance(getattr(error,'original',None),ClashOfClansError):
            embed = await clash_embed(
                context=ctx,
                message=f"{error.original.message}",
                success=False,
                timestamp=pendulum.now()
                )
            await ctx.send(embed=embed)
            return
        await self.bot.on_command_error(ctx,error,unhandled_by_cog=True)

    async def cog_app_command_error(self,interaction,error):
        if isinstance(getattr(error,'original',None),ClashOfClansError):
            embed = await clash_embed(
                context=interaction,
                message=f"{error.original.message}",
                success=False,
                timestamp=pendulum.now()
                )
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed,view=None)
            else:
                await interaction.response.send_message(embed=embed,view=None,ephemeral=True)
            return
    
    ##################################################
    ### CLAN ABBREVIATION LISTENER
    ##################################################
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
                found_clans.append(await self.client.from_clan_abbreviation(text))
            except InvalidAbbreviation:
                chk = False
        
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
                        + f"\n\n{clan.c_description}",
                    thumbnail=clan.badge,
                    show_author=False,
                    )
                embeds.append(embed)
            return await message.reply(embeds=embeds,view=view)
    
    ############################################################
    ############################################################
    #####
    ##### COMMAND DIRECTORY
    ##### - Clan / Export
    ##### - Clan / Compo
    ##### - Clan / Strength
    ##### - Clan / Donations
    ##### - Clan / Members
    ##### - Clan / Info
    ##### - Clan-Games
    ##### - ClanData / War Log** [under construction]
    ##### - ClanData / Raid Log** [under construction]
    ##### - ClanSet / Register
    ##### - ClanSet / Delete
    ##### - ClanSet / Link
    ##### - ClanSet / Unlink
    ##### - ClanSet / SetLeader
    ##### - ClanSet / Config    
    #####
    ############################################################
    ############################################################

    ##################################################
    ### PARENT COMMAND GROUPS
    ##################################################
    @commands.group(name="clan")
    @commands.guild_only()
    async def command_group_clan(self,ctx):
        """
        Group for Clan-related commands.

        **This is a command group. To use the sub-commands below, follow the syntax: `$clan [sub-command]`.**
        """
        if not ctx.invoked_subcommand:
            pass

    app_command_group_clan = app_commands.Group(
        name="clan",
        description="Group for Clan Data. Equivalent to [p]clandata.",
        guild_only=True
        )
    
    @commands.group(name="clanset")
    @commands.guild_only()
    async def command_group_clanset(self,ctx):
        """
        Group for Clan Settings.

        **This is a command group. To use the sub-commands below, follow the syntax: `$clanset [sub-command]`.**
        """
        if not ctx.invoked_subcommand:
            pass

    app_command_group_clanset = app_commands.Group(
        name="clan-set",
        description="Group for Clan Settings. Equivalent to [p]clanset.",
        guild_only=True
        )
    
    ##################################################
    ### CLAN FAMILY
    ##################################################
    @commands.command(name="family-clans")
    @commands.guild_only()
    async def command_family_clans(self,ctx:commands.Context):
        """
        Displays all Clans registered to the bot.
        """

        clans = await self.client.get_registered_clans()
        embed = await clash_embed(
            context=ctx,
            title=f"**{ctx.bot.user.name} Registered Clans**",
            message='\n'.join([f"{clan.emoji} {clan.abbreviation} {clan.clean_name} ({clan.tag})" for clan in clans]),
            )        
        await ctx.reply(embed=embed)
        
    @app_commands.command(
        name="family-clans",
        description="Displays all Clans registered to the bot.")
    @app_commands.guild_only()
    async def app_command_find_clan(self,interaction:discord.Interaction):

        await interaction.response.defer()
        clans = await self.client.get_registered_clans()
        embed = await clash_embed(
            context=interaction,
            title=f"**{interaction.client.user.name} Registered Clans**",
            message='\n'.join([f"{clan.emoji} {clan.abbreviation} {clan.clean_name} ({clan.tag})" for clan in clans]),
            )        
        await interaction.edit_original_response(embed=embed)

    ##################################################
    ### FIND-CLAN (ALIAS: CLAN INFO)
    ##################################################
    @commands.command(name="findclan")
    @commands.guild_only()
    async def command_find_clan_123(self,ctx:commands.Context,clan_tag:str):
        """
        Gets information about an in-game Clan.

        This command accepts an in-game Clash Tag. To use Alliance abbreviations, simply use `[p]abbreviation` instead.
        """

        clan = await self.client.fetch_clan(tag=clan_tag)

        if not clan:
            embed = await clash_embed(
            context=ctx,
            message=f"I couldn't find a Clan with the tag `{clan_tag}`.",
            )
            return await ctx.reply(embed=embed)

        view = ClanLinkMenu([clan])
        embed = await clash_embed(
            context=ctx,
            title=f"{clan.title}",
            message=f"{clan.long_description}"
                + (f"\n\n> **Recruiting:** {clan.recruitment_level_emojis}" if clan.is_alliance_clan else "")
                + f"\n\n{clan.c_description}",
            thumbnail=clan.badge,
            show_author=False,
            )
        return await ctx.reply(embed=embed,view=view)
        
    @app_commands.command(
        name="find-clan",
        description="Get information about a Clan.")
    @app_commands.guild_only()
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan or manually enter a Tag.")
    async def app_command_find_clan(self,interaction:discord.Interaction,clan:str):

        await interaction.response.defer()
        get_clan = await self.client.fetch_clan(tag=clan)

        view = ClanLinkMenu([get_clan])
        embed = await clash_embed(
            context=interaction,
            title=f"{get_clan.title}",
            message=f"{get_clan.long_description}"
                + (f"\n\n**Recruiting:** {get_clan.recruitment_level_emojis}" if len(get_clan.recruitment_level) > 0 else "")
                + f"\n\n>>> {get_clan.c_description}",
            thumbnail=get_clan.badge,
            )
        await interaction.edit_original_response(embed=embed,view=view)
    
    @command_group_clan.command(name="info")
    @commands.guild_only()
    async def command_get_clan_information(self,ctx:commands.Context,clan_tag:str):
        """
        Gets information about an in-game Clan.

        This command accepts an in-game Clash Tag. To use Alliance abbreviations, simply use `[p]abbreviation` instead.
        """

        clan = await self.client.fetch_clan(tag=clan_tag)
        if not clan:
            embed = await clash_embed( 
                context=ctx,
                message=f"I couldn't find a Clan with the tag `{clan_tag}`.",
                )
            return await ctx.reply(embed=embed)

        view = ClanLinkMenu([clan])
        embed = await clash_embed(
            context=ctx,
            title=f"{clan.title}",
            message=f"{clan.long_description}"
                + (f"\n\n> **Recruiting:** {clan.recruitment_level_emojis}" if clan.is_alliance_clan else "")
                + f"\n\n{clan.c_description}",
            thumbnail=clan.badge,
            show_author=False,
            )
        return await ctx.reply(embed=embed,view=view)
        
    @app_command_group_clan.command(
        name="info",
        description="Get information about a Clan.")
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan or manually enter a Tag.")
    async def app_command_clan_information(self,interaction:discord.Interaction,clan:str):

        await interaction.response.defer()
        get_clan = await self.client.fetch_clan(tag=clan)

        view = ClanLinkMenu([get_clan])
        embed = await clash_embed(
            context=interaction,
            title=f"{get_clan.title}",
            message=f"{get_clan.long_description}"
                + (f"\n\n**Recruiting:** {get_clan.recruitment_level_emojis}" if len(get_clan.recruitment_level) > 0 else "")
                + f"\n\n>>> {get_clan.c_description}",
            thumbnail=get_clan.badge,
            )
        await interaction.edit_original_response(embed=embed,view=view)
    
    ##################################################
    ### CLANDATA / EXPORT
    ##################################################
    @command_group_clan.command(name="export")
    @commands.guild_only()
    @commands.check(is_coleader)
    async def command_export_clan_data(self,ctx:commands.Context,clan_tag_or_abbreviation:str):
        """
        Exports a Clan's data to Excel.

        Only usable for Alliance clans. Defaults to current season. To export for different seasons, use the Slash command.
        """

        try:
            clan = await self.client.from_clan_abbreviation(clan_tag_or_abbreviation)
        except InvalidAbbreviation:
            clan = await self.client.fetch_clan(clan_tag_or_abbreviation)
        
        if not clan:
            embed = await clash_embed(
                context=ctx,
                message=f"I couldn't find a Clan with the input `{clan_tag_or_abbreviation}`.",
                success=False,
                )
            return await ctx.reply(embed=embed)

        if not clan.is_alliance_clan:
            embed = await clash_embed(
                context=ctx,
                message=f"Only Alliance Clans can be exported.",
                success=False,
                )
            return await ctx.reply(embed=embed)        

        wait_msg = await ctx.reply("Exporting Clan Data... please wait.")
        
        season = self.bot_client.current_season
        rp_file = await ClanExcelExport.generate_report(clan,season)

        await wait_msg.delete()
        await ctx.reply(
            content=f"Here is the Clan data for {clan} as you requested.",
            file=discord.File(rp_file))
        

    @app_command_group_clan.command(name="export",
        description="Export seasonal Clan Data to an Excel file.")
    @app_commands.check(is_coleader)
    @app_commands.autocomplete(
        clan=autocomplete_clans_coleader,
        season=autocomplete_seasons)
    @app_commands.describe(
        clan="Select a Clan. Only Alliance Clans can be selected.",
        season="Select a Season to export.")
    async def app_command_clan_export(self,interaction:discord.Interaction,clan:str,season:str):  
        
        await interaction.response.defer()
        
        get_clan = await self.client.fetch_clan(clan)
        if not clan.is_alliance_clan:
            embed = await clash_embed(
                context=interaction,
                message=f"Only Alliance Clans can be exported.",
                success=False,
                )
            return await interaction.edit_original_response(embed=embed)
        
        season = aClashSeason(season)
        rp_file = await ClanExcelExport.generate_report(get_clan,season)

        await interaction.followup.send(
            content=f"Here is the Clan data for {get_clan} as you requested.",
            file=discord.File(rp_file))
    
    ##################################################
    ### CLANDATA / COMPO
    ##################################################
    @command_group_clan.command(name="compo")
    @commands.guild_only()
    async def command_clan_composition(self,ctx:commands.Context,clan_tag_or_abbreviation:str):
        """
        View a Clan's Town Hall composition.

        For registered Alliance clans, returns registered and in-game compositions.
        """
     
        try:
            clan = await self.client.from_clan_abbreviation(clan_tag_or_abbreviation)
        except InvalidAbbreviation:
            clan = await self.client.fetch_clan(clan_tag_or_abbreviation)
        
        if not clan:
            embed = await clash_embed(
                context=ctx,
                message=f"I couldn't find a Clan with the input `{clan_tag_or_abbreviation}`.",
                success=False,
                )
            return await ctx.reply(embed=embed)
        
        embed = await self.clan_composition_embed(ctx,clan)            
        return await ctx.reply(embed=embed)

    @app_command_group_clan.command(
        name="compo",
        description="View a Clan's Townhall composition.")
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan.")
    async def app_command_clan_composition(self,interaction:discord.Interaction,clan:str):

        await interaction.response.defer()

        get_clan = await self.client.fetch_clan(clan)
        if not get_clan:
            embed = await clash_embed(
                context=interaction,
                message=f"I couldn't find a Clan with the input `{clan}`.",
                success=False,
                )
            return await interaction.edit_original_response(embed=embed)
        
        embed = await self.clan_composition_embed(interaction,get_clan)
        return await interaction.edit_original_response(embed=embed)

    ##################################################
    ### CLANDATA / STRENGTH
    ##################################################
    @command_group_clan.command(name="strength")
    @commands.guild_only()
    async def subcommand_clan_strength(self,ctx:commands.Context,clan_tag_or_abbreviation:str):
        """
        View a Clan's overall Offensive Strength.

        For registered Alliance clans, returns only registered members.
        """

        try:
            clan = await self.client.from_clan_abbreviation(clan_tag_or_abbreviation)
        except InvalidAbbreviation:
            clan = await self.client.fetch_clan(clan_tag_or_abbreviation)
        
        if not clan:
            embed = await clash_embed(
                context=ctx,
                message=f"I couldn't find a Clan with the input `{clan_tag_or_abbreviation}`.",
                success=False,
                )
            return await ctx.reply(embed=embed)

        embed = await self.clan_strength_embed(ctx,clan)
        return await ctx.reply(embed=embed)
    
    @app_command_group_clan.command(
        name="strength",
        description="View a Clan's Offensive strength.")
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan.")
    async def app_command_clan_strength(self,interaction:discord.Interaction,clan:str):

        await interaction.response.defer()

        get_clan = await self.client.fetch_clan(clan)
        if not get_clan:
            embed = await clash_embed(
                context=interaction,
                message=f"I couldn't find a Clan with the input `{clan}`.",
                success=False,
                )
            return await interaction.edit_original_response(embed=embed)            

        embed = await self.clan_strength_embed(interaction,get_clan)
        return await interaction.edit_original_response(embed=embed)

    ##################################################
    ### CLANDATA / DONATIONS
    ##################################################
    @command_group_clan.command(name="donations")
    @commands.guild_only()
    async def subcommand_clan_donations(self,ctx:commands.Context,clan_tag_or_abbreviation:str):
        """
        View a Clan's Donation Stats for the current season.

        For registered Alliance Clans, this will retrieve stats for registered members. For all other clans, this will return what is available via in-game.
        """
        
        try:
            clan = await self.client.from_clan_abbreviation(clan_tag_or_abbreviation)
        except InvalidAbbreviation:
            clan = await self.client.fetch_clan(clan_tag_or_abbreviation)
        
        if not clan:
            embed = await clash_embed(
                context=ctx,
                message=f"I couldn't find a Clan with the input `{clan_tag_or_abbreviation}`.",
                success=False,
                )
            return await ctx.reply(embed=embed)
        
        embed = await self.clan_donations_embed(ctx,clan)
        await ctx.reply(embed=embed)
    
    @app_command_group_clan.command(name="donations",
        description="View a Clan's Donation stats.")
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan.")
    async def app_command_clanstats_donations(self,interaction:discord.Interaction,clan:str):
   
        await interaction.response.defer()

        get_clan = await self.client.fetch_clan(clan)
        if not get_clan:
            embed = await clash_embed(
                context=interaction,
                message=f"I couldn't find a Clan with the input `{clan}`.",
                success=False,
                )
            return await interaction.edit_original_response(embed=embed)
        
        embed = await self.clan_donations_embed(interaction,get_clan)
        await interaction.edit_original_response(embed=embed)
    
    ##################################################
    ### CLAN / MEMBERS
    ##################################################
    @command_group_clan.command(name="members")
    @commands.guild_only()
    async def subcommand_clan_membersummary(self,ctx:commands.Context,clan_tag_or_abbreviation:str):
        """
        Display info on a Clan's Members.

        Contains menus for Discord Links, Rank Status, and War Opt-Ins.

        By default, this shows all in-game members. For Alliance Clans, this will also return registered members who are not in the in-game clan.
        """
  
        try:
            clan = await self.client.from_clan_abbreviation(clan_tag_or_abbreviation)
        except InvalidAbbreviation:
            clan = await self.client.fetch_clan(clan_tag_or_abbreviation)

        if not clan:
            embed = await clash_embed(
                context=ctx,
                message=f"I couldn't find a Clan with the input `{clan_tag_or_abbreviation}`.",
                success=False,
                )
            return await ctx.reply(embed=embed)
        
        menu = ClanMembersMenu(ctx,clan)
        await menu.start()

    @app_command_group_clan.command(name="members",
        description="View Clan Member information.")
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(
        clan="Select a Clan.") 
    async def app_command_clan_membersummary(self,interaction:discord.Interaction,clan:str):

        await interaction.response.defer()

        get_clan = await self.client.fetch_clan(clan)
        if not clan:
            embed = await clash_embed(
                context=interaction,
                message=f"I couldn't find a Clan with the input `{clan}`.",
                success=False,
                )
            return await interaction.edit_original_response(embed=embed)

        menu = ClanMembersMenu(interaction,get_clan)
        await menu.start()
    
    ##################################################
    ### CLAN GAMES
    ##################################################
    @commands.command(name="clangames",aliases=["cg"])
    @commands.guild_only()
    async def command_clan_games(self,ctx:commands.Context,clan_tag_or_abbreviation:str):
        """
        View the Clan Games leaderboard for a Clan.

        Defaults to the last completed Clan Games. If viewing non-Alliance clans, data may not be completed.
        """
  
        try:
            clan = await self.client.from_clan_abbreviation(clan_tag_or_abbreviation)
        except InvalidAbbreviation:
            clan = await self.client.fetch_clan(clan_tag_or_abbreviation)

        if not clan:
            embed = await clash_embed(
                context=ctx,
                message=f"I couldn't find a Clan with the input `{clan_tag_or_abbreviation}`.",
                success=False,
                )
            return await ctx.reply(embed=embed)

        embed = await self.clan_games_data(ctx,clan,aClashSeason.last_completed_clangames())
        await ctx.reply(embed=embed)

    @app_commands.command(name="clan-games",
        description="View Clan Games information. Defaults to the last completed Clan Games.")
    @app_commands.autocomplete(
        clan=autocomplete_clans,
        season=autocomplete_seasons)
    @app_commands.describe(
        clan="Select a Clan. If viewing non-Alliance clans, data may not be completed.",
        season="Select a Season to view for.")
    async def app_command_clan_games(self,interaction:discord.Interaction,clan:str,season:str):

        await interaction.response.defer()

        clan = await self.client.fetch_clan(clan)
        if not clan:
            embed = await clash_embed(
                context=interaction,
                message=f"I couldn't find a Clan with the input `{clan}`.",
                success=False,
                )
            return await interaction.edit_original_response(embed=embed)

        embed = await self.clan_games_data(interaction,clan,aClashSeason.last_completed_clangames())
        await interaction.edit_original_response(embed=embed)
    
    ##################################################
    ### CLANSET / REGISTER
    ##################################################
    async def helper_register_clan(self,
        context:Union[commands.Context,discord.Interaction],
        clan_tag:str,
        emoji:str,
        unicode_emoji:str,
        abbreviation:str):

        clan = await self.client.fetch_clan(clan_tag)
        clan.abbreviation = abbreviation
        clan.emoji = emoji
        clan.unicode_emoji = unicode_emoji

        embed = await clash_embed(
            context=context,
            title=f"Registered: {clan.title}",
            message=clan.long_description,
            thumbnail=clan.badge,
            success=True
            )
        return embed

    @command_group_clanset.command(name="register")
    @commands.guild_only()
    @commands.admin()
    async def subcommand_register_clan(self,ctx:commands.Context,clan_tag:str,emoji:str,unicode_emoji:str,abbreviation:str):
        """
        [Admin-only] Register an in-game Clan to the bot.

        Assigns:
        > - Clan Emoji
        > - Clan Abbreviation
        """
        
        embed = await self.helper_register_clan(ctx,clan_tag,emoji,unicode_emoji,abbreviation)
        await ctx.reply(embed=embed)
    
    @app_command_group_clanset.command(
        name="register",
        description="[Admin-only] Register an in-game Clan to the bot.")
    @app_commands.check(is_admin)
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(
        clan="Select a Clan, or enter a Clan Tag.",
        emoji="Provide the Emoji to use for the Clan.",
        unicode_emoji="Provide the Unicode Emoji to use for the Clan.",
        abbreviation="Provide the Clan's abbreviation.")
    async def app_subcommand_register_clan(self,interaction:discord.Interaction,
        clan:str,
        emoji:str,
        unicode_emoji:str,
        abbreviation:str):
        
        await interaction.response.defer()
        embed = await self.helper_register_clan(interaction,clan,emoji,unicode_emoji,abbreviation)
        await interaction.followup.send(embed=embed)
    
    ##################################################
    ### CLANSET / LINK
    ##################################################
    @command_group_clanset.command(name="link")
    @commands.guild_only()
    @commands.admin()
    async def subcommand_link_clan(self,ctx:commands.Context,clan_tag:str,coleader_role_id:int,elder_role_id:int,member_role_id:int):
        """
        [Admin-only] Links a Clan to this Discord Server.

        Linked Clans have linked Discord Roles, and will be synced based on membership status.
        > - Co-Leader Role
        > - Elder Role
        > - Member Role
        """
        
        clan = await self.client.fetch_clan(clan_tag)

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
            message=f"**Co-Leader Role:** {coleader_role.mention}"
                + f"\n**Elder Role:** {elder_role.mention}"
                + f"\n**Member Role:** {member_role.mention}",
            thumbnail=clan.badge)
        confirm_view = MenuConfirmation(ctx)
        
        message = await ctx.reply(
            message=f"{ctx.author.mention}, please confirm the below action.",
            embed=embed,
            view=confirm_view
            )        
        view_timed_out = await confirm_view.wait()

        if view_timed_out:
            timeout_embed = await clash_embed(
                context=ctx,
                message=f"Confirmation timed out. Please try again.",
                success=False)
            return await message.edit(embed=[embed,timeout_embed],view=None)
    
        if not confirm_view.confirmation:
            cancel_embed = await clash_embed(
                context=ctx,
                message=f"Task cancelled.",
                success=False)
            return await message.edit(embed=[embed,cancel_embed],view=None)

        if confirm_view.confirmation:
            await ClanGuildLink.create(
                clan_tag=clan.tag,
                guild=ctx.guild,
                member_role=member_role,
                elder_role=elder_role,
                coleader_role=coleader_role
                )            
            complete_embed = await clash_embed(
                context=ctx,
                title=f"Link Clan: **{clan.title}**",
                message=f"**Co-Leader Role:** {coleader_role.mention}"
                    + f"\n**Elder Role:** {elder_role.mention}"
                    + f"\n**Member Role:** {member_role.mention}",
                url=clan.share_link,
                success=True,
                thumbnail=clan.badge)
            return await message.edit(embed=complete_embed,view=None)

    @app_command_group_clanset.command(
        name="link",
        description="[Admin-only] Links a Clan to this Discord Server.")
    @app_commands.check(is_admin)
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan.")
    async def app_subcommand_link_clan(self,interaction:discord.Interaction,
        clan:str,
        coleader_role:discord.Role,
        elder_role:discord.Role,
        member_role:discord.Role):
        
        await interaction.response.defer()
        
        select_clan = await self.client.fetch_clan(clan)
        embed = await clash_embed(
            context=interaction,
            title=f"Link Clan: **{select_clan.title}**",
            message=f"**Co-Leader Role:** {coleader_role.mention}"
                + f"\n**Elder Role:** {elder_role.mention}"
                + f"\n**Member Role:** {member_role.mention}",
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
            return await interaction.edit_original_response(embeds=[embed,timeout_embed],view=None)
    
        if not confirm_view.confirmation:
            cancel_embed = await clash_embed(
                context=interaction,
                message=f"Task cancelled.",
                success=False)
            return await interaction.edit_original_response(embeds=[embed,cancel_embed],view=None)

        if confirm_view.confirmation:
            await ClanGuildLink.create(
                clan_tag=select_clan.tag,
                guild=interaction.guild,
                member_role=member_role,
                elder_role=elder_role,
                coleader_role=coleader_role
                )            
            complete_embed = await clash_embed(
                context=interaction,
                title=f"Link Clan: **{select_clan.title}**",
                message=f"**Co-Leader Role:** {coleader_role.mention}"
                    + f"\n**Elder Role:** {elder_role.mention}"
                    + f"\n**Member Role:** {member_role.mention}",
                url=select_clan.share_link,
                success=True,
                thumbnail=select_clan.badge)
            return await interaction.edit_original_response(embed=complete_embed,view=None)
    
    ##################################################
    ### CLANSET / UNLINK
    ##################################################
    @command_group_clanset.command(name="unlink")
    @commands.guild_only()
    @commands.admin()
    async def subcommand_link_clan(self,ctx:commands.Context,clan_tag:str):
        """
        [Admin-only] Unlinks a Clan from this Discord Server.
        """
        clan = await self.client.fetch_clan(clan_tag)
        link = ClanGuildLink.get_link(clan_tag,ctx.guild.id)
        
        embed = await clash_embed(
            context=ctx,
            title=f"Unlink Clan: **{clan.title}**",
            message=f"**Co-Leader Role:** {link.coleader_role.mention}"
                + f"\n**Elder Role:** {link.elder_role.mention}"
                + f"\n**Member Role:** {link.member_role.mention}",
            thumbnail=clan.badge)
        confirm_view = MenuConfirmation(ctx)
        
        message = await ctx.reply(
            message=f"{ctx.author.mention}, please confirm the below action.",
            embed=embed,
            view=confirm_view
            )        
        view_timed_out = await confirm_view.wait()

        if view_timed_out:
            timeout_embed = await clash_embed(
                context=ctx,
                message=f"Confirmation timed out. Please try again.",
                success=False)
            return await message.edit(embed=[embed,timeout_embed],view=None)
    
        if not confirm_view.confirmation:
            cancel_embed = await clash_embed(
                context=ctx,
                message=f"Task cancelled.",
                success=False)
            return await message.edit(embed=[embed,cancel_embed],view=None)

        if confirm_view.confirmation:
            await ClanGuildLink.delete(clan.tag,ctx.guild)
            complete_embed = await clash_embed(
                context=ctx,
                message=f"**{clan.title}** has been unlinked from {ctx.guild.name}.",
                success=True,
                thumbnail=clan.badge)
            return await message.edit(embed=complete_embed,view=None)

    @app_command_group_clanset.command(
        name="unlink",
        description="[Admin-only] Unlinks a Clan from this Discord Server.")
    @app_commands.check(is_admin)
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan.")
    async def app_subcommand_link_clan(self,interaction:discord.Interaction,clan:str):
        
        await interaction.response.defer()
        
        select_clan = await self.client.fetch_clan(clan)
        link = ClanGuildLink.get_link(select_clan.tag,interaction.guild.id)

        if not link:
            embed = await clash_embed(
                context=interaction,
                message=f"**{select_clan.title}** is not linked to {interaction.guild.name}.",
                success=False,
                thumbnail=select_clan.badge)
            return await interaction.edit_original_response(embed=embed,view=None)

        embed = await clash_embed(
            context=interaction,
            title=f"Link Clan: **{select_clan.title}**",
            message=f"**Co-Leader Role:** {link.coleader_role.mention}"
                + f"\n**Elder Role:** {link.elder_role.mention}"
                + f"\n**Member Role:** {link.member_role.mention}",
            thumbnail=select_clan.badge)
        confirm_view = MenuConfirmation(interaction)

        await interaction.followup.send(
            message=f"{interaction.user.mention}, please confirm the below action.",
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
            return await interaction.edit_original_response(embeds=[embed,timeout_embed],view=None)
    
        if not confirm_view.confirmation:
            cancel_embed = await clash_embed(
                context=interaction,
                message=f"Task cancelled.",
                success=False)
            return await interaction.edit_original_response(embeds=[embed,cancel_embed],view=None)

        if confirm_view.confirmation:
            await ClanGuildLink.delete(select_clan.tag,interaction.guild)
            complete_embed = await clash_embed(
                context=interaction,
                message=f"**{select_clan.title}** has been unlinked from {interaction.guild.name}.",
                success=True,
                thumbnail=select_clan.badge)
            return await interaction.edit_original_response(embed=complete_embed,view=None)
    
    ##################################################
    ### CLANSET / SETLEADER
    ##################################################
    def check_change_leader(self,guild:discord.Guild,clan:aClan,user_id:int):
        if user_id in self.bot.owner_ids:
            return True
        if user_id == clan.leader:
            return True
        member = guild.get_member(user_id)
        if clan.leader == 0 and member.guild_permissions.administrator:
            return True
        return False
        
    @command_group_clanset.command(name="leader")
    @commands.guild_only()
    @commands.check(is_admin_or_leader)
    async def subcommand_change_clan_leader(self,ctx:commands.Context,clan_abbreviation:str,new_leader:discord.Member):
        """
        Change the Leader of a registered Clan.

        Only the current Leader, or a Server Admin can use this Command.
        """

        clan = await self.client.from_clan_abbreviation(clan_abbreviation)

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
            message=f"**Current Leader:** <@{clan.leader}>"
                + f"\n**New Leader:** {new_leader.mention}"
                + f"\n\n{clan.long_description}"
                + f"\n\n>>> {clan.c_description}",
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
            return await message.edit(embeds=[embed,timeout_embed],view=None)

        if not confirm_view.confirmation:
            cancel_embed = await clash_embed(
                context=ctx,
                message=f"Task cancelled.",
                success=False)
            return await message.edit(embeds=[embed,cancel_embed],view=None)
        
        if confirm_view.confirmation:
            await clan.new_leader(new_leader.id)
            complete_embed = await clash_embed(
                context=ctx,
                title=f"Change Leader: **{clan.title}**",
                message=f"Leader: <@{clan.leader}>"
                    + f"\n\n{clan.long_description}"
                    + f"\n\n>>> {clan.c_description}",
                url=clan.share_link,
                success=True,
                thumbnail=clan.badge)
            return await message.edit(embed=complete_embed,view=None)

    @app_command_group_clanset.command(
        name="leader",
        description="[Admin-only] Change the Leader of a registered Clan.")
    @app_commands.check(is_admin_or_leader)
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan.")
    async def app_subcommand_link_clan(self,interaction:discord.Interaction,clan:str,new_leader:discord.Member):

        await interaction.response.defer()

        select_clan = await self.client.fetch_clan(clan)

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
            message=f"**Current Leader:** <@{select_clan.leader}>"
                + f"\n**New Leader:** {new_leader.mention}"
                + f"\n\n{select_clan.long_description}"
                + f"\n\n>>> {select_clan.c_description}",
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
            return await interaction.edit_original_response(embeds=[embed,timeout_embed],view=None)

        if not confirm_view.confirmation:
            cancel_embed = await clash_embed(
                context=interaction,
                message=f"Task cancelled.",
                success=False)
            return await interaction.edit_original_response(embeds=[embed,cancel_embed],view=None)
        
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
    
    ##################################################
    ### CLANSET / CONFIG
    ##################################################
    @command_group_clanset.command(name="config")
    @commands.guild_only()
    @commands.check(is_admin_or_coleader)
    async def subcommand_change_clan_config(self,ctx:commands.Context,clan_tag_or_abbreviation:str):
        """
        [Admin or Co-Leaders] Show/change Clan Configuration Options.

        Allows Co-Leaders to set up Recruitment Levels, Custom Clan Descriptions, War/Raid Reminders.
        """

        try:
            clan = await self.client.from_clan_abbreviation(clan_tag_or_abbreviation)
        except InvalidAbbreviation:
            clan = await self.client.fetch_clan(clan_tag_or_abbreviation)
        menu = ClanSettingsMenu(ctx,clan)
        await menu.start() 
    
    @app_command_group_clanset.command(
        name="config",
        description="[Admin or Co-Leaders] Show/change Clan Configuration Options.")
    @app_commands.check(is_admin_or_coleader)
    @app_commands.autocomplete(clan=autocomplete_clan_settings)
    @app_commands.describe(clan="Select a Clan. You must be a Server Admin or Leader/Co-Leader for the Clan.")
    async def app_command_clan_settings(self,interaction:discord.Interaction,clan:str):
        
        await interaction.response.defer()
        get_clan = await self.client.fetch_clan(clan)
        menu = ClanSettingsMenu(interaction,get_clan)
        await menu.start()
    
    async def clan_composition_embed(self,context:Union[commands.Context,discord.Interaction],clan:aClan):
        embed = await clash_embed(
            context=context,
            title=f"{clan.title}",
            message=f"**Clan Member Composition**",
            thumbnail=clan.badge,
            )            
        get_members = await asyncio.gather(*(self.client.fetch_player(member.tag) for member in clan.members),return_exceptions=True)
        ingame_members = [member for member in get_members if isinstance(member,aPlayer)]

        if clan.is_alliance_clan and clan.alliance_member_count > 0:
            get_members = await asyncio.gather(*(self.client.fetch_player(m) for m in clan.alliance_members),return_exceptions=True)
            clan_members = [member for member in get_members if isinstance(member,aPlayer)]
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

    async def clan_strength_embed(self,context:Union[commands.Context,discord.Interaction],clan:aClan):
        if clan.is_alliance_clan and clan.alliance_member_count > 0:
            showing_registered = True
            clan_members = await asyncio.gather(*(self.client.fetch_player(m) for m in clan.alliance_members))
        else:
            showing_registered = False
            clan_members = await asyncio.gather(*(self.client.fetch_player(member.tag) for member in clan.members))
        
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
            chunked_members = list(chunks(th_members,10))

            for i, members_chunk in enumerate(chunked_members):
                embed.add_field(
                    name=f"{EmojisTownHall.get(th)} **TH{th}**"
                        + (f" - ({i+1}/{len(chunked_members)})" if len(chunked_members) > 1 else ""),
                    value="\n".join([
                        f"`"
                        + (f"{getattr(member.get_hero('Barbarian King'),'level',''):^2}{'':^2}" if member.town_hall.level >= 7 else f"{'':^4}")
                        + (f"{getattr(member.get_hero('Archer Queen'),'level',''):^2}{'':^2}" if member.town_hall.level >= 9 else f"{'':^4}")
                        + (f"{getattr(member.get_hero('Grand Warden'),'level',''):^2}{'':^2}" if member.town_hall.level >= 11 else f"{'':^4}")
                        + (f"{getattr(member.get_hero('Royal Champion'),'level',''):^2}{'':^2}" if member.town_hall.level >= 13 else f"{'':^4}")
                        + f"{str(round((member.troop_strength / member.max_troop_strength)*100))+'%':>7}{'':^2}"
                        + (f"{str(round((member.spell_strength / member.max_spell_strength)*100))+'%':>7}" if member.max_spell_strength > 0 else f"{'':>7}")
                        + f"{'':^2}`\u3000{re.sub('[_*/]','',member.clean_name)}"
                        + (f" {EmojisUI.LOGOUT}" if clan.is_alliance_clan and member.tag not in clan.members_dict else "")
                        for member in members_chunk
                        ]),
                    inline=False,
                    )
        return embed

    async def clan_donations_embed(self,context:Union[commands.Context,discord.Interaction],clan:aClan):
        if clan.is_alliance_clan and clan.alliance_member_count > 0:
            clan_members = await asyncio.gather(*(self.client.fetch_player(m) for m in clan.alliance_members))
            clan_members.sort(key=lambda member: member.current_season.donations_sent.alliance_only,reverse=True)

            stats_text = "\n".join([
                f"`{member.current_season.donations_sent.alliance_only:>6}{'':^2}"
                + f"{member.current_season.donations_rcvd.alliance_only:>6}{'':^2}`"
                + f"\u3000{EmojisTownHall.get(member.town_hall.level)} {re.sub('[_*/]','',member.name)}"
                for member in clan_members])

            embed = await clash_embed(
                context=context,
                title=f"{clan.title}: Donations",
                message=f"**Showing stats for: {self.bot_client.current_season.description}**\n\n"
                    + f"{EmojisClash.DONATIONSOUT} Total Sent: {sum(member.current_season.donations_sent.season_only_clan for member in clan_members):,}\u3000|\u3000"
                    + f"{EmojisClash.DONATIONSRCVD} Total Received: {sum(member.current_season.donations_rcvd.season_only_clan for member in clan_members):,}\n\n"
                    + f"`{'SENT':>6}{'':^2}{'RCVD':>6}{'':^2}`\n"
                    + stats_text,
                thumbnail=clan.badge,
                )    
        else:
            clan_members = await asyncio.gather(*(self.client.fetch_player(member.tag) for member in clan.members))
            clan_members.sort(key=lambda member: member.donations,reverse=True)

            stats_text = "\n".join([
                f"`{member.donations:>6}{'':^2}"
                + f"{member.received:>6}{'':^2}`"
                + f"\u3000{EmojisTownHall.get(member.town_hall.level)} {re.sub('[_*/]','',member.name)}"
                for member in clan_members])

            embed = await clash_embed(
                context=context,
                title=f"{clan.title}: Donations",
                message=f"{EmojisClash.DONATIONSOUT} Total Sent: {sum(member.donations for member in clan_members):,}\u3000|\u3000"
                    + f"{EmojisClash.DONATIONSRCVD} Total Received: {sum(member.received for member in clan_members):,}\n\n"
                    + f"`{'SENT':>6}{'':^2}{'RCVD':>6}{'':^2}`\n"
                    + stats_text,
                thumbnail=clan.badge,
                )
        return embed

    async def clan_games_data(self,context:Union[commands.Context,discord.Interaction],clan:aClan,season:aClashSeason):
        query = db_PlayerStats.objects(
            season=season.id,
            clangames__clan=clan.tag,
            clangames__score__gt=0
            ).only('tag')
        
        players = await asyncio.gather(*(self.fetch_player(p.tag) for p in query))

        embed = await clash_embed(
            context=context,
            title=f"{clan.title}: Clan Games",
            message=f"**Showing stats for: {season.description}**\n\n"
                + f"{EmojisUI.MEMBERS} Total Participants: {len(players)}\n"
                + f"{EmojisClash.CLANGAMES} Total Score: {sum([p.clangames.score for p in players]):,}\n\n"
                + f"*{EmojisUI.LOGOUT} denotes a member who is not registered to this Clan.*\n"
                + f"`{'':<3}{'Score':>6}{'Time':>13}{'':<2}`\n"
                + f"\n".join([
                    f"`{i+1:<3}{p.clangames.score:>6,}{'':>2}{p.clangames.time_to_completion:>13}`\u3000{EmojisUI.LOGOUT if p.home_clan_tag != clan.tag else EmojisUI.SPACER}{EmojisTownHall.get(p.town_hall)} {re.sub('[_*/]','',p.name)}"
                    for i, p in enumerate(players)
                    ]),
            thumbnail=clan.badge,
            )
        return embed