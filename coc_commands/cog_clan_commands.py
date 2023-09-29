import discord
import logging

from redbot.core import commands, app_commands
from redbot.core.utils import AsyncIter

from coc_client.exceptions import ClashOfClansError

from coc_data.objects.clans.clan import aClan
from coc_data.objects.discord.clan_link import ClanGuildLink
from coc_data.objects.season.season import aClashSeason

from coc_data.utilities.utils import *
from coc_data.utilities.components import *
from coc_data.exceptions import *

from .views.clan_settings import ClanSettingsMenu
from .views.clan_members import ClanMembersMenu
from .excel.clan_export import ClanExcelExport

from .data_embeds import *

from .helpers.checks import *
from .helpers.autocomplete import *
from .helpers.components import *

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

    __author__ = "bakkutteh"
    __version__ = "1.0.1"

    def __init__(self,bot):        
        self.bot = bot

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"

    @property
    def client(self):
        return self.bot.get_cog("ClashOfClansClient").client
    
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
                found_clans.append(await aClan.from_abbreviation(text))
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
    ##### - Clan
    ##### - Clan-Export
    ##### - Clan-Compo
    ##### - Clan-Strength
    ##### - Clan-Donations
    ##### - Clan-Members
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
    ### FIND-CLAN (ALIAS: CLAN INFO)
    ##################################################
    @commands.command(name="findclan")
    @commands.guild_only()
    async def command_find_clan(self,ctx:commands.Context,clan_tag:str):
        """
        Gets information about an in-game Clan.

        This command accepts an in-game Clash Tag. To use Alliance abbreviations, simply use `[p]abbreviation` instead.
        """

        clan = await aClan.create(clan_tag)

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
        clan = await aClan.create(clan)

        view = ClanLinkMenu([clan])
        embed = await clash_embed(
            context=interaction,
            title=f"{clan.title}",
            message=f"{clan.long_description}"
                + (f"\n\n**Recruiting:** {clan.recruitment_level_emojis}" if len(clan.recruitment_level) > 0 else "")
                + f"\n\n>>> {clan.c_description}",
            thumbnail=clan.badge,
            )
        await interaction.edit_original_response(embed=embed,view=view)
    
    @command_group_clan.command(name="info")
    @commands.guild_only()
    async def command_get_clan_information(self,ctx:commands.Context,clan_tag:str):
        """
        Gets information about an in-game Clan.

        This command accepts an in-game Clash Tag. To use Alliance abbreviations, simply use `[p]abbreviation` instead.
        """

        clan = await aClan.create(clan_tag)

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
        clan = await aClan.create(clan)

        view = ClanLinkMenu([clan])
        embed = await clash_embed(
            context=interaction,
            title=f"{clan.title}",
            message=f"{clan.long_description}"
                + (f"\n\n**Recruiting:** {clan.recruitment_level_emojis}" if len(clan.recruitment_level) > 0 else "")
                + f"\n\n>>> {clan.c_description}",
            thumbnail=clan.badge,
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
            clan = await aClan.from_abbreviation(clan_tag_or_abbreviation)
        except InvalidAbbreviation:
            clan = await aClan.create(clan_tag_or_abbreviation)
        
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
        
        season = self.client.cog.current_season
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
        
        clan = await aClan.create(clan)
        if not clan.is_alliance_clan:
            embed = await clash_embed(
                context=interaction,
                message=f"Only Alliance Clans can be exported.",
                success=False,
                )
            return await interaction.edit_original_response(embed=embed)
        
        season = aClashSeason(season)
        rp_file = await ClanExcelExport.generate_report(clan,season)

        await interaction.followup.send(
            content=f"Here is the Clan data for {clan} as you requested.",
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
            clan = await aClan.from_abbreviation(clan_tag_or_abbreviation)
        except InvalidAbbreviation:
            clan = await aClan.create(clan_tag_or_abbreviation)
        
        if not clan:
            embed = await clash_embed(
                context=ctx,
                message=f"I couldn't find a Clan with the input `{clan_tag_or_abbreviation}`.",
                success=False,
                )
            return await ctx.reply(embed=embed)
        
        embed = await clan_composition_embed(ctx,clan)            
        return await ctx.reply(embed=embed)

    @app_command_group_clan.command(
        name="compo",
        description="View a Clan's Townhall composition.")
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan.")
    async def app_command_clan_composition(self,interaction:discord.Interaction,clan:str):

        await interaction.response.defer()

        clan = await aClan.create(clan)
        if not clan:
            embed = await clash_embed(
                context=interaction,
                message=f"I couldn't find a Clan with the input `{clan}`.",
                success=False,
                )
            return await interaction.edit_original_response(embed=embed)
        
        embed = await clan_composition_embed(interaction,clan)
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
            clan = await aClan.from_abbreviation(clan_tag_or_abbreviation)
        except InvalidAbbreviation:
            clan = await aClan.create(clan_tag_or_abbreviation)
        
        if not clan:
            embed = await clash_embed(
                context=ctx,
                message=f"I couldn't find a Clan with the input `{clan_tag_or_abbreviation}`.",
                success=False,
                )
            return await ctx.reply(embed=embed)

        embed = await clan_strength_embed(ctx,clan)
        return await ctx.reply(embed=embed)
    
    @app_command_group_clan.command(
        name="strength",
        description="View a Clan's Offensive strength.")
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan.")
    async def app_command_clan_strength(self,interaction:discord.Interaction,clan:str):

        await interaction.response.defer()

        clan = await aClan.create(clan)            
        if not clan:
            embed = await clash_embed(
                context=interaction,
                message=f"I couldn't find a Clan with the input `{clan}`.",
                success=False,
                )
            return await interaction.edit_original_response(embed=embed)            

        embed = await clan_strength_embed(interaction,clan)
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
            clan = await aClan.from_abbreviation(clan_tag_or_abbreviation)
        except InvalidAbbreviation:
            clan = await aClan.create(clan_tag_or_abbreviation)
        
        if not clan:
            embed = await clash_embed(
                context=ctx,
                message=f"I couldn't find a Clan with the input `{clan_tag_or_abbreviation}`.",
                success=False,
                )
            return await ctx.reply(embed=embed)
        
        embed = await clan_donations_embed(ctx,clan)
        await ctx.reply(embed=embed)
    
    @app_command_group_clan.command(name="donations",
        description="View a Clan's Donation stats.")
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan.")
    async def app_command_clanstats_donations(self,interaction:discord.Interaction,clan:str):
   
        await interaction.response.defer()

        clan = await aClan.create(clan)
        if not clan:
            embed = await clash_embed(
                context=interaction,
                message=f"I couldn't find a Clan with the input `{clan}`.",
                success=False,
                )
            return await interaction.edit_original_response(embed=embed)
        
        embed = await clan_donations_embed(interaction,clan)
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
            clan = await aClan.from_abbreviation(clan_tag_or_abbreviation)
        except InvalidAbbreviation:
            clan = await aClan.create(clan_tag_or_abbreviation)

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

        clan = await aClan.create(clan)
        if not clan:
            embed = await clash_embed(
                context=interaction,
                message=f"I couldn't find a Clan with the input `{clan}`.",
                success=False,
                )
            return await interaction.edit_original_response(embed=embed)

        menu = ClanMembersMenu(interaction,clan)
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
            clan = await aClan.from_abbreviation(clan_tag_or_abbreviation)
        except InvalidAbbreviation:
            clan = await aClan.create(clan_tag_or_abbreviation)

        if not clan:
            embed = await clash_embed(
                context=ctx,
                message=f"I couldn't find a Clan with the input `{clan_tag_or_abbreviation}`.",
                success=False,
                )
            return await ctx.reply(embed=embed)

        last_completed_clangames = self.client.cog.current_season if pendulum.now() >= self.client.cog.current_season.clangames_start else self.client.cog.current_season.previous_season()

        embed = await clan_games_data(ctx,clan,last_completed_clangames)
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

        clan = await aClan.create(clan)
        if not clan:
            embed = await clash_embed(
                context=interaction,
                message=f"I couldn't find a Clan with the input `{clan}`.",
                success=False,
                )
            return await interaction.edit_original_response(embed=embed)
        
        last_completed_clangames = self.client.cog.current_season if pendulum.now() >= self.client.cog.current_season.clangames_start else self.client.cog.current_season.previous_season()

        embed = await clan_games_data(interaction,clan,last_completed_clangames)
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

        clan = await aClan.create(clan_tag)
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
        clan = await aClan.create(clan_tag)

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
        
        select_clan = await aClan.create(clan)
        embed = await clash_embed(
            context=interaction,
            title=f"Link Clan: **{select_clan.title}**",
            message=f"**Co-Leader Role:** {coleader_role.mention}"
                + f"\n**Elder Role:** {elder_role.mention}"
                + f"\n**Member Role:** {member_role.mention}",
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
        clan = await aClan.create(clan_tag)
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
    @app_commands.autocomplete(clan=autocomplete_clans_only_registered)
    @app_commands.describe(clan="Select a Clan.")
    async def app_subcommand_link_clan(self,interaction:discord.Interaction,clan:str):
        
        await interaction.response.defer()
        
        select_clan = await aClan.from_tag(clan)
        link = ClanGuildLink.get_link(select_clan.tag,interaction.guild.id)

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
    @command_group_clanset.command(name="leader")
    @commands.guild_only()
    @commands.admin()
    async def subcommand_change_clan_leader(self,ctx:commands.Context,clan_abbreviation:str,new_leader:discord.Member):
        """
        [Admin-only] Change the Leader of a registered Clan.

        Assigns a Leader to the Clan. If the Clan is not already a Guild Clan, this will promote the Clan to Guild Clan status.
        """

        clan = await aClan.from_abbreviation(clan_abbreviation)

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
            clan.is_alliance_clan = True
            await clan.update_member_rank(new_leader.id,"Leader")
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
    @app_commands.check(is_admin)
    @app_commands.autocomplete(clan=autocomplete_clans_only_registered)
    @app_commands.describe(clan="Select a Clan.")
    async def app_subcommand_link_clan(self,interaction:discord.Interaction,clan:str,new_leader:discord.Member):

        await interaction.response.defer()

        select_clan = await aClan.create(clan)
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
            select_clan.is_alliance_clan = True
            await clan.update_member_rank(new_leader.id,"Leader")
            complete_embed = await clash_embed(
                context=interaction,
                title=f"Change Leader: **{select_clan.title}**",
                message=f"Leader: <@{select_clan.leader}>"
                    + f"\n\n{select_clan.long_description}"
                    + f"\n\n>>> {select_clan.c_description}",
                url=select_clan.share_link,
                success=True,
                thumbnail=select_clan.badge)
            return await interaction.edit_original_response(embed=complete_embed,view=None)
    
    ##################################################
    ### CLANSET / CONFIG
    ##################################################
    @command_group_clanset.command(name="config")
    @commands.guild_only()
    @commands.check(is_coleader)
    async def subcommand_change_clan_config(self,ctx:commands.Context,clan_abbreviation:str):
        """
        [Co-Leader+] Show/change Clan Configuration Options.

        Allows Co-Leaders to set up Recruitment Levels, Custom Clan Descriptions, War/Raid Reminders.
        """

        clan = await aClan.from_abbreviation(clan_abbreviation)
        menu = ClanSettingsMenu(ctx,clan)
        await menu.start() 
    
    @app_command_group_clanset.command(
        name="settings",
        description="[Co-Leader+] Show/change Clan Configuration Options.")
    @app_commands.check(is_coleader)
    @app_commands.autocomplete(clan=autocomplete_clans_coleader)
    @app_commands.describe(clan="Select a Clan. You must be a Co-Leader or higher for the Clan.")
    async def app_command_clan_settings(self,interaction:discord.Interaction,clan:str):
        
        await interaction.response.defer()
        clan = await aClan.create(clan)
        menu = ClanSettingsMenu(interaction,clan)
        await menu.start()