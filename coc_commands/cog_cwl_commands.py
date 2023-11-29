import discord
import pendulum

from typing import *

from redbot.core import commands, app_commands
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter

from coc_main.api_client import BotClashClient, aClashSeason, ClashOfClansError
from coc_main.cog_coc_client import ClashOfClansClient, aPlayer, aClan

from coc_main.discord.member import aMember

from coc_main.utils.components import clash_embed
from coc_main.utils.constants.coc_emojis import EmojisLeagues, EmojisTownHall
from coc_main.utils.autocomplete import autocomplete_clans, autocomplete_war_league_clans, autocomplete_players
from coc_main.utils.checks import is_member, is_admin, is_coleader

from .views.cwl_player import CWLPlayerMenu
from .views.cwl_setup import CWLSeasonSetup
from .views.cwl_view_roster import CWLRosterDisplayMenu
from .views.cwl_league_group import CWLClanGroupMenu
from .views.cwl_roster_setup import CWLRosterMenu

from .excel.cwl_roster_export import generate_cwl_roster_export

bot_client = BotClashClient()

############################################################
############################################################
#####
##### CLIENT COG
#####
############################################################
############################################################
class ClanWarLeagues(commands.Cog):
    """
    Commands for Clan War Leagues.
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
    
    @property
    def active_war_league_season(self) -> aClashSeason:
        if pendulum.now() > self.bot_client.current_season.cwl_end.add(days=5):
            return self.bot_client.current_season.next_season()
        return self.bot_client.current_season
    
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
    
    ############################################################
    ############################################################
    #####
    ##### COG DIRECTORY
    ##### - mycwl
    ##### - cwl
    #####   - info
    #####   - setup
    #####   - clan
    #####     - list
    #####     - add
    #####     - remove
    #####     - roster
    #####     - group
    #####   - roster
    #####     - setup
    #####     - add
    #####     - remove
    #####     - export
    #####
    ############################################################
    ############################################################

    ##################################################
    ### PARENT COMMAND GROUPS
    ##################################################
    @commands.group(name="cwl")
    @commands.guild_only()
    async def command_group_cwl(self,ctx):
        """
        Group for CWL-related Commands.

        **This is a command group. To use the sub-commands below, follow the syntax: `$cwl [sub-command]`.**
        """
        if not ctx.invoked_subcommand:
            pass

    app_command_group_cwl = app_commands.Group(
        name="cwl",
        description="Group for CWL commands. Equivalent to [p]cwl.",
        guild_only=True
        )

    ##################################################
    ### MYCWL
    ##################################################
    @commands.command(name="mycwl")
    @commands.check(is_member)
    @commands.guild_only()
    async def command_mycwl(self,ctx):
        """
        Manage your CWL Signup/Rosters/Stats.

        Automatically provides options depending on the current state of CWL.
        Defaults to the currently running CWL Season.
        """
        
        season = self.active_war_league_season
        cwlmenu = CWLPlayerMenu(ctx,season,aMember(ctx.author.id))

        if pendulum.now() < season.cwl_start:
            await cwlmenu.start_signup()
        else:
            await cwlmenu.show_live_cwl()

    @app_commands.command(name="mycwl",
        description="Manage your CWL Signups, Rosters, Stats.")
    @app_commands.check(is_member)
    @app_commands.guild_only()
    async def appcommand_mycwl(self,interaction:discord.Interaction):
        
        await interaction.response.defer()

        season = self.active_war_league_season
        cwlmenu = CWLPlayerMenu(interaction,season,aMember(interaction.user.id))

        if pendulum.now() < season.cwl_start.subtract(days=1): 
            await cwlmenu.start_signup()
        else:
            await cwlmenu.show_live_cwl()
    
    ##################################################
    ### CWL / INFO
    ##################################################
    async def cwl_information(self,context:Union[commands.Context,discord.Interaction]):
        embed = await clash_embed(
            context=context,
            title=f"Clan War Leagues with AriX",
            message=f"In AriX, we collaborate as an Alliance in the monthly Clan War Leagues. "
                + f"Together as an Alliance, you'll be able to play in a League that best suits your interest and/or skill level."
                + f"\n\nThe information below details what a typical CWL season looks like in AriX."
                + f"\n\u200b",
                )
        embed.add_field(
            name=f"**Registration**",
            value=f"In order to participate in CWL, you must first register. Registration is done on an account-basis, and you are **not** required to register every account."
                + f"\n\nRegistration typically opens on/around the 15th of every month, and lasts until the last day of the month. You will be able to manage your registrations through our AriX Bot, with the `/mycwl` command."
                + f"\n\u200b",
            inline=False
            )
        embed.add_field(
            name="**About League Groups**",
            value="When registering for CWL, you are required to register individual accounts to a **League Group**."
                + "\n\nLeague Groups provide a gauge to assist with rostering. The League Group you sign up for represents the **highest** league you are willing to play in. "
                + "**It is not a guarantee that you will play in that League.** Rosters are subject to availability and Alliance needs."
                + "\n\nThere are currently 4 League Groups available:"
                + f"\n> **League Group A**: {EmojisLeagues.CHAMPION_LEAGUE_I} Champion I ({EmojisTownHall.TH14} TH14+)"
                + f"\n> **League Group B**: {EmojisLeagues.MASTER_LEAGUE_II} Master League II ({EmojisTownHall.TH12} TH12+)"
                + f"\n> **League Group C**: {EmojisLeagues.CRYSTAL_LEAGUE_II} Crystal League II ({EmojisTownHall.TH10} TH10+)"
                + f"\n> **League Group D**: {EmojisLeagues.UNRANKED} Lazy CWL (TH6+; heroes down wars)"
                + "\n\n**Note**: If you do not have any accounts eligible for a specific League Group, you will not be able to register for that group."
                + "\n\u200b",
            inline=False
            )
        embed.add_field(
            name="**Example: How League Groups Work**",
            value="If you sign up for League Group B (Master League II):\n"
                + "\n> You will **not** be rostered in a Champion League III clan."
                + "\n> You **can** be rostered for a Crystal League III clan."
                + "\n\u200b",
            inline=False
            )
        embed.add_field(
            name="**Rostering**",
            value="Based on your indicated League Group, you will be rostered into one of our CWL Clans for the CWL period. **You will be required to move to your rostered CWL Clan for the duration of the CWL period.**"
                + "\n\nRosters will typically be published 1-2 days before the start of CWL. You will be able to view your roster through our AriX Bot, with the `/mycwl` command."
                + "\n\n**Important:** Once rosters are published, your registration cannot be modified further. If you cannot participate in CWL, please contact a Leader immediately."
                + "\n\u200b",
            inline=False
            )
        return embed
    
    @command_group_cwl.command(name="info")
    @commands.guild_only()
    async def subcommand_cwl_info(self,ctx):
        """
        Get information on CWL.
        """

        embed = await self.cwl_information(ctx)
        await ctx.reply(embed=embed)
    
    @app_command_group_cwl.command(name="info",
        description="Get information on CWL.",)
    @app_commands.guild_only()
    async def sub_appcommand_cwl_info(self,interaction:discord.Interaction):
        
        await interaction.response.defer(ephemeral=True)
        embed = await self.cwl_information(interaction)

        await interaction.followup.send(embed=embed,ephemeral=True)
    
    ##################################################
    ### CWL / SETUP
    ##################################################
    @command_group_cwl.command(name="setup")
    @commands.admin()
    @commands.guild_only()
    async def subcommand_cwl_setup(self,ctx):
        """
        Admin home for the CWL Season.

        Provides an overview to Admins of the current CWL Season, and provides toggles to control various options.
        """

        season = self.active_war_league_season
        menu = CWLSeasonSetup(ctx,season)
        await menu.start()
    
    @app_command_group_cwl.command(name="setup",
        description="Setup CWL for a season.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    async def sub_appcommand_cwl_setup(self,interaction:discord.Interaction):
        
        await interaction.response.defer()

        season = self.active_war_league_season
        menu = CWLSeasonSetup(interaction,season)
        await menu.start()
    
    ##################################################
    ### CWL / CLAN
    ##################################################
    @command_group_cwl.group(name="clan")
    @commands.guild_only()
    async def subcommand_group_cwl_clan(self,ctx):
        """
        Manage Clans available for CWL.
        """
        if not ctx.invoked_subcommand:
            pass

    app_subcommand_group_cwl_clan = app_commands.Group(
        name="clan",
        description="Manage Clans available for CWL.",
        parent=app_command_group_cwl,
        guild_only=True
        )    

    ##################################################
    ### CWL / CLAN / LIST
    ##################################################
    async def war_league_clan_list_embed(self,context:Union[discord.Interaction,commands.Context]):
        embed = await clash_embed(
            context=context,
            title=f"**CWL Clans**",
            message=f"Roles will not appear if they are from a different Server."
                + f"\nIf using Thread Channels, archived threads will not be visible."
            )
        clans = await self.client.get_war_league_clans()
        c_iter = AsyncIter(clans)
        async for clan in c_iter:
            embed.add_field(
                name=f"{clan.title}",
                value=f"**League:** {EmojisLeagues.get(clan.war_league_name)} {clan.war_league_name}"
                    + f"\n**Channel:** {getattr(clan.league_clan_channel,'mention','Unknown Channel')}"
                    + f"\n**Role:** {getattr(clan.league_clan_role,'mention','Unknown Role')}"
                    + f"\n\u200b",
                inline=False
                )            
        return embed
    
    @subcommand_group_cwl_clan.command(name="list")
    @commands.admin()
    @commands.guild_only()
    async def subcommand_cwl_clans_show(self,ctx):
        """
        [Admin-only] List all Clans available for CWL.

        Effectively, this is the "master list" of clans available for CWL, and will be included for tracking/reporting.

        To add a Clan to the list, use `/cwl clan add`.
        """

        embed = await self.war_league_clan_list_embed(ctx)
        await ctx.reply(embed=embed)
    
    @app_subcommand_group_cwl_clan.command(name="list",
        description="List all Clans available for CWL.",)
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    async def sub_appcommand_cwl_clans_show(self,interaction:discord.Interaction):
        
        await interaction.response.defer()
        embed = await self.war_league_clan_list_embed(interaction)
        await interaction.edit_original_response(embed=embed)
    
    ##################################################
    ### CWL / CLAN / ADD
    ##################################################
    async def add_war_league_clan_helper(self,
        context:Union[discord.Interaction,commands.Context],
        clan:aClan,
        channel:discord.TextChannel,
        role:discord.Role):

        await clan.add_to_war_league(channel,role)

        embed = await clash_embed(
            context=context,
            message=f"**{clan.title}** is now added as a CWL Clan."
                + f"\n\n**Channel:** {clan.league_clan_channel.mention}"
                + f"\n**Role:** {clan.league_clan_role.mention}",
            success=True
            )
        return embed

    @subcommand_group_cwl_clan.command(name="add")
    @commands.admin()
    @commands.guild_only()
    async def subcommand_cwl_clan_add(self,ctx,
        clan_tag:str,
        cwl_channel:Union[discord.TextChannel,discord.Thread],
        cwl_role:discord.Role):
        """
        Add a Clan as a CWL Clan.

        This adds the Clan to the master list. It does not add the Clan to the current CWL Season. To enable a Clan for a specific season, use `/cwl setup`.
        """
        
        clan = await self.client.fetch_clan(clan_tag)
        embed = await self.add_war_league_clan_helper(ctx,clan,cwl_channel,cwl_role)
        await ctx.reply(embed=embed)
    
    @app_subcommand_group_cwl_clan.command(name="add",
        description="Add a Clan to the available CWL Clans list.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(
        clan="The Clan to add as a CWL Clan.",
        channel="The primary channel to use for CWL in this clan.",
        role="The role to assign to CWL participants in this clan.")
    async def sub_appcommand_cwl_clan_add(self,interaction:discord.Interaction,clan:str,channel:Union[discord.TextChannel,discord.Thread],role:discord.Role):
        
        await interaction.response.defer()
        get_clan = await self.client.fetch_clan(clan)
        embed = await self.add_war_league_clan_helper(interaction,get_clan,channel,role)
        await interaction.edit_original_response(embed=embed)
    
    ##################################################
    ### CWL / CLAN / REMOVE
    ##################################################
    @subcommand_group_cwl_clan.command(name="remove")
    @commands.is_owner()
    @commands.guild_only()
    async def subcommand_cwl_clan_remove(self,ctx,clan_tag:str):
        """
        Remove a Clan from the available CWL Clans list.

        Owner-only to prevent strange things from happening.
        """
        
        clan = await self.client.fetch_clan(clan_tag)
        await clan.remove_from_war_league()

        embed = await clash_embed(
            context=ctx,
            message=f"**{clan.title}** is now removed from the CWL Clan List.",
            success=False
            )
        await ctx.reply(embed=embed)
    
    ##################################################
    ### CWL / CLAN / VIEW-ROSTER
    ##################################################
    @subcommand_group_cwl_clan.command(name="roster")
    @commands.check(is_member)
    @commands.guild_only()
    async def subcommand_cwl_clan_viewroster_member(self,ctx,clan_tag:str):
        """
        View the Roster for a CWL Clan.
        """

        season = self.active_war_league_season
        
        clan = await self.client.fetch_clan(clan_tag)
        cwl_clan = clan.war_league_season(season)

        if not cwl_clan.is_participating:
            embed = await clash_embed(
                context=ctx,
                message=f"**{clan.title}** is not participating in CWL for {season.description}.",
                success=False
                )
            return await ctx.reply(embed=embed,view=None)
        
        menu = CWLRosterDisplayMenu(ctx,cwl_clan)
        await menu.start()
    
    @app_subcommand_group_cwl_clan.command(name="roster",
        description="View a CWL Clan's current Roster.")
    @app_commands.check(is_member)
    @app_commands.guild_only()
    @app_commands.autocomplete(clan=autocomplete_war_league_clans)
    @app_commands.describe(clan="The Clan to view. Only registered CWL Clans are eligible.")
    async def sub_appcommand_cwl_clan_viewroster_member(self,interaction:discord.Interaction,clan:str):
        
        await interaction.response.defer()

        season = self.active_war_league_season

        get_clan = await self.client.fetch_clan(clan)
        cwl_clan = get_clan.war_league_season(season)

        if not cwl_clan.is_participating:
            embed = await clash_embed(
                context=interaction,
                message=f"**{get_clan.title}** is not participating in CWL for {season.description}.",
                success=False
                )
            return await interaction.edit_original_response(embed=embed,view=None)

        menu = CWLRosterDisplayMenu(interaction,cwl_clan)
        await menu.start()
    
    ##################################################
    ### CWL / CLAN / LEAGUE GROUP
    ##################################################
    @subcommand_group_cwl_clan.command(name="group")
    @commands.check(is_member)
    @commands.guild_only()
    async def subcommand_cwl_clan_viewgroup(self,ctx,clan_tag:str):
        """
        View the League Group for a CWL Clan.
        """
        
        clan = await self.client.fetch_clan(clan_tag)
        cwl_clan = clan.war_league_season(self.bot_client.current_season)

        if not cwl_clan.league_group:
            embed = await clash_embed(
                context=ctx,
                message=f"**{clan.title}** has not started CWL for {self.bot_client.current_season.description}."
                    + "\n\nIf you're looking for the Clan Roster, use [p]`cwl clan roster` instead.",
                success=False
                )
            return await ctx.reply(embed=embed,view=None)
        
        menu = CWLClanGroupMenu(ctx,cwl_clan)
        await menu.start()
    
    @app_subcommand_group_cwl_clan.command(name="group",
        description="View a CWL Clan's current League Group.")
    @app_commands.check(is_member)
    @app_commands.guild_only()
    @app_commands.autocomplete(clan=autocomplete_war_league_clans)
    @app_commands.describe(clan="The Clan to view. Only registered CWL Clans are tracked.")
    async def sub_appcommand_cwl_clan_viewgroup(self,interaction:discord.Interaction,clan:str):

        await interaction.response.defer()
        
        get_clan = await self.client.fetch_clan(clan)
        cwl_clan = get_clan.war_league_season(self.bot_client.current_season)

        if not cwl_clan.league_group:
            embed = await clash_embed(
                context=interaction,
                message=f"**{get_clan.title}** has not started CWL for {self.bot_client.current_season.description}."
                    + "\n\nIf you're looking for the Clan Roster, use [p]`cwl clan roster` instead.",
                success=False
                )
            return await interaction.edit_original_response(embed=embed,view=None)
        
        menu = CWLClanGroupMenu(interaction,cwl_clan)
        await menu.start()
    
    ##################################################
    ### CWL / ROSTERS
    ##################################################
    @command_group_cwl.group(name="roster")
    @commands.guild_only()
    async def subcommand_group_cwl_roster(self,ctx):
        """
        Manage CWL Rosters.

        Admins may create rosters from the list of Player Registrations. Rosters can be in two stages:
        > - **Open**: The roster is available for modifications. Players in the roster **cannot** see the roster yet.
        > - **Finalized**: The roster is locked and published. Players will be assigned the Clan role and can view their own rosters.

        A roster must have at least 15 players to be finalized. There is a maximum of 35 players per roster.
        
        To modify a roster once it has been finalized, use `/cwl roster add` or `/cwl roster remove`.
        """
        if not ctx.invoked_subcommand:
            pass

    app_subcommand_group_cwl_roster = app_commands.Group(
        name="roster",
        description="Manage CWL Rosters",
        parent=app_command_group_cwl,
        guild_only=True
        )
    
    ##################################################
    ### CWL / ROSTER / SETUP
    ##################################################
    @subcommand_group_cwl_roster.command(name="setup")
    @commands.admin()
    @commands.guild_only()
    async def subcommand_cwl_roster_setup(self,ctx,clan_tag:str):
        """
        Setup a Roster for a Clan.

        This is an interactive menu with various options to quickly set up a roster. Use the in-menu help buttons.

        Always defaults to the next open CWL Season.
        """
            
        season = self.active_war_league_season
        
        clan = await self.client.fetch_clan(clan_tag)
        cwl_clan = clan.war_league_season(season)

        if not cwl_clan.is_participating:
            embed = await clash_embed(
                context=ctx,
                message=f"**{clan.title}** is not participating in CWL for {season.description}.",
                success=False
                )
            return await ctx.reply(embed=embed,view=None)
        
        menu = CWLRosterMenu(ctx,season,cwl_clan)
        await menu.start()
    
    @app_subcommand_group_cwl_roster.command(name="setup",
        description="Setup a CWL Roster for a Clan. Defaults to the next open CWL Season.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    @app_commands.autocomplete(clan=autocomplete_war_league_clans)
    @app_commands.describe(clan="The Clan to setup for.")
    async def sub_appcommand_cwl_roster_setup(self,interaction:discord.Interaction,clan:str):
        
        await interaction.response.defer()

        season = self.active_war_league_season

        get_clan = await self.client.fetch_clan(clan)
        cwl_clan = get_clan.war_league_season(season)

        if not cwl_clan.is_participating:
            embed = await clash_embed(
                context=interaction,
                message=f"**{get_clan.title}** is not participating in CWL for {season.description}.",
                success=False
                )
            return await interaction.edit_original_response(embed=embed,view=None)

        menu = CWLRosterMenu(interaction,season,cwl_clan)
        await menu.start()
    
    ##################################################
    ### CWL / ROSTER / ADD
    ##################################################
    async def admin_add_player_helper(self,
        context:Union[discord.Interaction,commands.Context],
        clan_tag:str,
        player_tag:str):

        reopen = False
        season = self.active_war_league_season

        clan = await self.client.fetch_clan(clan_tag)
        cwl_clan = clan.war_league_season(season)

        if not cwl_clan.is_participating:
            embed = await clash_embed(
                context=context,
                message=f"**{clan.title}** is not participating in CWL for {season.description}.",
                success=False
                )
            return embed
        
        if cwl_clan.league_group:
            embed = await clash_embed(
                context=context,
                message=f"{season.description} CWL has already started for {clan.title}.",
                success=False
                )
            return embed

        player = await self.client.fetch_player(player_tag)
        cwl_player = player.war_league_season(season)
        original_roster = cwl_player.roster_clan

        await cwl_player.admin_add(cwl_clan.tag)

        if original_roster:
            original_roster_length = len(original_roster.participants)
            if original_roster_length < 15 and original_roster.roster_open == False:
                reopen = True
                await original_roster.open_roster()

        embed = await clash_embed(
            context=context,
            message=f"**{player.title}** has been added to CWL."
                + f"\n\n> Clan: {cwl_player.roster_clan.title}"
                + f"\n> Discord: <@{cwl_player.discord_user}>"
                + (f"\n\n{original_roster.clean_name}'s Roster has been re-opened. ({original_roster_length} players remain)" if reopen else ""),
            success=True
            )
        return embed

    @subcommand_group_cwl_roster.command(name="open")
    @commands.is_owner()
    @commands.guild_only()
    async def subcommand_cwl_roster_open(self,ctx,clan_tag:str):
        """
        Force open a CWL Clan's Roster.
        """
        season = self.active_war_league_season

        clan = await self.client.fetch_clan(clan_tag)
        cwl_clan = clan.war_league_season(season)

        await cwl_clan.open_roster()
        await ctx.tick()
    
    @subcommand_group_cwl_roster.command(name="add")
    @commands.admin()
    @commands.guild_only()
    async def subcommand_cwl_roster_add(self,ctx,clan_tag:str,player_tag:str):
        """
        Admin add a Player to a Roster.

        This works even if the roster has been finalized. If the player is currently not registered, this will auto-register them into CWL.

        **Important**
        > - If the player is currently not registered, this will make them appear as if they've registered without a League Group.
        > - If the player is already in a finalized roster, this will remove the player from that roster. If this lowers the roster below 15 players, the roster will be re-opened.
        """
        
        embed = await self.admin_add_player_helper(ctx,clan_tag,player_tag)
        await ctx.reply(embed=embed)
    
    @app_subcommand_group_cwl_roster.command(name="add",
        description="Add a Player to a CWL Roster. Automatically registers the Player, if not registered.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    @app_commands.autocomplete(clan=autocomplete_war_league_clans)
    @app_commands.autocomplete(player=autocomplete_players)
    @app_commands.describe(
        clan="The Clan to add the player to. Must be an active CWL Clan.",
        player="The Player to add to the Roster.")
    async def sub_appcommand_cwl_roster_add(self,interaction:discord.Interaction,clan:str,player:str):
        
        await interaction.response.defer()
        embed = await self.admin_add_player_helper(interaction,clan,player)
        return await interaction.edit_original_response(embed=embed)
    
    ##################################################
    ### CWL / ROSTER / REMOVE
    ##################################################
    async def admin_remove_player_helper(self,
        context:Union[discord.Interaction,commands.Context],
        player_tag:str):

        reopen = False
        season = self.active_war_league_season
        
        player = await self.client.fetch_player(player_tag)
        cwl_player = player.war_league_season(season)
        
        if getattr(cwl_player,'league_clan',None):
            embed = await clash_embed(
                context=context,
                message=f"**{player}** is already in CWL with **{cwl_player.league_clan.title}**.",
                success=False
                )
            return embed

        original_roster = cwl_player.roster_clan
        await cwl_player.admin_remove()        

        if original_roster:
            original_roster_length = len(original_roster.participants)
            if original_roster_length < 15 and original_roster.roster_open == False:
                reopen = True
                await original_roster.open_roster()

        embed = await clash_embed(
            context=context,
            message=f"**{player.title}** has been removed from {season.description} CWL."
                + (f"\n\n{original_roster.name}'s Roster has been re-opened. ({original_roster_length} players remain)" if reopen else ""),
            success=True
            )
        return embed
    
    @subcommand_group_cwl_roster.command(name="remove")
    @commands.admin()
    @commands.guild_only()
    async def subcommand_cwl_roster_remove(self,ctx,player_tag:str):
        """
        Admin remove a Player from CWL.

        This works even if the roster has been finalized. If the player is currently in a roster, this will auto-remove them from CWL.

        **Important**
        If the player is in a finalized roster, and this lowers the roster below 15 players, the roster will be re-opened.
        """
            
        embed = await self.admin_remove_player_helper(ctx,player_tag)
        await ctx.reply(embed=embed)
    
    @app_subcommand_group_cwl_roster.command(name="remove",
        description="Removes a Player from a CWL Roster. Automatically unregisters the Player, if registered.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    @app_commands.autocomplete(player=autocomplete_players)
    @app_commands.describe(player="The Player to remove from CWL.")
    async def sub_appcommand_cwl_roster_add(self,interaction:discord.Interaction,player:str):
        
        await interaction.response.defer()

        embed = await self.admin_remove_player_helper(interaction,player)
        return await interaction.edit_original_response(embed=embed)

    ##################################################
    ### CWL / ROSTER / EXPORT
    ##################################################
    @subcommand_group_cwl_roster.command(name="export")
    @commands.check(is_coleader)
    @commands.guild_only()
    async def subcommand_cwl_roster_export(self,ctx):
        """
        Exports all Signups (and Roster information) to Excel.

        Defaults to the currently open CWL Season.
        """

        wait_msg = await ctx.reply("Exporting Data... please wait.")

        season = self.active_war_league_season

        rp_file = await generate_cwl_roster_export(season)
        
        if not rp_file:
            return await wait_msg.edit(f"I couldn't export the CWL Roster for {season.description}. Were you trying to export an already-completed CWL Season?")
        
        await wait_msg.delete()
        await ctx.reply(
            content=f"Here is the CWL Roster for {season.description}.",
            file=discord.File(rp_file))
    
    @app_subcommand_group_cwl_roster.command(name="export",
        description="Exports all Signups (and Roster information) to Excel. Uses the currently open CWL Season.")
    @app_commands.check(is_coleader)
    @app_commands.guild_only()
    async def sub_appcommand_cwl_roster_export(self,interaction:discord.Interaction):
        
        await interaction.response.defer()

        season = self.active_war_league_season
        
        rp_file = await generate_cwl_roster_export(season)
        
        if not rp_file:
            return await interaction.edit_original_response(content=f"I couldn't export the CWL Roster for {season.description}. Were you trying to export an already-completed CWL Season?")
        
        await interaction.followup.send(
            content=f"Here is the CWL Roster for {season.description}.",
            file=discord.File(rp_file))