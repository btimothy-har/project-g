import discord
import asyncio
import pendulum
import asyncio
import coc
import re

from typing import *

from redbot.core import Config, commands, app_commands
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter, bounded_gather

from coc_main.api_client import BotClashClient, aClashSeason, ClashOfClansError
from coc_main.cog_coc_client import ClashOfClansClient, aClan, aClanWar, aPlayer, BasicPlayer
from coc_main.coc_objects.events.clan_war_leagues import WarLeagueGroup, WarLeaguePlayer, WarLeagueClan
from coc_main.coc_objects.events.clan_war import aWarPlayer

from coc_main.discord.member import aMember
from coc_main.tasks.war_tasks import ClanWarLoop

from coc_main.utils.components import clash_embed, ClanLinkMenu
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

        self._cwl_channel_listener = 1194618178760876042 if bot_client.bot.user.id == 1031240380487831664 else 1194618586610802688

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
    def cwl_channel_listener(self) -> Optional[discord.TextChannel]:
        return self.bot.get_channel(self._cwl_channel_listener)
    
    @property
    def cwl_channel_category(self) -> Optional[discord.CategoryChannel]:
        if self.cwl_channel_listener:
            return self.cwl_channel_listener.category
        return None
    
    @property
    def cwl_guild(self) -> Optional[discord.Guild]:
        if self.cwl_channel_listener:
            return self.cwl_channel_listener.guild
        return None
    
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
    
    async def create_clan_channel(self,clan:WarLeagueClan):
        if not self.cwl_channel_listener:
            raise ValueError("CWL Channel Category is not set.")
        
        league_clan = await WarLeagueClan(clan.tag,self.active_war_league_season)
        if league_clan.league_channel and league_clan.league_role:
            return
        
        await self.cwl_channel_listener.send(f"--ticket {clan.tag} {clan.name}")

        st = pendulum.now()
        while True:
            now = pendulum.now()
            if now.int_timestamp - st.int_timestamp > 45:
                break

            league_clan = await WarLeagueClan(clan.tag,self.active_war_league_season)
            if league_clan.league_channel and league_clan.league_role:
                break
        
        if not league_clan.league_channel or not league_clan.league_role:
            raise ValueError("Could not create Clan Channel.")
        
        cwl_participants = await league_clan.get_participants()
        fetch_players = await self.client.fetch_many_players(*[p.tag for p in cwl_participants])

        p_iter = AsyncIter(cwl_participants)
        tasks = [m.finalize(role=league_clan.league_role) async for m in p_iter]
        await bounded_gather(*tasks,limit=1)

        fetch_players.sort(key=lambda x:(x.town_hall.level,x.hero_strength,x.exp_level),reverse=True)
        participants_20 = fetch_players[:20]
        participants_40 = fetch_players[20:40]

        embeds = []
        if len(participants_20) > 0:
            embed_1 = await clash_embed(
                context=bot_client.bot,
                title=f"CWL Roster: {league_clan.name} {league_clan.tag}",
                message=f"Season: {league_clan.season.description}"
                    + f"\nLeague: {EmojisLeagues.get(league_clan.league)} {league_clan.league}"
                    + f"\nParticipants: {len(fetch_players)}"
                    + f"\n\n"
                    + '\n'.join([f"{EmojisTownHall.get(p.town_hall_level)} `{p.tag:<12} {re.sub('[_*/]','',p.clean_name)[:18]:<18}` <@{p.discord_user}>" for i,p in enumerate(participants_20,1)]),
                show_author=False
                )
            embeds.append(embed_1)
        if len(participants_40) > 0:
            embed_2 = await clash_embed(
                context=bot_client.bot,
                message='\n'.join([f"{EmojisTownHall.get(p.town_hall_level)} `{p.tag:<12} {re.sub('[_*/]','',p.clean_name)[:18]:<18}` <@{p.discord_user}>" for i,p in enumerate(participants_40,21)]),
                show_author=False
                )
            embeds.append(embed_2)
        
        view = ClanLinkMenu([league_clan])            
        if len(embeds) > 0:
            msg = await league_clan.league_channel.send(embeds=embeds,view=view)
            await msg.pin()    
        await league_clan.league_channel.send(f"--add {league_clan.league_role.id}")
    
    @commands.Cog.listener("on_guild_channel_create")
    async def league_channel_ticket_create_listener(self,channel:discord.TextChannel):
        clan_tag = None
        await asyncio.sleep(1)
        
        async for message in channel.history(limit=1,oldest_first=True):
            for embed in message.embeds:
                if embed.footer.text == "Clan War Leagues":
                    clan_tag = embed.description.split()[0]
                    break

        if not clan_tag:
            return
        
        league_clan = await WarLeagueClan(clan_tag,self.active_war_league_season)
        league_role = await channel.guild.create_role(
            reason="CWL Channel Created.",
            name=f"CWL {self.active_war_league_season.short_description} {league_clan.name}"
            )

        await channel.edit(name=f"cwl・{league_clan.name}")
        await league_clan.set_league_discord(channel,league_role)
    
    @commands.Cog.listener("on_guild_channel_delete")
    async def league_channel_ticket_delete_listener(self,channel:discord.TextChannel):
        query_league_clan_by_channel = {'league_channel': channel.id}
        db_query = await bot_client.coc_db.db__war_league_clan.find_one(query_league_clan_by_channel)

        if db_query:
            league_role = channel.guild.get_role(db_query['league_role'])
            if league_role:
                await league_role.delete(reason="CWL Channel Deleted.")
        
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
        
        calculated_elo = {}
        
        if league_group.state == WarState.WAR_ENDED and league_group.current_round == league_group.number_of_rounds:
            league_clan = league_group.get_clan(clan.tag)

            if not league_clan:
                return
            if not league_clan.is_participating:
                return
        
            clan_roster = await league_clan.get_participants()
            async for p in AsyncIter(clan_roster):
                calculated_elo[p.tag] = await p.estimate_elo()
            
            elo_iter = AsyncIter(list(calculated_elo.items()))
            async for tag,elo in elo_iter:
                player = await WarLeaguePlayer(tag,league_group.season)
                await player.set_elo_change(elo)
                await player.adjust_war_elo(elo)
        
    async def war_elo_adjustment(self,clan:aClan,war:aClanWar):
        if war.type != ClanWarType.RANDOM:
            return
        
        if not clan.is_alliance_clan:
            return
        
        async def player_elo_adjustment(player:aWarPlayer):
            elo_gain = 0
            att_iter = AsyncIter(player.attacks)
            async for att in att_iter:
                elo_gain += att.elo_effect
            await player.adjust_war_elo(elo_gain)
        
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
                "description": "Identifies the next current or upcoming season for the Clan War Leagues (CWL).",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    },
                },
            {
                "name": "_assistant_get_cwl_clans",
                "description": "Returns all official Clan War League Clans for The Assassins Guild. Capitalization can be ignored when identifying clans.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    },
                },
            {
                "name": "_assistant_get_league_clan_information",
                "description": "Returns details about a Clan participating in the current or upcoming Clan War Leagues. An identifying Clan Tag must be provided as this only returns one clan.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "clan_tag": {
                            "description": "The Clan Tag to search for.",
                            "type": "string",
                            },
                        },
                    "required": ["clan_tag"]
                    },
                },
            {
                "name": "_assistant_get_clan_roster_information",
                "description": "Returns the War Roster for a Clan participating in the current or upcoming Clan War Leagues. Capitalization can be ignored when identifying clans. Multiple accounts may be registered to the same discord_user.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "clan_name_or_tag": {
                            "type": "string",
                            "description": "The Clan Name or Tag of the Clan to get the roster for.",
                            },
                        },
                    "required": ["clan_tag"]
                    },
                },
            {
                "name": "_assistant_get_user_participation_information",
                "description": "Returns the accounts belonging to the active user which are registered for Clan War Leagues. Multiple accounts may be registered to the same discord_user.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                    },
                },
            ]
        await cog.register_functions(cog_name="ClanWarLeagues", schemas=schemas)
    
    async def _assistant_get_cwl_season(self,*args,**kwargs) -> str:
        return f"The next upcoming Clan War Leagues is for the {self.active_war_league_season.description} season."
    
    async def _assistant_get_cwl_clans(self,*args,**kwargs) -> str:
        clans = await self.client.get_war_league_clans()
        return_info = [c.assistant_name_json() for c in clans]
        return f"The following Clans are registered as official Clan War League clans: {return_info}"
    
    async def _assistant_get_league_clan_information(self,clan_tag:str,*args,**kwargs) -> str:
        clan = await WarLeagueClan(clan_tag,self.active_war_league_season)
        if not clan.is_participating:
            return f"{clan.title} is not participating in CWL for {self.active_war_league_season.description}."
        return f"War League information for {clan.name}: {clan.assistant_json()}"
    
    async def _assistant_get_clan_roster_information(self,clan_name_or_tag:str,*args,**kwargs) -> str:
        q_doc = {
            '$or':[
                {'tag':{'$regex':f'^{clan_name_or_tag}',"$options":"i"}},
                {'name':{'$regex':f'^{clan_name_or_tag}',"$options":"i"}}
                ]
            }
        find_clan = await bot_client.coc_db.db__clan.find_one(q_doc)
        if not find_clan:
            return f"Could not find a clan with the name or tag `{clan_name_or_tag}`."
        
        clan = await WarLeagueClan(find_clan['_id'],self.active_war_league_season)
        
        if not clan.is_participating:
            return f"{clan.title} is not participating in CWL for {self.active_war_league_season.description}."
        if clan.roster_open:
            return f"{clan.title}'s CWL Roster has not been finalized and cannot be communicated yet."
        
        if clan.league_group_id:
            roster = await clan.compute_lineup_stats()
            return_info = [p.assistant_cwl_json() for p in roster]
            unique_users = list(set([p.discord_user for p in roster]))

            return f"The roster for {clan.name} in {self.active_war_league_season.description} has {len(return_info)} players with {len(unique_users)} unique persons. This is the locked in-game roster and cannot be changed. The members are: {return_info}"
        else:
            roster = await clan.get_participants()
            return_info = [p.assistant_cwl_json() for p in roster]
            unique_users = list(set([p.discord_user for p in roster]))

            return f"The roster for {clan.name} in {self.active_war_league_season.description} has {len(return_info)} players with {len(unique_users)} unique persons. This is a pre-start roster and might be subject to changes. The members are: {return_info}"

    async def _assistant_get_user_participation_information(self,user:discord.Member,*args,**kwargs) -> str:
        registered_accounts = await WarLeaguePlayer.get_by_user(self.active_war_league_season,user.id,True)
        if len(registered_accounts) == 0:
            return f"{user.display_name} does not have any accounts registered in CWL for {self.active_war_league_season.description}."
        
        return_info = [p.assistant_cwl_json() for p in registered_accounts]
        return f"{user.display_name}'s registered accounts for {self.active_war_league_season.description} are: {return_info}"
    
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
    @commands.command(name="finalize")
    @commands.is_owner()
    @commands.guild_only()
    async def command_finalize(self,ctx):
        """
        Finalize CWL Rosters for the current season.
        """

        clan = await WarLeagueClan("#URGQUR82",self.active_war_league_season)
        clan.roster_open = True
        i = await clan.finalize_roster()
        await ctx.reply(f"Finalized: {i}.")

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
    async def add_war_league_clan_helper(self,context:Union[discord.Interaction,commands.Context],clan:aClan):

        await clan.add_to_war_league()

        embed = await clash_embed(
            context=context,
            message=f"**{clan.title}** is now added as a CWL Clan.",
            success=True
            )
        return embed

    @subcommand_group_cwl_clan.command(name="add")
    @commands.admin()
    @commands.guild_only()
    async def subcommand_cwl_clan_add(self,ctx,clan_tag:str):
        """
        Add a Clan as a CWL Clan.

        This adds the Clan to the master list. It does not add the Clan to the current CWL Season. To enable a Clan for a specific season, use `/cwl setup`.
        """
        
        clan = await self.client.fetch_clan(clan_tag)
        embed = await self.add_war_league_clan_helper(ctx,clan)
        await ctx.reply(embed=embed)
    
    @app_subcommand_group_cwl_clan.command(name="add",
        description="Add a Clan to the available CWL Clans list.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="The Clan to add as a CWL Clan.")
    async def sub_appcommand_cwl_clan_add(self,interaction:discord.Interaction,clan:str):
        
        await interaction.response.defer()
        get_clan = await self.client.fetch_clan(clan)
        embed = await self.add_war_league_clan_helper(interaction,get_clan)
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