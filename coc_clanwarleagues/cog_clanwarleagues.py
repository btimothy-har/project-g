import coc
import discord
import asyncio
import pendulum
import asyncio
import re

from typing import *

from redbot.core import Config, commands, app_commands
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter, bounded_gather

from coc_main.api_client import BotClashClient, aClashSeason, ClashOfClansError
from coc_main.cog_coc_client import aClan, aClanWar
from coc_main.coc_objects.events.clan_war_leagues import WarLeagueGroup, WarLeaguePlayer, WarLeagueClan
from coc_main.coc_objects.events.clan_war import aWarPlayer

from coc_main.discord.member import aMember

from coc_main.utils.components import clash_embed, ClanLinkMenu
from coc_main.utils.constants.coc_emojis import EmojisLeagues, EmojisTownHall
from coc_main.utils.constants.coc_constants import WarState, ClanWarType
from coc_main.utils.autocomplete import autocomplete_clans, autocomplete_players

from .checks import is_cwl_admin
from .autocomplete import autocomplete_all_league_clans, autocomplete_season_league_participants, autocomplete_season_league_clans

from coc_data.tasks.war_tasks import ClanWarLoop

from .components.cwl_player import CWLPlayerMenu
from .components.cwl_setup import CWLSeasonSetup
from .components.cwl_view_roster import CWLRosterDisplayMenu
from .components.cwl_league_group import CWLClanGroupMenu
from .components.cwl_roster_setup import CWLRosterMenu

