import coc
import discord
import asyncio
import pendulum
import asyncio
import re
import logging

from typing import *
from discord.ext import tasks

from redbot.core import Config, commands, app_commands
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter, bounded_gather

from coc_main.client.global_client import GlobalClient
from coc_main.cog_coc_main import ClashOfClansMain as coc_main

from coc_main.coc_objects.season.season import aClashSeason
from coc_main.coc_objects.clans.clan import aClan
from coc_main.coc_objects.events.clan_war_v2 import bClanWar, bWarClan, bWarLeagueClan, bWarPlayer
from coc_main.coc_objects.events.war_players import bWarLeaguePlayer

from coc_main.discord.member import aMember

from coc_main.utils.components import clash_embed, ClanLinkMenu
from coc_main.utils.constants.ui_emojis import EmojisUI
from coc_main.utils.constants.coc_emojis import EmojisLeagues, EmojisTownHall
from coc_main.utils.constants.coc_constants import WarState, ClanWarType
from coc_main.utils.autocomplete import autocomplete_clans, autocomplete_players

from coc_discord.feeds.reminders import EventReminder

from .checks import is_cwl_admin
from .autocomplete import autocomplete_all_league_clans, autocomplete_season_league_participants, autocomplete_season_league_clans

from .components.cwl_player import CWLPlayerMenu
from .components.cwl_setup import CWLSeasonSetup
from .components.cwl_view_roster import CWLRosterDisplayMenu
from .components.cwl_league_group import CWLClanGroupMenu
from .components.cwl_roster_setup import CWLRosterMenu

from .components.cwl_roster_export import generate_cwl_roster_export

LOG = logging.getLogger("coc.main")

