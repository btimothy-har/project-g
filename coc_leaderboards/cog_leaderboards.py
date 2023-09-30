import asyncio
import discord
import pendulum

from discord.ext import tasks

from redbot.core import commands, app_commands
from redbot.core.data_manager import cog_data_path
from coc_client.api_client import BotClashClient

from coc_data.utilities.utils import *
from coc_data.utilities.components import *
from coc_data.exceptions import *

from coc_commands.helpers.checks import *

from .leaderboard_files.discord_leaderboard import *

lb_type_selector = [
    app_commands.Choice(name="Clan War Triples", value=1),
    app_commands.Choice(name="Resource Loot", value=3),
    app_commands.Choice(name="Donations", value=4),
    app_commands.Choice(name="Clan Games", value=5)
    ]

async def autocomplete_leaderboard_selector(interaction:discord.Interaction,current:str):
    guild_leaderboards = DiscordLeaderboard.get_guild_leaderboards(interaction.guild.id)
    return [
        app_commands.Choice(
            name=str(lb),
            value=lb.id
            )
        for lb in guild_leaderboards
        ]

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

    __author__ = "bakkutteh"
    __version__ = "1.1.0"

    def __init__(self,bot):        
        self.bot = bot 
        self.leaderboard_lock = asyncio.Lock()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"

    @property
    def client(self):
        return self.bot.get_cog("ClashOfClansClient").client
    
    async def cog_load(self):
        self.update_leaderboards.start()
    
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
    @command_group_clash_leaderboards.command(name="list")
    @commands.guild_only()
    @commands.admin()
    async def command_list_leaderboard(self,ctx):
        """
        List all Leaderboards setup in this server.
        """
        
        embed = await clash_embed(
            context=ctx,
            title="**Server Leaderboards**"
            )
        async for lb in AsyncIter(DiscordLeaderboard.get_guild_leaderboards(ctx.guild.id)):
            embed.add_field(
                name=f"**{getattr(lb.channel,'name','Unknown Channel')}**",
                value=f"\nMessage: {getattr(await lb.fetch_message(),'jump_url','')}"
                    + f"\nID: `{lb.id}`"
                    + f"\nType: {lb.lb_type}"
                    + f"\nIs Global? `{lb.is_global}`"
                    + f"\n\u200b",
                inline=True
                )
            
        await ctx.reply(embed=embed)
    
    @app_command_group_leaderboards.command(name="list",
        description="List all Leaderboards setup in this server.")
    @app_commands.check(is_admin)
    @app_commands.guild_only()
    async def sub_appcommand_leaderboards_list(self,interaction:discord.Interaction):
        
        await interaction.response.defer()

        embed = await clash_embed(
            context=interaction,
            title="**Server Leaderboards**"
            )
        async for lb in AsyncIter(DiscordLeaderboard.get_guild_leaderboards(interaction.guild.id)):
            embed.add_field(
                name=f"**{getattr(lb.channel,'name','Unknown Channel')}**",
                value=f"\nMessage: {getattr(await lb.fetch_message(),'jump_url','')}"
                    + f"\nID: `{lb.id}`"
                    + f"\nType: {lb.lb_type}"
                    + f"\nIs Global? `{lb.is_global}`"
                    + f"\n\u200b",
                inline=True
                )            
        await interaction.edit_original_response(embed=embed,view=None)
    
    ##################################################
    ### LEADERBOARD / CREATE
    ##################################################
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

        if type not in [1,3,4,5]:
            embed = await clash_embed(
                context=ctx,
                message=f"Type `{type}` is not a valid type.",
                success=False,
                timestamp=pendulum.now()
                )
            return await ctx.reply(embed=embed)
        
        if is_global not in [0,1]:
            embed = await clash_embed(
                context=ctx,
                message=f"Is_Global argument should be `0` or `1`.",
                success=False,
                timestamp=pendulum.now()
                )
            return await ctx.reply(embed=embed)
        
        lb = await DiscordLeaderboard.create(
            leaderboard_type=type,
            is_global=True if is_global == 1 else False,
            guild=ctx.guild,
            channel=channel
            )
        
        embed = await clash_embed(
            context=ctx,
            title="**Leaderboard Created**",
            message=f"Channel: {getattr(lb.channel,'name','Unknown Channel')}"
                + f"\nID: `{lb.id}`"
                + f"\nType: {lb.lb_type}"
                + f"\nIs Global? `{lb.is_global}`",
            success=True,
            timestamp=pendulum.now()
            )
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

        lb = await DiscordLeaderboard.create(
            leaderboard_type=type,
            is_global=True if is_global == 1 else False,
            guild=interaction.guild,
            channel=channel
            )
        
        embed = await clash_embed(
            context=interaction,
            title="**Leaderboard Created**",
            message=f"Channel: {getattr(lb.channel,'name','Unknown Channel')}"
                + f"\nID: `{lb.id}`"
                + f"\nType: {lb.lb_type}"
                + f"\nIs Global? `{lb.is_global}`",
            success=True,
            timestamp=pendulum.now()
            )
        await interaction.edit_original_response(embed=embed,view=None)
    
    ##################################################
    ### LEADERBOARD / DELETE
    ##################################################    
    @command_group_clash_leaderboards.command(name="delete")
    @commands.guild_only()
    @commands.admin()
    async def command_delete_leaderboard(self,ctx,leaderboard_id:str):
        """
        Delete a Leaderboard by ID.

        To get the ID of a Leaderboard, use the command [p]`coclb list`.
        """

        try:
            lb = DiscordLeaderboard.get_by_id(leaderboard_id)
        except DoesNotExist:
            embed = await clash_embed(
                context=ctx,
                message=f"Leaderboard with ID `{leaderboard_id}` does not exist.",
                success=False,
                timestamp=pendulum.now()
                )
            return await ctx.reply(embed=embed)
        
        if lb.guild_id != ctx.guild.id:
            embed = await clash_embed(
                context=ctx,
                message=f"Leaderboard with ID `{leaderboard_id}` was not found in this server.",
                success=False,
                timestamp=pendulum.now()
                )
            return await ctx.reply(embed=embed)

        message = await lb.fetch_message()
        if message:
            await message.delete()        
        lb.delete()

        embed = await clash_embed(
            context=ctx,
            message=f"Leaderboard with ID `{leaderboard_id}` was successfully deleted.",
            success=True,
            timestamp=pendulum.now()
            )
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

        try:
            lb = DiscordLeaderboard.get_by_id(leaderboard)
        except DoesNotExist:
            embed = await clash_embed(
                context=interaction,
                message=f"Leaderboard with ID `{leaderboard}` does not exist.",
                success=False,
                timestamp=pendulum.now()
                )
            return await interaction.edit_original_response(embed=embed,view=None)
        
        if lb.guild_id != interaction.guild.id:
            embed = await clash_embed(
                context=interaction,
                message=f"Leaderboard with ID `{leaderboard}` was not found in this server.",
                success=False,
                timestamp=pendulum.now()
                )
            return await interaction.edit_original_response(embed=embed,view=None)

        message = await lb.fetch_message()
        if message:
            await message.delete()        
        lb.delete()

        embed = await clash_embed(
            context=interaction,
            message=f"Leaderboard with ID `{leaderboard}` was successfully deleted.",
            success=True,
            timestamp=pendulum.now()
            )
        await interaction.edit_original_response(embed=embed,view=None)
    
    @tasks.loop(minutes=15.0)
    async def update_leaderboards(self):
        if self.leaderboard_lock.locked():
            return

        async with self.leaderboard_lock:
            st = pendulum.now()
            self.client.cog.coc_main_log.info("Updating Leaderboards...")
            tasks = []
            for guild in self.bot.guilds:
                guild_leaderboards = DiscordLeaderboard.get_guild_leaderboards(guild.id)
                tasks.extend([asyncio.create_task(lb.update_leaderboard()) for lb in guild_leaderboards])
            
            await asyncio.gather(*tasks)
            et = pendulum.now()
            self.client.cog.coc_main_log.info(f"Leaderboards Updated. Time Taken: {et.int_timestamp - st.int_timestamp} seconds.")