from .components.cwl_roster_export import generate_cwl_roster_export

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

    def __init__(self,bot:Red):
        self.bot = bot
        
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

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"

    ############################################################
    #####
    ##### COG LOAD / UNLOAD
    #####
    ############################################################    
    async def cog_load(self):
        async def load_events():
            while True:
                if getattr(bot_client,'_is_initialized',False):
                    break
                await asyncio.sleep(1)            
            ClanWarLoop.add_war_end_event(self.cwl_elo_adjustment)
            ClanWarLoop.add_war_end_event(self.war_elo_adjustment)

        self.banned_users = set(await self.config.banned_users())
        self.ticket_prefix = await self.config.ticket_prefix()
        self._ticket_listener = await self.config.ticket_listener()
        self._cwl_guild = await self.config.master_guild()
        self._cwl_top_role = await self.config.master_role()
        self._admin_role = await self.config.admin_role()

        asyncio.create_task(load_events())
    
    async def cog_unload(self):
        ClanWarLoop.remove_war_end_event(self.cwl_elo_adjustment)
        ClanWarLoop.remove_war_end_event(self.war_elo_adjustment)
    
    ############################################################
    #####
    ##### COG PROPERTIES
    #####
    ############################################################    
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
        if pendulum.now() > bot_client.current_season.cwl_end.add(days=4):
            return bot_client.current_season.next_season()
        return bot_client.current_season
    
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
        p_iter = AsyncIter(cwl_participants)
        tasks = [m.finalize(role=league_clan.league_role) async for m in p_iter]
        await bounded_gather(*tasks,limit=1)

        fetch_players = [p async for p in bot_client.coc.get_players([p.tag for p in cwl_participants])]
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
        clans = await bot_client.coc.get_war_league_clans()
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
    #####
    ##### COMMAND HELPERS
    #####
    ############################################################
    async def cog_command_error(self,ctx,error):
        original = getattr(error,'original',None)
        if isinstance(original,coc.NotFound):
            embed = await clash_embed(
                context=ctx,
                message="The Tag you provided doesn't seem to exist.",
                success=False,
                timestamp=pendulum.now()
                )
            await ctx.send(embed=embed)
            return
        elif isinstance(original,coc.GatewayError) or isinstance(original,coc.Maintenance):
            embed = await clash_embed(
                context=ctx,
                message="The Clash of Clans API is currently unavailable.",
                success=False,
                timestamp=pendulum.now()
                )
            await ctx.send(embed=embed)
            return
        elif isinstance(original,ClashOfClansError):
            embed = await clash_embed(
                context=ctx,
                message=f"{original.message}",
                success=False,
                timestamp=pendulum.now()
                )
            await ctx.send(embed=embed)
            return
        await self.bot.on_command_error(ctx,error,unhandled_by_cog=True)

    async def cog_app_command_error(self,interaction,error):
        original = getattr(error,'original',None)
        embed = None
        if isinstance(original,coc.NotFound):
            embed = await clash_embed(
                context=interaction,
                message="The Tag you provided doesn't seem to exist.",
                success=False,
                timestamp=pendulum.now()
                )            
        elif isinstance(original,coc.GatewayError) or isinstance(original,coc.Maintenance):
            embed = await clash_embed(
                context=interaction,
                message="The Clash of Clans API is currently unavailable.",
                success=False,
                timestamp=pendulum.now()
                )            
        elif isinstance(original,ClashOfClansError):
            embed = await clash_embed(
                context=interaction,
                message=f"{original.message}",
                success=False,
                timestamp=pendulum.now()
                )
        if embed:
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed,view=None)
            else:
                await interaction.response.send_message(embed=embed,view=None,ephemeral=True)
            return
    
    ##################################################
    ### MYCWL
    ##################################################
    @commands.command(name="mycwl")
    @commands.guild_only()
    async def cmdgroup_cwl_mycwl(self,ctx:commands.Context):
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
    async def appgroup_cwl_mycwl(self,interaction:discord.Interaction):
        
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
    ##### COMMAND GROUP: CWLSET
    ##### Only available as text command
    ############################################################
    @commands.group(name="cwlset")
    @commands.is_owner()
    @commands.guild_only()
    async def cmdgroup_cwl_cwlset(self,ctx:commands.Context):
        """
        Command group for setting up the CWL Module.
        """
        if not ctx.invoked_subcommand:
            pass
    
    ##################################################
    ### CWLSET / GUILD
    ##################################################    
    @cmdgroup_cwl_cwlset.command(name="guild")
    @commands.is_owner()
    @commands.guild_only()
    async def subcmd_cwl_cwlset_guild(self,ctx:commands.Context,guild_id:int):
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
    @cmdgroup_cwl_cwlset.command(name="role")
    @commands.is_owner()
    @commands.guild_only()
    async def subcmd_cwl_cwlset_role(self,ctx:commands.Context,role_id:int):
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
    @cmdgroup_cwl_cwlset.command(name="admin")
    @commands.is_owner()
    @commands.guild_only()
    async def subcmd_cwl_cwlset_admin(self,ctx:commands.Context,role_id:int):
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
    @cmdgroup_cwl_cwlset.command(name="listener")
    @commands.is_owner()
    @commands.guild_only()
    async def subcmd_cwl_cwlset_listener(self,ctx:commands.Context,channel_id:int):
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
    @cmdgroup_cwl_cwlset.command(name="prefix")
    @commands.is_owner()
    @commands.guild_only()
    async def subcmd_cwl_cwlset_prefix(self,ctx:commands.Context,prefix:str):
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
    async def cmdgroup_cwl_cwl(self,ctx):
        """
        Group for CWL-related Commands.

        **This is a command group. To use the sub-commands below, follow the syntax: `$cwl [sub-command]`.**
        """
        if not ctx.invoked_subcommand:
            pass

    appgroup_cwl_cwl = app_commands.Group(
        name="cwl",
        description="Group for CWL commands. Equivalent to [p]cwl.",
        guild_only=True
        )
    
    ##################################################
    ### CWL / SETUP
    ##################################################
    @cmdgroup_cwl_cwl.command(name="setup")
    @commands.check(is_cwl_admin)
    @commands.guild_only()
    async def subcmd_cwl_setup(self,ctx):
        """
        Admin home for the CWL Season.

        Provides an overview to Admins of the current CWL Season, and provides toggles to control various options.
        """

        menu = CWLSeasonSetup(ctx,self.active_war_league_season)
        await menu.start()
    
    @appgroup_cwl_cwl.command(name="setup",
        description="Setup CWL for a season.")
    @app_commands.check(is_cwl_admin)
    @app_commands.guild_only()
    async def subappcmd_cwl_setup(self,interaction:discord.Interaction):
        
        await interaction.response.defer()

        season = self.active_war_league_season
        menu = CWLSeasonSetup(interaction,season)
        await menu.start()
    
    ##################################################
    ### CWL / BAN
    ##################################################
    @cmdgroup_cwl_cwl.command(name="ban", aliases=["banuser","ban-user"])
    @commands.check(is_cwl_admin)
    @commands.guild_only()
    async def subcmd_cwl_banuser(self,ctx:commands.Context,user:discord.Member):
        """
        Bans a user from participating in future CWL.
        """

        self.banned_users.add(user.id)
        await self.config.banned_users.set(list(self.banned_users))
        await ctx.reply(f"{user.display_name} `{user.id}` is now banned from participating in future CWL.")
    
    @appgroup_cwl_cwl.command(name="ban",
        description="Ban a user from participating in future CWL.")
    @app_commands.describe(user="The user to ban.")
    @app_commands.check(is_cwl_admin)
    @app_commands.guild_only()
    async def subappcmd_cwl_banuser(self,interaction:discord.Interaction,user:discord.Member):
        
        await interaction.response.defer()

        self.banned_users.add(user.id)
        await self.config.banned_users.set(list(self.banned_users))
        await interaction.followup.send(
            content=f"{user.display_name} `{user.id}`is now banned from participating in future CWL."
            )
    
    ##################################################
    ### CWL / UNBAN
    ##################################################
    @cmdgroup_cwl_cwl.command(name="unban", aliases=["unbanuser","unban-user"])
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
    
    @appgroup_cwl_cwl.command(name="unban",
        description="Unban a user from participating in future CWL.")
    @app_commands.describe(user="The user to unban.")
    @app_commands.check(is_cwl_admin)
    @app_commands.guild_only()
    async def subappcmd_cwl_unbanuser(self,interaction:discord.Interaction,user:discord.Member):
        
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
    @cmdgroup_cwl_cwl.group(name="clan")
    @commands.guild_only()
    async def subcmdgroup_cwl_cwlclan(self,ctx:commands.Context):
        """
        Manage Clans for CWL.
        """
        if not ctx.invoked_subcommand:
            pass

    subappgroup_cwl_cwlclan = app_commands.Group(
        name="clan",
        description="Manage Clans for CWL.",
        parent=appgroup_cwl_cwl,
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
        clans = await bot_client.coc.get_war_league_clans()
        c_iter = AsyncIter(clans)
        async for clan in c_iter:
            embed.add_field(
                name=f"{clan.title}",
                value=f"**League:** {EmojisLeagues.get(clan.war_league_name)} {clan.war_league_name}"
                    + f"\n\u200b",
                inline=False
                )            
        return embed
    
    @subcmdgroup_cwl_cwlclan.command(name="list")
    @commands.check(is_cwl_admin)
    @commands.guild_only()
    async def subcmd_cwl_cwlclanlist(self,ctx:commands.Context):
        """
        [Admin-only] List all Clans available for CWL.

        Effectively, this is the "master list" of clans available for CWL, and will be included for tracking/reporting.

        To add a Clan to the list, use `/cwl clan add`.
        """

        embed = await self.war_league_clan_list_embed(ctx)
        await ctx.reply(embed=embed)
    
    @subappgroup_cwl_cwlclan.command(name="list",
        description="List all Clans available for CWL.",)
    @app_commands.check(is_cwl_admin)
    @app_commands.guild_only()
    async def subappcmd_cwl_cwlclanlist(self,interaction:discord.Interaction):
        
        await interaction.response.defer()
        embed = await self.war_league_clan_list_embed(interaction)
        await interaction.followup.send(embed=embed)
    
    ##################################################
    ### CWL / CLAN / ADD
    ##################################################
    async def add_war_league_clan_helper(self,context:Union[discord.Interaction,commands.Context],clan_tag:str):
        clan = await bot_client.coc.get_clan(clan_tag)

        await clan.add_to_war_league()
        embed = await clash_embed(
            context=context,
            message=f"**{clan.title}** is now added as a CWL Clan.",
            success=True
            )
        return embed

    @subcmdgroup_cwl_cwlclan.command(name="add")
    @commands.check(is_cwl_admin)
    @commands.guild_only()
    async def subcmd_cwl_cwlclanadd(self,ctx:commands.Context,clan_tag:str):
        """
        Add a Clan as a CWL Clan.

        This adds the Clan to the master list. It does not add the Clan to the current CWL Season. To enable a Clan for a specific season, use `/cwl setup`.
        """        
        embed = await self.add_war_league_clan_helper(ctx,clan_tag)
        await ctx.reply(embed=embed)
    
    @subappgroup_cwl_cwlclan.command(name="add",
        description="Add a Clan to the available CWL Clans list.")
    @app_commands.check(is_cwl_admin)
    @app_commands.guild_only()
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="The Clan to add as a CWL Clan.")
    async def subappcmd_cwl_cwlclanadd(self,interaction:discord.Interaction,clan:str):
        
        await interaction.response.defer()
        embed = await self.add_war_league_clan_helper(interaction,clan)
        await interaction.edit_original_response(embed=embed)
    
    ##################################################
    ### CWL / CLAN / REMOVE
    ##################################################
    @subcmdgroup_cwl_cwlclan.command(name="remove")
    @commands.is_owner()
    @commands.guild_only()
    async def subcmd_cwl_cwlclanremove(self,ctx:commands.Context,clan_tag:str):
        """
        Remove a Clan from the available CWL Clans list.

        Owner-only to prevent strange things from happening.
        """
        
        clan = await bot_client.coc.get_clan(clan_tag)
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
    @subcmdgroup_cwl_cwlclan.command(name="roster")
    @commands.guild_only()
    async def subcmd_cwl_cwlclanroster(self,ctx,clan_tag:str):
        """
        View the Roster for a CWL Clan.
        """

        league_clan = await WarLeagueClan(clan_tag,self.active_war_league_season)

        if not league_clan.is_participating:
            embed = await clash_embed(
                context=ctx,
                message=f"**{league_clan.title}** is not participating in Guild CWL for {self.active_war_league_season.description}.",
                success=False
                )
            return await ctx.reply(embed=embed,view=None)
        
        menu = CWLRosterDisplayMenu(ctx,league_clan)
        await menu.start()
    
    @subappgroup_cwl_cwlclan.command(name="roster",
        description="View a CWL Clan's current Roster.")
    @app_commands.describe(
        clan="The Clan to view. Only registered CWL Clans are eligible.")
    @app_commands.guild_only()
    @app_commands.autocomplete(clan=autocomplete_season_league_clans)    
    async def subappcmd_cwl_cwlclanroster(self,interaction:discord.Interaction,clan:str):
        
        await interaction.response.defer()

        league_clan = await WarLeagueClan(clan,self.active_war_league_season)

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
    @subcmdgroup_cwl_cwlclan.command(name="group")
    @commands.guild_only()
    async def subcmd_cwl_cwlclangroup(self,ctx:commands.Context,clan_tag:str):
        """
        View the League Group for a CWL Clan.
        """
        
        league_clan = await WarLeagueClan(clan_tag,self.bot_client.current_season)

        if not league_clan.is_participating:
            embed = await clash_embed(
                context=ctx,
                message=f"**{league_clan.title}** is not participating in Guild CWL for {self.bot_client.current_season.description}. You might be able to view their CWL Group with a different bot.",
                success=False
                )
            return await ctx.reply(embed=embed,view=None)

        if not league_clan.league_group_id:
            embed = await clash_embed(
                context=ctx,
                message=f"**{league_clan.title}** has not started CWL for {self.bot_client.current_season.description}."
                    + "\n\nIf you're looking for the Clan Roster, use `/cwl clan roster` instead.",
                success=False
                )
            return await ctx.reply(embed=embed,view=None)

        league_group = await league_clan.get_league_group()        
        menu = CWLClanGroupMenu(ctx,league_group)
        await menu.start()
    
    @subappgroup_cwl_cwlclan.command(name="group",
        description="View a CWL Clan's current League Group.")
    @app_commands.describe(
        clan="The Clan to view. Only registered CWL Clans are tracked.")
    @app_commands.guild_only()
    @app_commands.autocomplete(clan=autocomplete_season_league_clans)    
    async def subappcmd_cwl_cwlclangroup(self,interaction:discord.Interaction,clan:str):

        await interaction.response.defer()

        league_clan = await WarLeagueClan(clan,self.bot_client.current_season)
        if not league_clan.is_participating:
            embed = await clash_embed(
                context=interaction,
                message=f"**{league_clan.title}** is not participating in Guild CWL for {self.bot_client.current_season.description}. You might be able to view their CWL Group with a different bot.",
                success=False
                )
            return await interaction.edit_original_response(embed=embed,view=None)

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
    
    ############################################################
    #####
    ##### GROUP: CWL ROSTER COMMANDS
    #####
    ############################################################
    @cmdgroup_cwl_cwl.group(name="roster")
    @commands.check(is_cwl_admin)
    @commands.guild_only()
    async def subcmdgroup_cwl_cwlroster(self,ctx):
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

    subappgroup_cwl_cwlroster = app_commands.Group(
        name="roster",
        description="Manage CWL Rosters",
        parent=appgroup_cwl_cwl,
        guild_only=True
        )
    
    ##################################################
    ### CWL / ROSTER / SETUP
    ##################################################
    @subcmdgroup_cwl_cwlroster.command(name="setup")
    @commands.check(is_cwl_admin)
    @commands.guild_only()
    async def subcmd_cwl_cwlrostersetup(self,ctx:commands.Context,clan_tag:str):
        """
        Setup a Roster for a Clan.

        This is an interactive menu with various options to quickly set up a roster. Use the in-menu help buttons.

        Always defaults to the next open CWL Season.
        """
            
        league_clan = await WarLeagueClan(clan_tag,self.active_war_league_season)

        if not league_clan.is_participating:
            embed = await clash_embed(
                context=ctx,
                message=f"**{league_clan.title}** is not participating in CWL for {self.active_war_league_season.description}.",
                success=False
                )
            return await ctx.reply(embed=embed,view=None)
        
        menu = CWLRosterMenu(ctx,self.active_war_league_season,league_clan)
        await menu.start()
    
    @subappgroup_cwl_cwlroster.command(name="setup",
        description="Setup a CWL Roster for a Clan. Defaults to the next open CWL Season.")
    @app_commands.check(is_cwl_admin)
    @app_commands.guild_only()
    @app_commands.autocomplete(clan=autocomplete_season_league_clans)
    @app_commands.describe(clan="The Clan to setup for.")
    async def subappcmd_cwl_cwlrostersetup(self,interaction:discord.Interaction,clan:str):
        
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
    ### CWL / ROSTER / OPEN
    ##################################################
    @subcmdgroup_cwl_cwlroster.command(name="open")
    @commands.is_owner()
    @commands.guild_only()
    async def subcmd_cwl_cwlrosteropen(self,ctx:commands.Context,clan_tag:str):
        """
        Force open a CWL Clan's Roster.
        """
        season = self.active_war_league_season
        clan = await bot_client.coc.get_clan(clan_tag)
        cwl_clan = await WarLeagueClan(clan.tag,season)

        await cwl_clan.open_roster()
        await ctx.tick()
    
    ##################################################
    ### CWL / ROSTER / ADD
    ##################################################
    async def admin_add_player_helper(self,
        context:Union[discord.Interaction,commands.Context],
        clan_tag:str,
        player_tag:str):

        reopen = False
        season = self.active_war_league_season
        clan = await bot_client.coc.get_clan(clan_tag)
        league_clan = await WarLeagueClan(clan.tag,season)

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
        
        player = await bot_client.coc.get_player(player_tag)
        league_player = await WarLeaguePlayer(player.tag,season)
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
    
    @subcmdgroup_cwl_cwlroster.command(name="add")
    @commands.check(is_cwl_admin)
    @commands.guild_only()
    async def subcmd_cwl_cwlrosteradd(self,ctx:commands.Context,clan_tag:str,player_tag:str):
        """
        Admin add a Player to a Roster.

        This works even if the roster has been finalized. If the player is currently not registered, this will auto-register them into CWL.

        **Important**
        > - If the player is currently not registered, this will make them appear as if they've registered without a League Group.
        > - If the player is already in a finalized roster, this will remove the player from that roster. If this lowers the roster below 15 players, the roster will be re-opened.
        """
        
        embed = await self.admin_add_player_helper(ctx,clan_tag,player_tag)
        await ctx.reply(embed=embed)
    
    @subappgroup_cwl_cwlroster.command(name="add",
        description="Add a Player to a CWL Roster. Automatically registers the Player, if not registered.")
    @app_commands.check(is_cwl_admin)
    @app_commands.guild_only()
    @app_commands.autocomplete(clan=autocomplete_season_league_clans)
    @app_commands.autocomplete(player=autocomplete_players)
    @app_commands.describe(
        clan="The Clan to add the player to. Must be an active CWL Clan.",
        player="The Player to add to the Roster.")
    async def subcmd_cwl_cwlrosteradd(self,interaction:discord.Interaction,clan:str,player:str):
        
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

        player = await bot_client.coc.get_player(player_tag)        
        league_player = await WarLeaguePlayer(player.tag,season)
        
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
    
    @subcmd_cwl_cwlrostersetup.command(name="remove")
    @commands.check(is_cwl_admin)
    @commands.guild_only()
    async def subcmd_cwl_cwlrosterremove(self,ctx:commands.Context,player_tag:str):
        """
        Admin remove a Player from CWL.

        This works even if the roster has been finalized. If the player is currently in a roster, this will auto-remove them from CWL.

        **Important**
        If the player is in a finalized roster, and this lowers the roster below 15 players, the roster will be re-opened.
        """
            
        embed = await self.admin_remove_player_helper(ctx,player_tag)
        await ctx.reply(embed=embed)
    
    @subappgroup_cwl_cwlroster.command(name="remove",
        description="Removes a Player from a CWL Roster. Automatically unregisters the Player, if registered.")
    @app_commands.check(is_cwl_admin)
    @app_commands.guild_only()
    @app_commands.autocomplete(player=autocomplete_players)
    @app_commands.describe(player="The Player to remove from CWL.")
    async def subappcmd_cwl_cwlrosterremove(self,interaction:discord.Interaction,player:str):
        
        await interaction.response.defer()

        embed = await self.admin_remove_player_helper(interaction,player)
        return await interaction.edit_original_response(embed=embed)

    ##################################################
    ### CWL / ROSTER / EXPORT
    ##################################################
    @subcmdgroup_cwl_cwlroster.command(name="export")
    @commands.check(is_cwl_admin)
    @commands.guild_only()
    async def subcmd_cwl_cwlrosterexport(self,ctx:commands.Context):
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
    
    @subappgroup_cwl_cwlroster.command(name="export",
        description="Exports all Signups (and Roster information) to Excel. Uses the currently open CWL Season.")
    @app_commands.check(is_cwl_admin)
    @app_commands.guild_only()
    async def subappcmd_cwl_cwlrosterexport(self,interaction:discord.Interaction):
        
        await interaction.response.defer()

        season = self.active_war_league_season        
        rp_file = await generate_cwl_roster_export(season)
        
        if not rp_file:
            return await interaction.edit_original_response(content=f"I couldn't export the CWL Roster for {season.description}. Were you trying to export an already-completed CWL Season?")
        
        await interaction.followup.send(
            content=f"Here is the CWL Roster for {season.description}.",
            file=discord.File(rp_file))