############################################################
############################################################
#####
##### CLIENT COG
#####
############################################################
############################################################
class ClanWarLeagues(commands.Cog,GlobalClient):
    """
    Commands for Clan War Leagues.
    """

    __author__ = coc_main.__author__
    __version__ = coc_main.__version__

    def __init__(self):        
        self.banned_users = set()

        self.ticket_prefix = "--"
        self._ticket_listener = 0        
        self._cwl_guild = 0
        self._cwl_top_role = 0
        self._admin_role = 0

        self.config = Config.get_conf(self,identifier=644530507505336330,force_registration=True)
        default_global = {
            "banned_users":[],
            "ticket_prefix": "--",
            "ticket_listener": 0,            
            "master_guild": 0,
            "master_role": 0,
            "admin_role": 0
            }
        self.config.register_global(**default_global)

        self.last_season_check = pendulum.now().subtract(days=1)
        self._current_season = None

        self._loop_lock = asyncio.Lock()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"
    
    async def cog_command_error(self,ctx:commands.Context,error:discord.DiscordException):
        original_exc = getattr(error,'original',error)
        await GlobalClient.handle_command_error(original_exc,ctx)

    async def cog_app_command_error(self,interaction:discord.Interaction,error:discord.DiscordException):
        original_exc = getattr(error,'original',error)
        await GlobalClient.handle_command_error(original_exc,interaction)
    
    ############################################################
    #####
    ##### PROPERTIES
    #####
    ############################################################
    @property
    def bot(self) -> Red:
        return GlobalClient.bot
    
    @property
    def cwl_guild(self) -> Optional[discord.Guild]:
        return self.bot.get_guild(self._cwl_guild)
    @property
    def cwl_top_role(self) -> Optional[discord.Role]:
        if self.cwl_guild:
            return self.cwl_guild.get_role(self._cwl_top_role)
        return None
    @property
    def admin_role(self) -> Optional[discord.Role]:
        if self.cwl_guild:
            return self.cwl_guild.get_role(self._admin_role)
        return None
    @property
    def ticket_listener(self) -> Optional[discord.TextChannel]:
        return self.bot.get_channel(self._ticket_listener)
    
    @property
    def active_war_league_season(self) -> aClashSeason:
        if not self._current_season or pendulum.now() > self.last_season_check.add(minutes=10):
            current = aClashSeason.current()
            if pendulum.now() > current.cwl_end.add(days=20):
                self._current_season = current.next_season()
            else:
                self._current_season = aClashSeason.current()
            self.last_season_check = pendulum.now()
        return self._current_season

    ############################################################
    #####
    ##### COG LOAD / UNLOAD
    #####
    ############################################################
    async def cog_load(self):
        async def load_events():
            while True:
                if getattr(self,'_is_ready',False):
                    break
                await asyncio.sleep(1)

            self.coc_client.add_events(
                self.war_state_change_elo
                )
            self.update_clan_war_loop.start()

        self.banned_users = set(await self.config.banned_users())
        self.ticket_prefix = await self.config.ticket_prefix()
        self._ticket_listener = await self.config.ticket_listener()
        self._cwl_guild = await self.config.master_guild()
        self._cwl_top_role = await self.config.master_role()
        self._admin_role = await self.config.admin_role()

        asyncio.create_task(load_events())
    
    async def cog_unload(self):
        self.update_clan_war_loop.stop()
        self.coc_client.remove_events(
            self.war_state_change_elo
        )
    
    ############################################################
    #####
    ##### COG ASSISTANT FUNCTIONS
    #####
    ############################################################
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
        clans = await self.coc_client.get_war_league_clans()
        return_info = [c.assistant_name_json() for c in clans]
        return f"The following Clans are registered as official Clan War League clans: {return_info}"
    
    async def _assistant_get_league_clan_information(self,clan_tag:str,*args,**kwargs) -> str:
        clan = await self.coc_client.get_league_clan(clan_tag,season=self.active_war_league_season)
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
        find_clan = await self.database.db__clan.find_one(q_doc)
        if not find_clan:
            return f"Could not find a clan with the name or tag `{clan_name_or_tag}`."
        
        league_clan = await self.coc_client.get_league_clan(find_clan['_id'],season=self.active_war_league_season)        
        if not league_clan.is_participating:
            return f"{league_clan.title} is not participating in CWL for {self.active_war_league_season.description}."
        if league_clan.roster_open:
            return f"{league_clan.title}'s CWL Roster has not been finalized and cannot be communicated yet."
        
        if len(league_clan.members) > 0:
            return_info = [p.assistant_cwl_json() for p in league_clan.members]
            unique_users = list(set([p.discord_user for p in league_clan.members]))

            return f"The roster for {league_clan.name} in {self.active_war_league_season.description} has {len(return_info)} players with {len(unique_users)} unique persons. This is the locked in-game roster and cannot be changed. The members are: {return_info}"
        else:            
            return_info = [p.assistant_cwl_json() for p in league_clan.participants]
            unique_users = list(set([p.discord_user for p in league_clan.participants]))

            return f"The roster for {league_clan.name} in {self.active_war_league_season.description} has {len(return_info)} players with {len(unique_users)} unique persons. This is a pre-start roster and might be subject to changes. The members are: {return_info}"

    async def _assistant_get_user_participation_information(self,user:discord.Member,*args,**kwargs) -> str:
        registered_accounts = await self.coc_client.get_league_players(
            season=self.active_war_league_season,
            discord_user=user.id,
            registered=True)
    

        if len(registered_accounts) == 0:
            return f"{user.display_name} does not have any accounts registered in CWL for {self.active_war_league_season.description}."
        
        base_info = [p.assistant_cwl_json() for p in registered_accounts]
        return_info = []
        for p in base_info:
            if len(p.get('roster_clan','')) > 0:
                clan = await self.coc_client.get_clan(p['roster_clan'])
                p['roster_clan'] = clan.assistant_name_json()
            return_info.append(p)

        return f"{user.display_name}'s registered accounts for {self.active_war_league_season.description} are: {return_info}"

    ############################################################
    #####
    ##### COMMAND: MYCWL
    #####
    ############################################################
    @commands.command(name="mycwl")
    @commands.guild_only()
    async def cmd_mycwl(self,ctx:commands.Context):
        """
        Manage your CWL Signup/Rosters/Stats.

        Automatically provides options depending on the current state of CWL.
        Defaults to the currently running CWL Season.
        """
        
        member = await aMember(ctx.author.id)
        cwlmenu = CWLPlayerMenu(ctx,self.active_war_league_season,member)

        if pendulum.now() < self.active_war_league_season.cwl_start:
            if ctx.author.id in self.banned_users:
                await ctx.reply("You have been banned from participating in CWL.")
                return
            await cwlmenu.start_signup()
        else:
            await cwlmenu.show_live_cwl()

    @app_commands.command(name="mycwl",
        description="Manage your CWL Signups, Rosters, Stats.")
    @app_commands.guild_only()
    async def appcmd_mycwl(self,interaction:discord.Interaction):
        
        await interaction.response.defer()

        member = await aMember(interaction.user.id)
        cwlmenu = CWLPlayerMenu(interaction,self.active_war_league_season,member)

        if pendulum.now() < self.active_war_league_season.cwl_start.subtract(days=1): 
            if interaction.user.id in self.banned_users:
                await interaction.edit_original_response(content="You have been banned from participating in CWL.")
                return
            await cwlmenu.start_signup()
        else:
            await cwlmenu.show_live_cwl()

    ############################################################
    #####
    ##### COMMAND GROUP: CWL SET
    ##### Only available as text command
    ############################################################
    @commands.group(name="cwlset")
    @commands.is_owner()
    @commands.guild_only()
    async def cmdgroup_cwlset(self,ctx:commands.Context):
        """
        Command group for setting up the CWL Module.
        """
        if not ctx.invoked_subcommand:
            pass
    
    ##################################################
    ### CWLSET / GUILD
    ##################################################    
    @cmdgroup_cwlset.command(name="guild")
    @commands.is_owner()
    @commands.guild_only()
    async def subcmd_cwlset_guild(self,ctx:commands.Context,guild_id:int):
        """
        Set the Master Guild for the CWL Module.
        """

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return await ctx.reply(f"Guild not found.")
        
        await self.config.master_guild.set(guild_id)
        self._cwl_guild = guild_id
        await ctx.reply(f"CWL Master Guild set to {guild.name}.")
    
    ##################################################
    ### CWLSET / ROLE
    ##################################################    
    @cmdgroup_cwlset.command(name="role")
    @commands.is_owner()
    @commands.guild_only()
    async def subcmd_cwlset_role(self,ctx:commands.Context,role_id:int):
        """
        Set the Master Role for the CWL Module.

        All roles created for CWL will be created under this role.
        """

        if not self.cwl_guild:
            return await ctx.reply(f"Master Guild not set.")
        
        role = self.cwl_guild.get_role(role_id)
        if not role:
            return await ctx.reply(f"Role not found.")
        
        await self.config.master_role.set(role_id)
        self._cwl_top_role = role_id
        await ctx.reply(f"Master Role set to {role.name}.")
    
    ##################################################
    ### CWLSET / ADMIN
    ##################################################    
    @cmdgroup_cwlset.command(name="admin")
    @commands.is_owner()
    @commands.guild_only()
    async def subcmd_cwlset_admin(self,ctx:commands.Context,role_id:int):
        """
        Set the Admin Role for the CWL Module.
        """

        if not self.cwl_guild:
            return await ctx.reply(f"Master Guild not set.")

        role = self.cwl_guild.get_role(role_id)
        if not role:
            return await ctx.reply(f"Role not found.")
        
        await self.config.admin_role.set(role_id)
        self._admin_role = role_id
        await ctx.reply(f"CWL Admin Role set to {role.name}.")
    
    ##################################################
    ### CWLSET / LISTENER
    ##################################################    
    @cmdgroup_cwlset.command(name="listener")
    @commands.is_owner()
    @commands.guild_only()
    async def subcmd_cwlset_listener(self,ctx:commands.Context,channel_id:int):
        """
        Set the Listener Channel for the CWL Module.
        """

        if not self.cwl_guild:
            return await ctx.reply(f"Master Guild not set.")

        channel = self.cwl_guild.get_channel(channel_id)
        if not channel:
            return await ctx.reply(f"Channel not found.")
        
        await self.config.ticket_listener.set(channel_id)
        self._ticket_listener = channel_id
        await ctx.reply(f"Ticket Listener set to {channel.name}.")

    ##################################################
    ### CWLSET / PREFIX
    ##################################################    
    @cmdgroup_cwlset.command(name="prefix")
    @commands.is_owner()
    @commands.guild_only()
    async def subcmd_cwlset_prefix(self,ctx:commands.Context,prefix:str):
        """
        Set the Listener Prefix for the CWL Module.
        """

        if not self.cwl_guild:
            return await ctx.reply(f"Master Guild not set.")
        
        await self.config.ticket_prefix.set(prefix)
        self.ticket_prefix = prefix
        await ctx.reply(f"Ticket Prefix set to {prefix}.")
    
    ############################################################
    #####
    ##### GROUP: CWL MASTER COMMANDS
    #####
    ############################################################
    @commands.group(name="cwl")
    @commands.guild_only()
    async def cmdgroup_cwl(self,ctx):
        """
        Group for CWL-related Commands.

        **This is a command group. To use the sub-commands below, follow the syntax: `$cwl [sub-command]`.**
        """
        if not ctx.invoked_subcommand:
            pass

    appgroup_cwl = app_commands.Group(
        name="cwl",
        description="Group for CWL commands. Equivalent to [p]cwl.",
        guild_only=True
        )
    
    ##################################################
    ### CWL / INFO
    ##################################################
    async def _cwl_info_embed(self,context:Union[commands.Context,discord.Interaction]) -> List[discord.Embed]:
        text = ""
        text += "As part of The Assassins Guild, we collaborate with other Guild Clans and the Guild Community in the monthly Clan War Leagues. "
        text += "When you participate in Clan War Leagues with us, you'll get to play at a League level suited to your Townhall Level and ability. "
        text += "You'll also get to play with other members of the Guild Community, and get to know other players in the Guild. "
        text += "\n\n"
        text += "The information below details what a typical CWL season looks like. "
        text += "\n## Registrations"
        text += "\nIn order to participate in CWL, you must first register. Registration is done on a per-account-basis, and you are not required to register every account. "
        text += "If you wish to register with an account, link the account to your profile with `/profile`. "
        text += "\n\n"
        text += f"Registration typically opens on/around the 15th of every month, and lasts until the last day of the month. You will be able to manage your registrations through <@{self.bot.user.id}>, with the `/mycwl` command."
        text += "\n\n"
        text += "If you wish to be notified when registrations open, subscribe to the `@CWL News` role in the [Guild Server](https://discord.gg/assassinsguild)."
        text += "\n## League Groups"
        text += "\nWhen registering, you will be required to register to a preferred League Group. This is an **indicative** preference, and represents the highest league you are willing to play in. **It is not a guarantee that you will play in that League.** "
        text += "\n### Example: How League Groups Work"
        text += "\nIf you sign up for Master League II:"
        text += "\n- You will not be rostered in a Champion League III clan."
        text += "\n- You can be rostered for a Crystal League III clan."
        text += "\n## Rostering"
        text += "\nBased on your preferred League Group and War Rank, you will be rostered into one of our CWL Clans for the CWL period."
        text += "\n\n"
        text += "> **You will be required to move to your rostered CWL Clan for the duration of the CWL period.** "
        text += "\n\nRosters will typically be published 1-2 days before the start of CWL. You will be able to view your roster with the `/mycwl` command."
        text += "\n\n**Once rosters are published, your registration cannot be modified further. If you cannot participate in CWL, please contact a Leader immediately.**"
        text += "\n## War Leaders, Rules, Bonuses & Penalties"
        text += "\nEvery CWL Clan will be assigned one or more War Leader(s) to coordinate and organize CWL for that Clan. You are **expected** to follow the instructions of your War Leader(s)."
        text += "\n- **War Rules**: Regular Clan War Rules will not apply during CWL. Your War Leader(s) will define and set rules that apply during CWL."
        text += "\n- **CWL Bonuses**: War Leaders have full decision making authority in administering bonuses for CWL Medals."
        text += "\n- **Penalties**: If necessary, War Leaders may mete out penalties for undesirable behaviour, up to and including a full and permanent ban from future CWLs."
        text += "\n\nGuild Staff reserve the right to enforce any action without reason. All enforcement actions are irreversible."
        text += "\n## Useful Commands"
        text += "\n`/mycwl` - Manage your CWL Signups, Rosters, Stats."
        text += "\n`/cwl clan roster` - Shows a League Clan's CWL Roster."
        text += "\n`/cwl clan group` - Shows a League Clan's CWL Group."

        cwl_embed = await clash_embed(
            context=context,
            title=f"Clan War Leagues with {context.guild.name}",
            message=text
            )
        
        text2 = ""
        text2 += f"You might see the following icon on some of your player profiles: {EmojisUI.ELO} . This is your War Rank."
        text2 += "\n\n"
        text2 += "The War Rank System is designed to provide an objective ranking of your capability in Clan Wars and CWL. "
        text2 += "War Ranks are primarily used for rostering players of equal Townhall and Hero Levels. The higher your War Rank, the more likely you will be rostered as close to your highest preferred League as possible."
        text2 += "\n\n"
        text2 += "### __Rank Points are gained by playing in CWL with our official CWL clans.__"
        text2 += "\n- You lose -3 rank points for every war you are rostered in."
        text2 += "\n- You gain: +1 for a 1-star hit, +2 for a 2-star hit, +4 for a 3-star hit."
        text2 += "\n- For a hit against a different TH level, you gain/lose points based on the difference in TH levels."
        text2 += "\n- Your final rank point gain/loss will be adjusted by the average Rank of your War Clan."
        text2 += "\n\n"
        text2 += "### __You can also gain Rank Points from regular wars with our Guild Clans.__"
        text2 += "\n- Only attacks against equivalent TH opponents count."
        text2 += "\n- You gain/lose: -1 for a 0-star hit, -0.75 for a 1-star hit, -0.25 for a 2-star hit, +0.5 for a 3-star hit."

        rank_embed = await clash_embed(
            context=context,
            title=f"The War Rank System",
            message=text2
            )
        return [cwl_embed,rank_embed]

    @cmdgroup_cwl.command(name="info") 
    @commands.guild_only()
    async def subcmd_cwl_info(self,ctx:commands.Context):
        """
        Get information about how CWL is run.
        """

        embed = await self._cwl_info_embed(ctx)
        await ctx.reply(embeds=embed)
    
    @appgroup_cwl.command(name="info",
        description="Get information about how CWL is run.")
    @app_commands.guild_only()
    async def appcmd_cwl_info(self,interaction:discord.Interaction):
        
        await interaction.response.defer()

        embed = await self._cwl_info_embed(interaction)
        await interaction.followup.send(embeds=embed)
    
    ##################################################
    ### CWL / SETUP
    ##################################################
    @cmdgroup_cwl.command(name="setup")
    @commands.check(is_cwl_admin)
    @commands.guild_only()
    async def subcmd_cwl_setup(self,ctx):
        """
        Admin home for the CWL Season.

        Provides an overview to Admins of the current CWL Season, and provides toggles to control various options.
        """

        menu = CWLSeasonSetup(ctx,self.active_war_league_season)
        await menu.start()
    
    @appgroup_cwl.command(name="setup",
        description="Setup CWL for a season.")
    @app_commands.check(is_cwl_admin)
    @app_commands.guild_only()
    async def appcmd_cwl_setup(self,interaction:discord.Interaction):
        
        await interaction.response.defer()

        season = self.active_war_league_season
        menu = CWLSeasonSetup(interaction,season)
        await menu.start()
    
    ##################################################
    ### CWL / BAN
    ##################################################
    @cmdgroup_cwl.command(name="ban", aliases=["banuser","ban-user"])
    @commands.check(is_cwl_admin)
    @commands.guild_only()
    async def subcmd_cwl_banuser(self,ctx:commands.Context,user:discord.Member):
        """
        Bans a user from participating in future CWL.
        """

        self.banned_users.add(user.id)
        await self.config.banned_users.set(list(self.banned_users))
        await ctx.reply(f"{user.display_name} `{user.id}` is now banned from participating in future CWL.")
    
    @appgroup_cwl.command(name="ban",
        description="Ban a user from participating in future CWL.")
    @app_commands.describe(user="The user to ban.")
    @app_commands.check(is_cwl_admin)
    @app_commands.guild_only()
    async def appcmd_cwl_banuser(self,interaction:discord.Interaction,user:discord.Member):
        
        await interaction.response.defer()

        self.banned_users.add(user.id)
        await self.config.banned_users.set(list(self.banned_users))
        await interaction.followup.send(
            content=f"{user.display_name} `{user.id}`is now banned from participating in future CWL."
            )
    
    ##################################################
    ### CWL / UNBAN
    ##################################################
    @cmdgroup_cwl.command(name="unban", aliases=["unbanuser","unban-user"])
    @commands.check(is_cwl_admin)
    @commands.guild_only()
    async def subcmd_cwl_unbanuser(self,ctx:commands.Context,user:discord.Member):
        """
        Unbans a user from CWL participation.
        """
        if user.id not in self.banned_users:
            return await ctx.reply(f"{user.display_name} `{user.id}` is currently not banned from participating in future CWL.")

        self.banned_users.remove(user.id)
        await self.config.banned_users.set(list(self.banned_users))
        await ctx.reply(f"{user.display_name} `{user.id}` is now unbanned from participating in future CWL.")
    
    @appgroup_cwl.command(name="unban",
        description="Unban a user from participating in future CWL.")
    @app_commands.describe(user="The user to unban.")
    @app_commands.check(is_cwl_admin)
    @app_commands.guild_only()
    async def appcmd_cwl_unbanuser(self,interaction:discord.Interaction,user:discord.Member):
        
        await interaction.response.defer()
        if user.id not in self.banned_users:
            await interaction.followup.send(
                content=f"{user.display_name} `{user.id}` is currently not banned from participating in future CWL."
                )
            return

        self.banned_users.remove(user.id)
        await self.config.banned_users.set(list(self.banned_users))
        await interaction.followup.send(
            content=f"{user.display_name} `{user.id}` is now unbanned from future CWL."
            )
    
    ############################################################
    #####
    ##### GROUP: CWL CLAN COMMANDS
    #####
    ############################################################
    @cmdgroup_cwl.group(name="clan")
    @commands.guild_only()
    async def subcmdgrp_cwl_clan(self,ctx:commands.Context):
        """
        Manage Clans for CWL.
        """
        if not ctx.invoked_subcommand:
            pass

    appgroup_cwl_clan = app_commands.Group(
        name="clan",
        description="Manage Clans for CWL.",
        parent=appgroup_cwl,
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
        clans = await self.coc_client.get_war_league_clans()
        c_iter = AsyncIter(clans)
        async for clan in c_iter:
            embed.add_field(
                name=f"{clan.title}",
                value=f"**League:** {EmojisLeagues.get(clan.war_league_name)} {clan.war_league_name}"
                    + f"\n\u200b",
                inline=False
                )            
        return embed
    
    @subcmdgrp_cwl_clan.command(name="list")
    @commands.check(is_cwl_admin)
    @commands.guild_only()
    async def subcmd_cwl_clan_list(self,ctx:commands.Context):
        """
        List all Clans available for CWL.

        Effectively, this is the "master list" of clans available for CWL, and will be included for tracking/reporting.

        To add a Clan to the list, use `/cwl clan add`.
        """

        embed = await self.war_league_clan_list_embed(ctx)
        await ctx.reply(embed=embed)
    
    @appgroup_cwl_clan.command(name="list",
        description="List all Clans available for CWL.",)
    @app_commands.check(is_cwl_admin)
    @app_commands.guild_only()
    async def appcmd_cwl_clan_list(self,interaction:discord.Interaction):
        
        await interaction.response.defer()
        embed = await self.war_league_clan_list_embed(interaction)
        await interaction.followup.send(embed=embed)
    
    ##################################################
    ### CWL / CLAN / ADD
    ##################################################
    async def add_war_league_clan_helper(self,context:Union[discord.Interaction,commands.Context],clan_tag:str):
        clan = await self.coc_client.get_clan(clan_tag)

        await clan.add_to_war_league()
        embed = await clash_embed(
            context=context,
            message=f"**{clan.title}** is now added as a CWL Clan.",
            success=True
            )
        return embed

    @subcmdgrp_cwl_clan.command(name="add")
    @commands.check(is_cwl_admin)
    @commands.guild_only()
    async def subcmd_cwl_clan_add(self,ctx:commands.Context,clan_tag:str):
        """
        Add a Clan as a CWL Clan.

        This adds the Clan to the master list. It does not add the Clan to the current CWL Season. To enable a Clan for a specific season, use `/cwl setup`.
        """        
        embed = await self.add_war_league_clan_helper(ctx,clan_tag)
        await ctx.reply(embed=embed)
    
    @appgroup_cwl_clan.command(name="add",
        description="Add a Clan to the available CWL Clans list.")
    @app_commands.check(is_cwl_admin)
    @app_commands.guild_only()
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="The Clan to add as a CWL Clan.")
    async def appcmd_cwl_clan_add(self,interaction:discord.Interaction,clan:str):
        
        await interaction.response.defer()
        embed = await self.add_war_league_clan_helper(interaction,clan)
        await interaction.edit_original_response(embed=embed)
    
    ##################################################
    ### CWL / CLAN / REMOVE
    ##################################################
    @subcmdgrp_cwl_clan.command(name="remove")
    @commands.is_owner()
    @commands.guild_only()
    async def subcmd_cwl_clan_remove(self,ctx:commands.Context,clan_tag:str):
        """
        Remove a Clan from the available CWL Clans list.

        Owner-only to prevent strange things from happening.
        """
        
        clan = await self.coc_client.get_clan(clan_tag)
        await clan.remove_from_war_league()
        embed = await clash_embed(
            context=ctx,
            message=f"**{clan.title}** is now removed from the CWL Clan List.",
            success=False
            )
        await ctx.reply(embed=embed)
    
    ##################################################
    ### CWL / CLAN / ROSTER
    ##################################################
    @subcmdgrp_cwl_clan.command(name="roster")
    @commands.guild_only()
    async def subcmd_cwl_clan_roster(self,ctx,clan_tag:str):
        """
        View the Roster for a CWL Clan.
        """

        league_clan = await self.coc_client.get_league_clan(clan_tag,self.active_war_league_season)

        if not league_clan.is_participating:
            embed = await clash_embed(
                context=ctx,
                message=f"**{league_clan.title}** is not participating in Guild CWL for {self.active_war_league_season.description}.",
                success=False
                )
            return await ctx.reply(embed=embed,view=None)
        
        menu = CWLRosterDisplayMenu(ctx,league_clan)
        await menu.start()
    
    @appgroup_cwl_clan.command(name="roster",
        description="View a CWL Clan's current Roster.")
    @app_commands.describe(
        clan="The Clan to view. Only registered CWL Clans are eligible.")
    @app_commands.guild_only()
    @app_commands.autocomplete(clan=autocomplete_season_league_clans)    
    async def appcmd_cwl_clan_roster(self,interaction:discord.Interaction,clan:str):
        
        await interaction.response.defer()

        league_clan = await self.coc_client.get_league_clan(clan,self.active_war_league_season)

        if not league_clan.is_participating:
            embed = await clash_embed(
                context=interaction,
                message=f"**{league_clan.title}** is not participating in Guild CWL for {self.active_war_league_season.description}.",
                success=False
                )
            return await interaction.edit_original_response(embed=embed,view=None)

        menu = CWLRosterDisplayMenu(interaction,league_clan)
        await menu.start()
    
    ##################################################
    ### CWL / CLAN / LEAGUE GROUP
    ##################################################
    @subcmdgrp_cwl_clan.command(name="group")
    @commands.guild_only()
    async def subcmd_cwl_clan_group(self,ctx:commands.Context,clan_tag:str):
        """
        View the League Group for a Clan.
        """

        clan = await self.coc_client.get_clan(clan_tag)
        league_group = await self.coc_client.get_league_group(clan_tag,season=self.active_war_league_season)

        if not league_group:
            embed = await clash_embed(
                context=ctx,
                message=f"**{clan.title}** has not started CWL for {self.active_war_league_season.description}."
                    + "\n\nIf you're looking for the Clan Roster, use `/cwl clan roster` instead.",
                success=False
                )
            return await ctx.reply(embed=embed,view=None)

        menu = CWLClanGroupMenu(ctx,league_group)
        await menu.start()
    
    @appgroup_cwl_clan.command(name="group",
        description="View a CWL Clan's current League Group.")
    @app_commands.describe(
        clan="The Clan to view. Only registered CWL Clans are tracked.")
    @app_commands.guild_only()
    @app_commands.autocomplete(clan=autocomplete_season_league_clans)    
    async def appcmd_cwl_clan_group(self,interaction:discord.Interaction,clan:str):

        await interaction.response.defer()

        get_clan = await self.coc_client.get_clan(clan)
        league_group = await self.coc_client.get_league_group(clan,season=self.active_war_league_season)

        if not league_group:
            embed = await clash_embed(
                context=interaction,
                message=f"**{get_clan.title}** has not started CWL for {self.active_war_league_season.description}."
                    + "\n\nIf you're looking for the Clan Roster, use `/cwl clan roster` instead.",
                success=False
                )
            return await interaction.edit_original_response(embed=embed,view=None)
        
        menu = CWLClanGroupMenu(interaction,league_group)
        await menu.start()
    
    ############################################################
    #####
    ##### GROUP: CWL ROSTER COMMANDS
    #####
    ############################################################
    @cmdgroup_cwl.group(name="roster")
    @commands.check(is_cwl_admin)
    @commands.guild_only()
    async def subcmdgrp_cwl_roster(self,ctx):
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

    appgroup_cwl_roster = app_commands.Group(
        name="roster",
        description="Manage CWL Rosters",
        parent=appgroup_cwl,
        guild_only=True
        )
    
    ##################################################
    ### CWL / ROSTER / SETUP
    ##################################################
    @subcmdgrp_cwl_roster.command(name="setup")
    @commands.check(is_cwl_admin)
    @commands.guild_only()
    async def subcmd_cwl_roster_setup(self,ctx:commands.Context,clan_tag:str):
        """
        Setup a Roster for a Clan.

        This is an interactive menu with various options to quickly set up a roster. Use the in-menu help buttons.

        Always defaults to the next open CWL Season.
        """
            
        league_clan = await self.coc_client.get_league_clan(clan_tag,self.active_war_league_season)

        if not league_clan.is_participating:
            embed = await clash_embed(
                context=ctx,
                message=f"**{league_clan.title}** is not participating in CWL for {self.active_war_league_season.description}.",
                success=False
                )
            return await ctx.reply(embed=embed,view=None)
        
        menu = CWLRosterMenu(ctx,self.active_war_league_season,league_clan)
        await menu.start()
    
    @appgroup_cwl_roster.command(name="setup",
        description="Setup a CWL Roster for a Clan. Defaults to the next open CWL Season.")
    @app_commands.check(is_cwl_admin)
    @app_commands.guild_only()
    @app_commands.autocomplete(clan=autocomplete_season_league_clans)
    @app_commands.describe(clan="The Clan to setup for.")
    async def appcmd_cwl_roster_setup(self,interaction:discord.Interaction,clan:str):
        
        await interaction.response.defer()

        league_clan = await self.coc_client.get_league_clan(clan,season=self.active_war_league_season)

        if not league_clan.is_participating:
            embed = await clash_embed(
                context=interaction,
                message=f"**{league_clan.title}** is not participating in CWL for {self.active_war_league_season.description}.",
                success=False
                )
            return await interaction.edit_original_response(embed=embed,view=None)

        menu = CWLRosterMenu(interaction,self.active_war_league_season,league_clan)
        await menu.start()
    
    ##################################################
    ### CWL / ROSTER / OPEN
    ##################################################
    @subcmdgrp_cwl_roster.command(name="open")
    @commands.is_owner()
    @commands.guild_only()
    async def subcmd_cwl_roster_open(self,ctx:commands.Context,clan_tag:str):
        """
        Force open a CWL Clan's Roster.
        """
        league_clan = await self.coc_client.get_league_clan(clan_tag,season=self.active_war_league_season)
        await league_clan.open_roster()
        await ctx.tick()
    
    ##################################################
    ### CWL / ROSTER / ADD
    ##################################################
    async def admin_add_player_helper(self,
        context:Union[discord.Interaction,commands.Context],
        clan_tag:str,
        player_tag:str):

        reopen = False        
        league_clan = await self.coc_client.get_league_clan(clan_tag,season=self.active_war_league_season)

        if not league_clan.is_participating:
            embed = await clash_embed(
                context=context,
                message=f"**{league_clan.title}** is not participating in CWL for {self.active_war_league_season.description}.",
                success=False
                )
            return embed
        
        if league_clan.cwl_started:
            embed = await clash_embed(
                context=context,
                message=f"{self.active_war_league_season.description} CWL has already started for {league_clan.title}.",
                success=False
                )
            return embed
        
        league_player = await self.coc_client.get_league_player(player_tag,season=self.active_war_league_season)
        original_tag = league_player.roster_clan_tag
        await league_player.admin_add(league_clan)

        original_clan = await self.coc_client.get_league_clan(original_tag,season=self.active_war_league_season) if original_tag else None
        if original_clan:
            if len(original_clan.participants) < 15 and original_clan.roster_open == False:
                reopen = True
                await original_clan.open_roster()

        embed = await clash_embed(
            context=context,
            message=f"**{league_player.title}** has been added to CWL."
                + f"\n\n> Clan: {league_player.roster_clan.title}"
                + f"\n> Discord: <@{league_player.discord_user}>"
                + (f"\n\n{original_clan.clean_name}'s Roster has been re-opened. ({len(original_clan.participants)} players remain)" if reopen else ""),
            success=True
            )
        return embed
    
    @subcmdgrp_cwl_roster.command(name="add")
    @commands.check(is_cwl_admin)
    @commands.guild_only()
    async def subcmd_cwl_roster_add(self,ctx:commands.Context,clan_tag:str,player_tag:str):
        """
        Admin add a Player to a Roster.

        This works even if the roster has been finalized. If the player is currently not registered, this will auto-register them into CWL.

        **Important**
        > - If the player is currently not registered, this will make them appear as if they've registered without a League Group.
        > - If the player is already in a finalized roster, this will remove the player from that roster. If this lowers the roster below 15 players, the roster will be re-opened.
        """
        
        embed = await self.admin_add_player_helper(ctx,clan_tag,player_tag)
        await ctx.reply(embed=embed)
    
    @appgroup_cwl_roster.command(name="add",
        description="Add a Player to a CWL Roster. Automatically registers the Player, if not registered.")
    @app_commands.check(is_cwl_admin)
    @app_commands.guild_only()
    @app_commands.autocomplete(clan=autocomplete_season_league_clans)
    @app_commands.autocomplete(player=autocomplete_players)
    @app_commands.describe(
        clan="The Clan to add the player to. Must be an active CWL Clan.",
        player="The Player to add to the Roster.")
    async def appcmd_cwl_roster_add(self,interaction:discord.Interaction,clan:str,player:str):
        
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
        league_player = await self.coc_client.get_league_player(player_tag,season=self.active_war_league_season)
        
        if getattr(league_player,'league_clan_tag',None):
            league_clan = await self.coc_client.get_league_clan(league_player.league_clan_tag,season=self.active_war_league_season)
            embed = await clash_embed(
                context=context,
                message=f"**{league_player}** is already in CWL with **{league_clan.title}**.",
                success=False
                )
            return embed

        original_clan_tag = league_player.roster_clan_tag
        await league_player.admin_remove()

        original_clan = await self.coc_client.get_league_clan(original_clan_tag,season=self.active_war_league_season) if original_clan_tag else None
        if original_clan:            
            if len(original_clan.participants) < 15 and original_clan.roster_open == False:
                reopen = True
                await original_clan.open_roster()

        embed = await clash_embed(
            context=context,
            message=f"**{league_player.title}** has been removed from {self.active_war_league_season.description} CWL."
                + (f"\n\n{original_clan.name}'s Roster has been re-opened. ({len(original_clan.participants)} players remain)" if reopen else ""),
            success=True
            )
        return embed
    
    @subcmdgrp_cwl_roster.command(name="remove")
    @commands.check(is_cwl_admin)
    @commands.guild_only()
    async def subcmd_cwl_roster_remove(self,ctx:commands.Context,player_tag:str):
        """
        Admin remove a Player from CWL.

        This works even if the roster has been finalized. If the player is currently in a roster, this will auto-remove them from CWL.

        **Important**
        If the player is in a finalized roster, and this lowers the roster below 15 players, the roster will be re-opened.
        """
            
        embed = await self.admin_remove_player_helper(ctx,player_tag)
        await ctx.reply(embed=embed)
    
    @appgroup_cwl_roster.command(name="remove",
        description="Removes a Player from a CWL Roster. Automatically unregisters the Player, if registered.")
    @app_commands.check(is_cwl_admin)
    @app_commands.guild_only()
    @app_commands.autocomplete(player=autocomplete_players)
    @app_commands.describe(player="The Player to remove from CWL.")
    async def appcmd_cwl_roster_remove(self,interaction:discord.Interaction,player:str):
        
        await interaction.response.defer()

        embed = await self.admin_remove_player_helper(interaction,player)
        return await interaction.edit_original_response(embed=embed)

    ##################################################
    ### CWL / ROSTER / EXPORT
    ##################################################
    @subcmdgrp_cwl_roster.command(name="export")
    @commands.check(is_cwl_admin)
    @commands.guild_only()
    async def subcmd_cwl_roster_export(self,ctx:commands.Context):
        """
        Exports all Signups (and Roster information) to Excel.

        Defaults to the currently open CWL Season.
        """

        wait_msg = await ctx.reply("Exporting Data... please wait.")

        rp_file = await generate_cwl_roster_export(self.active_war_league_season)
        
        if not rp_file:
            return await wait_msg.edit(f"I couldn't export the CWL Roster for {self.active_war_league_season.description}. Were you trying to export an already-completed CWL Season?")
        
        await wait_msg.delete()
        await ctx.reply(
            content=f"Here is the CWL Roster for {self.active_war_league_season.description}.",
            file=discord.File(rp_file))
    
    @appgroup_cwl_roster.command(name="export",
        description="Exports all Signups (and Roster information) to Excel. Uses the currently open CWL Season.")
    @app_commands.check(is_cwl_admin)
    @app_commands.guild_only()
    async def appcmd_cwl_roster_export(self,interaction:discord.Interaction):
        
        await interaction.response.defer()

        rp_file = await generate_cwl_roster_export(self.active_war_league_season)
        
        if not rp_file:
            return await interaction.edit_original_response(content=f"I couldn't export the CWL Roster for {self.active_war_league_season.description}. Were you trying to export an already-completed CWL Season?")
        
        await interaction.followup.send(
            content=f"Here is the CWL Roster for {self.active_war_league_season.description}.",
            file=discord.File(rp_file))
    
    ############################################################
    #####
    ##### WAR UPDATE LOOP TASK
    #####
    ############################################################    
    @tasks.loop(minutes=10)
    async def update_clan_war_loop(self):        
        async with self._loop_lock:
            if self.coc_client.maintenance:
                return            
            
            alliance_clans = await self.coc_client.get_alliance_clans()
            self.coc_client.add_war_updates(*[c.tag for c in alliance_clans])
    
    ############################################################
    #####
    ##### WAR ELO TASKS
    #####
    ############################################################
    @coc.WarEvents.state_change()
    async def war_state_change_elo(self,war:bClanWar):
        if war.state == WarState.WAR_ENDED:

            if war.type == ClanWarType.CWL:
                await self.cwl_elo_adjustment(war.clans[0],war)
                await self.cwl_elo_adjustment(war.clans[1],war)
            
            if war.type == ClanWarType.RANDOM:
                await self.war_elo_adjustment(war.clans[0],war)
                await self.war_elo_adjustment(war.clans[1],war)

    async def cwl_elo_adjustment(self,clan:bWarClan,war:bClanWar):
        league_group = await self.coc_client.get_league_group(clan_tag=clan.tag,season=self.active_war_league_season)
        if not league_group:
            return        
        
        war_round = league_group.get_round_from_war(war)        
        if war_round == league_group.number_of_rounds:
            league_clan = league_group.get_clan(clan.tag)

            if not league_clan:
                return
            if not league_clan.is_participating:
                return
            
            async def player_elo_adjustment(player:bWarLeaguePlayer,roster_elo:int):
                elo_gain = 0
                elo_multi = roster_elo / player.war_elo
                    
                async for war in league_group.get_wars_for_player(player.tag):
                    elo_gain -= 3
                    elo_gain += [att.elo_effect for att in war.get_member(player.tag).attacks]

                if elo_gain > 0:
                    adj_elo = round(elo_gain * elo_multi,3)
                else:
                    adj_elo = round(elo_gain,3)
                await player.set_elo_change(adj_elo)
                await player.adjust_war_elo(adj_elo)

            participants = AsyncIter(league_clan.participants)
            roster_elo = sum([p.war_elo for p in participants]) / len(league_clan.participants)

            tasks = [player_elo_adjustment(p,roster_elo) async for p in participants]
            await bounded_gather(*tasks)
        
    async def war_elo_adjustment(self,clan:bWarClan,war:bClanWar):        
        if not clan.is_alliance_clan:
            return
        
        async def player_elo_adjustment(player:bWarPlayer):
            elo_gain = 0
            att_iter = AsyncIter(player.attacks)
            async for att in att_iter:
                elo_gain += att.elo_effect
            await player.adjust_war_elo(elo_gain)
        
        p_iter = AsyncIter(clan.members)
        tasks = [player_elo_adjustment(p) async for p in p_iter]
        await bounded_gather(*tasks)
    
    ############################################################
    #####
    ##### CWL CHANNELS
    #####
    ############################################################    
    async def create_clan_channel(self,clan:bWarLeagueClan):
        if not self.ticket_listener:
            raise ValueError("CWL Channel Category is not set.")
        
        league_clan = await self.coc_client.get_league_clan(clan.tag,season=self.active_war_league_season)
        if league_clan.league_channel and league_clan.league_role:
            return
        
        await self.ticket_listener.send(f"--ticket {clan.tag} {clan.name}")

        st = pendulum.now()
        while True:
            now = pendulum.now()
            if now.int_timestamp - st.int_timestamp > 45:
                break

            league_clan = await self.coc_client.get_league_clan(clan.tag,season=self.active_war_league_season)
            if league_clan.league_channel and league_clan.league_role:
                break
        
        if not league_clan.league_channel or not league_clan.league_role:
            raise ValueError("Could not create Clan Channel.")
        
        discord_users = [league_clan.league_role.guild.get_member(p) for p in list(set([p.discord_user for p in league_clan.participants])) if league_clan.league_role.guild.get_member(p)]
        assign_role_tasks = [u.add_roles(league_clan.league_role,reason='CWL Roster Finalized') for u in discord_users]
        await bounded_gather(*assign_role_tasks,limit=1)

        fetch_players = [p async for p in self.coc_client.get_players([p.tag for p in league_clan.participants])]
        fetch_players.sort(key=lambda x:(x.town_hall.level,x.hero_strength,x.exp_level),reverse=True)        
        participants_20 = fetch_players[:20]
        participants_40 = fetch_players[20:40]

        embeds = []
        if len(participants_20) > 0:
            embed_1 = await clash_embed(
                context=self.bot,
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
                context=self.bot,
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
        if not isinstance(channel, discord.TextChannel):
            return
        
        clan_tag = None
        await asyncio.sleep(1)
        
        async for message in channel.history(limit=1,oldest_first=True):
            for embed in message.embeds:
                if embed.footer.text == "Clan War Leagues":
                    clan_tag = embed.description.split()[0]
                    break

        if not clan_tag:
            return
        
        league_clan = await self.coc_client.get_league_clan(clan_tag,season=self.active_war_league_season)
        league_role = await channel.guild.create_role(
            reason="CWL Channel Created.",
            name=f"CWL {self.active_war_league_season.short_description} {league_clan.name}"
            )

        await channel.edit(name=f"cwl・{league_clan.name}")
        await league_clan.set_league_discord(channel,league_role)

        clan = await self.coc_client.get_clan(clan_tag)

        await EventReminder.create_war_reminder(
            clan=clan,
            channel=channel,
            war_types=[ClanWarType.CWL],
            interval=[16,12,8,6,4,3,2,1]
            )
    
    @commands.Cog.listener("on_guild_channel_delete")
    async def league_channel_ticket_delete_listener(self,channel:discord.TextChannel):

        query_league_clan_by_channel = {'league_channel': channel.id}
        db_query = await self.database.db__war_league_clan.find_one(query_league_clan_by_channel)

        if db_query:
            league_role = channel.guild.get_role(db_query['league_role'])
            if league_role:
                await league_role.delete(reason="CWL Channel Deleted.")