import discord
import asyncio
import pendulum
import asyncio
import coc

from typing import *

from redbot.core import commands, app_commands
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter, bounded_gather

from coc_main.api_client import BotClashClient, aClashSeason, ClashOfClansError
from coc_main.cog_coc_client import ClashOfClansClient, aClan, aClanWar, aPlayer
from coc_main.coc_objects.events.clan_war_leagues import WarLeagueGroup, WarLeaguePlayer, WarLeagueClan
from coc_main.coc_objects.events.clan_war import aWarPlayer

from coc_main.discord.member import aMember
from coc_main.tasks.war_tasks import ClanWarLoop

from coc_main.utils.components import clash_embed
from coc_main.utils.constants.coc_emojis import EmojisLeagues, EmojisTownHall
from coc_main.utils.constants.coc_constants import WarState, ClanWarType
from coc_main.utils.constants.coc_emojis import EmojisClash
from coc_main.utils.constants.ui_emojis import EmojisUI
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
    
    async def cog_load(self):
        asyncio.create_task(self.load_events())
    
    async def cog_unload(self):
        ClanWarLoop.remove_war_end_event(self.cwl_elo_adjustment)
        ClanWarLoop.remove_war_end_event(self.war_elo_adjustment)
    
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
    ##### WAR ELO TASKS
    ############################################################    
    async def load_events(self):
        while True:
            if getattr(bot_client,'_is_initialized',False):
                break
            await asyncio.sleep(1)
        
        ClanWarLoop.add_war_end_event(self.cwl_elo_adjustment)
        ClanWarLoop.add_war_end_event(self.war_elo_adjustment)

    async def cwl_elo_adjustment(self,clan:aClan,war:aClanWar):
        if war.type != ClanWarType.CWL:
            return
        if war._league_group == '':
            return
        
        league_group = await WarLeagueGroup(war._league_group)
        if not league_group:
            return

        async def player_elo_adjustment(player:aWarPlayer,roster_elo:float):
            elo_gain = 0
            att_iter = AsyncIter(player.attacks)
            async for att in att_iter:
                if att.stars >= 1:
                    elo_gain += 1
                if att.stars >= 2:
                    elo_gain += 1
                if att.stars >= 3:
                    elo_gain += 2

                elo_gain += (att.defender.town_hall - att.attacker.town_hall)
            
            adj_elo = round((elo_gain * (roster_elo / player.war_elo)),3) - 3
            await player.adjust_war_elo(adj_elo)
        
        if league_group.state == WarState.WAR_ENDED and league_group.current_round == league_group.number_of_rounds:
            league_clan = league_group.get_clan(clan.tag)

            if not league_clan:
                return
        
            clan_roster = await league_clan.get_participants()
            try:
                avg_elo = sum([p.war_elo for p in clan_roster]) / len(clan_roster)
            except ZeroDivisionError:
                avg_elo = 0

            w_iter = AsyncIter(league_clan.league_wars)
            async for war in w_iter:
                w_clan = war.get_clan(clan.tag)
                p_iter = AsyncIter(w_clan.members)
                tasks = [player_elo_adjustment(p,avg_elo) async for p in p_iter]
                await bounded_gather(*tasks)
        
    async def war_elo_adjustment(self,clan:aClan,war:aClanWar):
        if war.type != ClanWarType.RANDOM:
            return
        
        async def player_elo_adjustment(player:aWarPlayer):
            elo_gain = 0
            att_iter = AsyncIter(player.attacks)
            async for att in att_iter:
                if att.defender.town_hall == att.attacker.town_hall:
                    elo_gain += -1
                    if att.stars >= 1:
                        elo_gain += 0.25 # -0.75 for 1 star
                    if att.stars >= 2:
                        elo_gain += 0.5 # -0.25 for 2 star
                    if att.stars >= 3:
                        elo_gain += 0.75 # +0.5 for 3 star
            await player.adjust_war_elo(elo_gain)
        
        bot_client.coc_main_log.info(f"ELO for {war}")
        war_clan = war.get_clan(clan.tag)
        p_iter = AsyncIter(war_clan.members)
        tasks = [player_elo_adjustment(p) async for p in p_iter]
        await bounded_gather(*tasks)
    
    ##################################################
    ### ASSISTANT COG FUNCTIONS
    ##################################################
    @commands.Cog.listener()
    async def on_assistant_cog_add(self,cog:commands.Cog):
        schemas = [
            {
                "name": "_assistant_get_cwl_season",
                "description": "Identifies the next upcoming season for the Clan War Leagues (CWL).",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    },
                },
            {
                "name": "_assistant_get_cwl_information",
                "description": "Information on how Clan War Leagues (CWL) work in The Assassins Guild, including available commands. Use this when being asked about CWL. Always tell the user that they can run `/cwl info` for more information.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    },
                }
            ]
        await cog.register_functions(cog_name="ClanWarLeagues", schemas=schemas)
    
    async def _assistant_get_cwl_season(self,*args,**kwargs) -> str:
        return f"The next upcoming Clan War Leagues is for the {self.active_war_league_season.description} season."

    async def _assistant_get_cwl_information(self,*args,**kwargs) -> str:
        info = await self.cwl_information()
        x = info.to_dict()
        return f"CWL Information: {x}"
    
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
        cwlmenu = CWLPlayerMenu(ctx,season,await aMember(ctx.author.id))

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
    async def cwl_information(self,context:Optional[Union[commands.Context,discord.Interaction]]=None):
        if not context:
            context = self.bot
        
        embed = await clash_embed(
            context=context,
            title=f"Clan War Leagues with The Assassins Guild",
            message=f"In the Guild, our clans collaborate together in the monthly Clan War Leagues."
                + f"As a member of the Guild, you'll be able to play in a League that best suits your interest and/or skill level."
                + f"\n\nThe information below details what a typical CWL season will look like."
                + f"\n\u200b",
                )
        embed.add_field(
            name=f"**Registration**",
            value=f"In order to participate in CWL, you must first register. Registration is done on an account-basis, and you are **not** required to register every account."
                + f"\n\nRegistration typically opens on/around the 15th of every month, and lasts until the last day of the month. You will be able to manage your registrations through N.E.B.U.L.A., with the `/mycwl` command."
                + f"\n\u200b",
            inline=False
            )
        embed.add_field(
            name="**About League Groups**",
            value="When registering for CWL, you are required to register individual accounts to a **League Group**."
                + "\n\nLeague Groups provide a gauge to assist with rostering. The League Group you sign up for represents the **highest** league you are willing to play in. "
                + "**It is not a guarantee that you will play in that League.** Rosters are subject to availability and Alliance needs."
                + "\n\nThere are currently 4 League Groups available:"
                + f"\n> **League Group A**: {EmojisLeagues.CHAMPION_LEAGUE_I} Champion I ({EmojisTownHall.TH15} TH15+)"
                + f"\n> **League Group B**: {EmojisLeagues.MASTER_LEAGUE_II} Master League II ({EmojisTownHall.TH13} TH13+)"
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
            name="**The War Rank System**",
            value=f"You might see the following icon on some of your player profiles: {EmojisUI.ELO}. This is your **War Rank**."
                + f"\n\nWar Ranks are used for rostering players of equal Townhall and Hero Levels. The higher your War Rank, the more likely you will be rostered as close to your League Group as possible."
                + "\n"
                + f"\n__Rank Points are gained by playing in CWL.__"
                + f"\n- You lose -3 rank points for every war you are rostered in."
                + f"\n- You gain: +1 for a 1-star hit, +2 for a 2-star hit, +4 for a 3-star hit."
                + f"\n- For a hit against a different TH level, you gain/lose points based on the difference in TH levels."
                + f"\n- Your final rank point gain/loss will be adjusted by the average Rank of your War Clan."
                + "\n"
                + f"\n__You can also gain Rank Points from regular wars.__"
                + f"\n- Only attacks against equivalent TH opponents count."
                + f"\n- -1 for a 0-star hit"
                + f"\n- -0.75 for a 1-star hit"
                + f"\n- -0.25 for a 2-star hit"
                + f"\n- +0.5 for a 3-star hit"
                + "\n\u200b",
            inline=False
            )
        embed.add_field(
            name="**Rostering**",
            value="Based on your indicated League Group and War Rank, you will be rostered into one of our CWL Clans for the CWL period. **You will be required to move to your rostered CWL Clan for the duration of the CWL period.**"
                + "\n\nRosters will typically be published 1-2 days before the start of CWL. You will be able to view your roster with the `/mycwl` command."
                + "\n\n**Important:** Once rosters are published, your registration cannot be modified further. If you cannot participate in CWL, please contact a Leader immediately."
                + "\n\u200b",
            inline=False
            )
        embed.add_field(
            name="**Useful Commands**",
            value=f"**/mycwl** - Manage your CWL Signups, Rosters, Stats."
                + f"\n**/cwl info** - Shows this page!"
                + f"\n**/cwl clan roster** - Shows a League Clan's CWL Roster."
                + f"\n**/cwl clan group** - Shows a League Clan's CWL Group."
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

    @commands.command(name="cwlelo")
    @commands.is_owner()
    @commands.guild_only()
    async def command_cwlelo(self,ctx):
        """
        [Owner-only] Adjusts the ELO of all CWL Players.
        """
        date = pendulum.datetime(2023,12,1)
        q_doc = {
            'type': 'random',
            'state': 'warEnded',
            'preparation_start_time': {'$gte': date.int_timestamp},
            }
        query = bot_client.coc_db.db__clan_war.find(q_doc)
        war_list = [await aClanWar(w['_id']) async for w in query]

        w_iter = AsyncIter(war_list)
        async for war in w_iter:
            bot_client.coc_main_log.info(f"Adjusting ELO for {war}")
            clan = None
            if war.clan_1.is_alliance_clan:
                clan = war.clan_1
            elif war.clan_2.is_alliance_clan:
                clan = war.clan_2
            if clan:
                bot_client.coc_main_log.info(f"Adjusting ELO for {war}")
                await self.war_elo_adjustment(clan,war)
        
        await ctx.reply("Done.")
    
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
        league_clan = await WarLeagueClan(clan_tag,season)

        if not league_clan.is_participating:
            embed = await clash_embed(
                context=ctx,
                message=f"**{league_clan.title}** is not participating in CWL for {season.description}.",
                success=False
                )
            return await ctx.reply(embed=embed,view=None)
        
        menu = CWLRosterDisplayMenu(ctx,league_clan)
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
        league_clan = await WarLeagueClan(clan,season)

        if not league_clan.is_participating:
            embed = await clash_embed(
                context=interaction,
                message=f"**{league_clan.title}** is not participating in CWL for {season.description}.",
                success=False
                )
            return await interaction.edit_original_response(embed=embed,view=None)

        menu = CWLRosterDisplayMenu(interaction,league_clan)
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
        
        league_clan = await WarLeagueClan(clan_tag,self.bot_client.current_season)

        if not league_clan.league_group_id:
            embed = await clash_embed(
                context=ctx,
                message=f"**{league_clan.title}** has not started CWL for {self.bot_client.current_season.description}."
                    + "\n\nIf you're looking for the Clan Roster, use [p]`cwl clan roster` instead.",
                success=False
                )
            return await ctx.reply(embed=embed,view=None)

        league_group = await league_clan.get_league_group()        
        menu = CWLClanGroupMenu(ctx,league_group)
        await menu.start()
    
    @app_subcommand_group_cwl_clan.command(name="group",
        description="View a CWL Clan's current League Group.")
    @app_commands.check(is_member)
    @app_commands.guild_only()
    @app_commands.autocomplete(clan=autocomplete_war_league_clans)
    @app_commands.describe(clan="The Clan to view. Only registered CWL Clans are tracked.")
    async def sub_appcommand_cwl_clan_viewgroup(self,interaction:discord.Interaction,clan:str):

        await interaction.response.defer()

        league_clan = await WarLeagueClan(clan,self.bot_client.current_season)

        if not league_clan.league_group_id:
            embed = await clash_embed(
                context=interaction,
                message=f"**{league_clan.title}** has not started CWL for {self.bot_client.current_season.description}."
                    + "\n\nIf you're looking for the Clan Roster, use [p]`cwl clan roster` instead.",
                success=False
                )
            return await interaction.edit_original_response(embed=embed,view=None)
        
        league_group = await league_clan.get_league_group()        
        menu = CWLClanGroupMenu(interaction,league_group)
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
        league_clan = await WarLeagueClan(clan_tag,season)

        if not league_clan.is_participating:
            embed = await clash_embed(
                context=ctx,
                message=f"**{league_clan.title}** is not participating in CWL for {season.description}.",
                success=False
                )
            return await ctx.reply(embed=embed,view=None)
        
        menu = CWLRosterMenu(ctx,season,league_clan)
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
        league_clan = await WarLeagueClan(clan,season)

        if not league_clan.is_participating:
            embed = await clash_embed(
                context=interaction,
                message=f"**{league_clan.title}** is not participating in CWL for {season.description}.",
                success=False
                )
            return await interaction.edit_original_response(embed=embed,view=None)

        menu = CWLRosterMenu(interaction,season,league_clan)
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
        league_clan = await WarLeagueClan(clan_tag,season)

        if not league_clan.is_participating:
            embed = await clash_embed(
                context=context,
                message=f"**{league_clan.title}** is not participating in CWL for {season.description}.",
                success=False
                )
            return embed
        
        if league_clan.league_group_id:
            embed = await clash_embed(
                context=context,
                message=f"{season.description} CWL has already started for {league_clan.title}.",
                success=False
                )
            return embed

        league_player = await WarLeaguePlayer(player_tag,season)
        original_roster = league_player.roster_clan

        await league_player.admin_add(league_clan)

        if original_roster:
            original_roster_length = len(await original_roster.get_participants())
            if original_roster_length < 15 and original_roster.roster_open == False:
                reopen = True
                await original_roster.open_roster()

        embed = await clash_embed(
            context=context,
            message=f"**{league_player.title}** has been added to CWL."
                + f"\n\n> Clan: {league_player.roster_clan.title}"
                + f"\n> Discord: <@{league_player.discord_user}>"
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
        
        league_player = await WarLeaguePlayer(player_tag,season)
        
        if getattr(league_player,'league_clan',None):
            embed = await clash_embed(
                context=context,
                message=f"**{league_player}** is already in CWL with **{league_player.league_clan.title}**.",
                success=False
                )
            return embed

        original_roster = league_player.roster_clan
        await league_player.admin_remove()

        if original_roster:
            original_roster_length = len(await original_roster.get_participants())
            if original_roster_length < 15 and original_roster.roster_open == False:
                reopen = True
                await original_roster.open_roster()

        embed = await clash_embed(
            context=context,
            message=f"**{league_player.title}** has been removed from {season.description} CWL."
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