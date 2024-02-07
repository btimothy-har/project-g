import asyncio
import discord
import pendulum
import random

from typing import *
from discord.ext import tasks

from redbot.core import commands, app_commands
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter,bounded_gather

from coc_main.api_client import BotClashClient, ClashOfClansError
from coc_main.cog_coc_client import ClashOfClansClient
from coc_main.utils.checks import is_admin
from coc_main.utils.components import clash_embed

from .leaderboard_files.discord_leaderboard import DiscordLeaderboard

lb_type_selector = [
    app_commands.Choice(name="Clan War Triples", value=1),
    app_commands.Choice(name="Resource Loot", value=3),
    app_commands.Choice(name="Donations", value=4),
    app_commands.Choice(name="Clan Games", value=5)
    ]

bot_client = BotClashClient()

async def autocomplete_leaderboard_selector(interaction:discord.Interaction,current:str):
    try:
        guild_leaderboards = await DiscordLeaderboard.get_guild_leaderboards(interaction.guild.id)
        
        if current:
            sel_lb = [p for p in guild_leaderboards if current.lower() in str(p).lower()]
        else:
            sel_lb = guild_leaderboards

        sample = random.sample(sel_lb,min(5,len(sel_lb)))

        return [
            app_commands.Choice(name=str(lb),value=lb.id) for lb in sample] 
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_leaderboard_selector")

############################################################
############################################################
#####
##### CLIENT COG
#####
############################################################
############################################################
class Leaderboards(commands.Cog):
    """
    Auto-updating Discord Leaderboards for Clash of Clans.
    """

    __author__ = bot_client.author
    __version__ = bot_client.version
    __release__ = 2

    def __init__(self,bot:Red):
        self.bot = bot
        self.leaderboard_lock = asyncio.Lock()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}.{self.__release__}"

    @property
    def bot_client(self) -> BotClashClient:
        return bot_client

    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    async def cog_load(self):
        async def start_cog():
            while True:
                if getattr(bot_client,'_api_logged_in',False):
                    break
                await asyncio.sleep(1)
                
            await bot_client.bot.wait_until_ready()
            self.update_leaderboards.start()
        
        asyncio.create_task(start_cog())
    
    async def cog_unload(self):
        self.update_leaderboards.cancel()
    
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
    ##### COMMAND DIRECTORY
    ##### - Leaderboard / List
    ##### - Leaderboard / Create
    ##### - Leaderboard / Delete
    #####
    ############################################################
    ############################################################

    ##################################################
    ### PARENT COMMAND GROUPS
    ##################################################
    @commands.group(name="cocleaderboard",aliases=["coclb"])
    @commands.guild_only()
    async def command_group_clash_leaderboards(self,ctx):
        """
        Group to set up Clash Leaderboards.

        **This is a command group. To use the sub-commands below, follow the syntax: `$member [sub-command]`.**
        """
        if not ctx.invoked_subcommand:
            pass

    app_command_group_leaderboards = app_commands.Group(
        name="coc-leaderboard",
        description="Group to set up Clash Leaderboards.",
        guild_only=True
        )

    ##################################################
    ### LEADERBOARD / LIST
    ##################################################
    async def helper_list_guild_leaderboards(self,
        context:Union[discord.Interaction,commands.Context],
        guild:discord.Guild) -> discord.Embed:

        embed = await clash_embed(
            context=context,
            title="**Server Leaderboards**"
            )
        
        lbs = await DiscordLeaderboard.get_guild_leaderboards(guild.id)
        a_iter = AsyncIter(lbs)

        async for lb in a_iter:
            embed.add_field(
                name=f"**{getattr(lb.channel,'name','Unknown Channel')}**",
                value=f"\nMessage: {getattr(await lb.fetch_message(),'jump_url','')}"
                    + f"\nID: `{lb.id}`"
                    + f"\nType: {lb.type}"
                    + f"\nIs Global? `{lb.is_global}`"
                    + f"\n\u200b",
                inline=True
                )            
        return embed

    @command_group_clash_leaderboards.command(name="hdel")
    @commands.guild_only()
    @commands.is_owner()
    async def command_delete_history_leaderboard(self,ctx):
        """
        Delete all historical leaderboards.
        """        
        await bot_client.coc_db.db__leaderboard_archive.delete_many({})
        await ctx.reply("Historical Leaderboards Deleted.")

    @command_group_clash_leaderboards.command(name="list")
    @commands.guild_only()
    @commands.admin()
    async def command_list_leaderboard(self,ctx):
        """
        List all Leaderboards setup in this server.
        """
        
        embed = await self.helper_list_guild_leaderboards(ctx,ctx.guild)
        await ctx.reply(embed=embed)        
    
    @app_command_group_leaderboards.command(name="list",
        description="List all Leaderboards setup in this server.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    async def sub_appcommand_leaderboards_list(self,interaction:discord.Interaction):
        
        await interaction.response.defer()

        embed = await self.helper_list_guild_leaderboards(interaction,interaction.guild)
        await interaction.edit_original_response(embed=embed,view=None)
    
    ##################################################
    ### LEADERBOARD / CREATE
    ##################################################
    async def helper_create_guild_leaderboard(self,
        context:Union[discord.Interaction,commands.Context],
        type:int,
        is_global:int,
        channel:discord.TextChannel) -> discord.Embed:  

        if type not in [1,3,4,5]:
            embed = await clash_embed(
                context=context,
                message=f"Type `{type}` is not a valid type.",
                success=False,
                timestamp=pendulum.now()
                )
            return embed
        
        if is_global not in [0,1]:
            embed = await clash_embed(
                context=context,
                message=f"Is_Global argument should be `0` or `1`.",
                success=False,
                timestamp=pendulum.now()
                )
            return embed
        
        lb = await DiscordLeaderboard.create(
            leaderboard_type=type,
            is_global=True if is_global == 1 else False,
            guild=context.guild,
            channel=channel
            )        
        embed = await clash_embed(
            context=context,
            title="**Leaderboard Created**",
            message=f"Channel: {getattr(lb.channel,'name','Unknown Channel')}"
                + f"\nID: `{lb.id}`"
                + f"\nType: {lb.type}"
                + f"\nIs Global? `{lb.is_global}`",
            success=True,
            timestamp=pendulum.now()
            )
        return embed
                                              
    @command_group_clash_leaderboards.command(name="create")
    @commands.guild_only()
    @commands.admin()
    async def command_create_leaderboard(self,ctx,type:int,is_global:int,channel:discord.TextChannel):
        """
        Create a new Clash Leaderboard.

        **Arguments**
        
        1) `type` - The type of leaderboard to create. Accepted values are:
        - 1: Clan War Leaderboard
        - 3: Resource Loot Leaderboard
        - 4: Donation Leaderboard
        - 5: Clan Games Leaderboard

        2) `is_global` - Whether the leaderboard should be global or not. Accepted values are:
        - 0: Not a global leaderboard. This leaderboard will be specific to members in this server.
        - 1: Global leaderboard. This leaderboard will be shared across all servers.

        Clan Games Leaderboards cannot be global.

        3) `channel` - The channel to post the leaderboard in.
        """

        embed = await self.helper_create_guild_leaderboard(ctx,type,is_global,channel)
        await ctx.reply(embed=embed)
    
    @app_command_group_leaderboards.command(name="create",
        description="Create a new Clash Leaderboard in this server.")
    @app_commands.check(is_admin)
    @app_commands.describe(
        type="The type of Leaderboard.",
        is_global="Whether the leaderboard should be global or not.",
        channel="The channel to post the leaderboard in.")
    @app_commands.choices(type=lb_type_selector)
    @app_commands.choices(is_global=[
        app_commands.Choice(name="Yes",value=1),
        app_commands.Choice(name="No",value=0)])
    async def app_command_create_leaderboard(self,interaction:discord.Interaction,type:int,is_global:int,channel:discord.TextChannel):
        
        await interaction.response.defer()
        embed = await self.helper_create_guild_leaderboard(interaction,type,is_global,channel)
        await interaction.edit_original_response(embed=embed)
    
    ##################################################
    ### LEADERBOARD / DELETE
    ##################################################
    async def helper_delete_guild_leaderboard(self,
        context:Union[discord.Interaction,commands.Context],
        leaderboard_id:str) -> discord.Embed:  

        lb = await DiscordLeaderboard.get_by_id(leaderboard_id)
        if not lb:
            embed = await clash_embed(
                context=context,
                message=f"Leaderboard with ID `{leaderboard_id}` does not exist.",
                success=False,
                timestamp=pendulum.now()
                )
            return embed
        
        if lb.guild_id != context.guild.id:
            embed = await clash_embed(
                context=context,
                message=f"Leaderboard with ID `{leaderboard_id}` was not found in this server.",
                success=False,
                timestamp=pendulum.now()
                )
            return embed

        await lb.delete()

        embed = await clash_embed(
            context=context,
            message=f"Leaderboard with ID `{leaderboard_id}` was successfully deleted.",
            success=True,
            timestamp=pendulum.now()
            )
        return embed
    
    @command_group_clash_leaderboards.command(name="delete")
    @commands.guild_only()
    @commands.admin()
    async def command_delete_leaderboard(self,ctx,leaderboard_id:str):
        """
        Delete a Leaderboard by ID.

        To get the ID of a Leaderboard, use the command [p]`coclb list`.
        """
        embed = await self.helper_delete_guild_leaderboard(ctx,leaderboard_id)
        await ctx.reply(embed=embed)
    
    @app_command_group_leaderboards.command(name="delete",
        description=f"Deletes a Leaderboard.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    @app_commands.autocomplete(leaderboard=autocomplete_leaderboard_selector)
    @app_commands.describe(
        leaderboard="The Leaderboard to delete.")
    async def appcommand_delete_leaderboard(self,interaction:discord.Interaction,leaderboard:str):
        
        await interaction.response.defer()
        embed = await self.helper_delete_guild_leaderboard(interaction,leaderboard)
        await interaction.edit_original_response(embed=embed,view=None)
    
    @tasks.loop(minutes=20.0)
    async def update_leaderboards(self):
        if self.leaderboard_lock.locked():
            return

        async with self.leaderboard_lock:
            st = pendulum.now()
            bot_client.coc_main_log.info("Updating Leaderboards...")

            all_leaderboards = await DiscordLeaderboard.get_all_leaderboards()

            tasks = [lb.update_leaderboard() for lb in all_leaderboards]
            await bounded_gather(*tasks,return_exceptions=True)
            et = pendulum.now()
            bot_client.coc_main_log.info(f"Leaderboards Updated. Time Taken: {et.int_timestamp - st.int_timestamp} seconds.")