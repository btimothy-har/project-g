import asyncio
import coc
import discord
import pendulum
import os
import urllib

from typing import *

from discord.ext import tasks
from redbot.core import Config, commands, app_commands
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path

from coc_main.api_client import BotClashClient, ClashOfClansError
from coc_main.cog_coc_client import ClashOfClansClient

from coc_main.utils.components import clash_embed, MultipleChoiceSelectionMenu, DiscordModal
from coc_main.utils.constants.coc_constants import TroopCampSize, clan_castle_size
from coc_main.utils.checks import is_member, is_owner

from .views.base_vault import BaseVaultMenu
from .objects.war_base import eWarBase
from .components import eclipse_embed

bot_client = BotClashClient()

############################################################
############################################################
#####
##### CLIENT COG
#####
############################################################
############################################################
class ECLIPSE(commands.Cog):
    """
    E.C.L.I.P.S.E.

    An **E**xtraordinarily **C**ool **L**ooking **I**nteractive & **P**rofessional **S**earch **E**ngine.

    Your Clash of Clans database of attack strategies, guides and war bases.a
    """

    __author__ = bot_client.author
    __version__ = bot_client.version
    __release__ = 4

    def __init__(self,bot:Red):        
        self.bot = bot
        self._dump_channel = 1079665410770739201
        self._dump_lock = asyncio.Lock()
        self.dump_messages = []

        resource_path = f"{cog_data_path(self)}"
        self.bot.base_image_path = f"{resource_path}/base_images"
        if not os.path.exists(self.bot.base_image_path):
            os.makedirs(self.bot.base_image_path)

        self.config = Config.get_conf(self,identifier=644530507505336330,force_registration=True)
        default_global = {
            "vault_pass_guild": 0,
            "vault_pass_role": 0,
            }
        self.config.register_global(**default_global)

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}.{self.__release__}"
    
    @property
    def client(self) -> ClashOfClansClient:
        return self.bot.get_cog("ClashOfClansClient")
    
    @property
    def dump_channel(self) -> discord.TextChannel:
        return self.bot.get_channel(self._dump_channel)
    
    @property
    def vault_pass_guild(self) -> Optional[discord.Guild]:
        return self.bot.get_guild(self._vault_pass_guild)
    
    @property
    def vault_pass(self) -> Optional[discord.Role]:
        if self.vault_pass_guild:
            return self.vault_pass_guild.get_role(self._vault_pass_role)
        return None

    async def cog_load(self):        
        self.delete_dump_messages.start()
        try:
            self._vault_pass_guild = await self.config.vault_pass_guild()
        except:
            self._vault_pass_guild = 0
        try:
            self._vault_pass_role = await self.config.vault_pass_role()
        except:
            self._vault_pass_role = 0
    
    async def cog_unload(self):
        self.delete_dump_messages.cancel()
    
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
    
    @tasks.loop(minutes=10)
    async def delete_dump_messages(self):
        if self._dump_lock.locked():
            return
        await self.clear_dump_messages()

    async def clear_dump_messages(self):
        async with self._dump_lock:
            if not self.dump_channel:
                return            
            async for message in self.dump_channel.history(limit=30):
                try:
                    if message.author.id == self.bot.user.id:
                        if message.id in self.dump_messages:
                            self.dump_messages.remove(message.id)
                        await message.delete()
                except Exception:
                    bot_client.coc_main_log.exception(f"Error deleting ECLIPSE Dump Message {message.id} in {self.dump_channel.id}.")
                    continue    
    
    ############################################################
    ############################################################
    #####
    ##### COMMAND DIRECTORY
    ##### - eclipse
    #####
    ############################################################
    ############################################################                
    @commands.group(name="eclipseset")
    @commands.guild_only()
    @commands.is_owner()
    async def command_group_eclipseset(self,ctx):
        """
        Config for E.C.L.I.P.S.E.
        """
        if not ctx.invoked_subcommand:
            pass
                
    @command_group_eclipseset.command(name="vaultpass")
    @commands.guild_only()
    @commands.is_owner()
    async def subcommand_bank_eclipseset_vaultpass(self,ctx:commands.Context,role:discord.Role):
        """
        [Owner only] Assign a Role as a Vault Pass.
        """

        self._vault_pass_guild = role.guild.id
        self._vault_pass_role = role.id
        await ctx.reply(f"Vault Pass set to {role.name} `{role.id}`.")

        await self.config.vault_pass_guild.set(role.guild.id)
        await self.config.vault_pass_role.set(role.id)

        await ctx.tick()        

    ##################################################
    ### BASE VAULT
    ##################################################
    @commands.command(name="eclipse")
    @commands.guild_only()
    @commands.check(is_member)
    async def command_eclipse_base_vault(self,ctx):
        """
        Access the E.C.L.I.P.S.E. Base Vault.
        """
        if isinstance(ctx.channel,discord.Thread):
            embed = await eclipse_embed(
                context=ctx,
                message=f"Sorry, E.C.L.I.P.S.E. is not available in threads. Try using this command in a regular text channel.",
                success=False,
                timestamp=pendulum.now()
                )
            await ctx.reply(embed=embed,delete_after=60)
            return
        
        menu = BaseVaultMenu(ctx)
        await menu.start()
    
    @app_commands.command(name="eclipse",
        description="Access the E.C.L.I.P.S.E. Base Vault.")
    @app_commands.guild_only()
    @app_commands.check(is_member)
    async def appcommand_eclipse_base_vault(self,interaction:discord.Interaction):
     
        await interaction.response.defer(ephemeral=True)
    
        if isinstance(interaction.channel,discord.Thread):
            embed = await eclipse_embed(
                context=interaction,
                message=f"Sorry, E.C.L.I.P.S.E. is not available in threads. Try using this command in a regular text channel.",
                success=False,
                timestamp=pendulum.now()
                )
            await interaction.followup.send(embed=embed,ephemeral=True)
            return       
        
        menu = BaseVaultMenu(interaction)
        await menu.start()
    
    @property
    def builder_notes_modal(self) -> DiscordModal:
        m = DiscordModal(
            function=self._get_builder_notes,
            title=f"Add New Base",
            )
        defensive_cc = discord.ui.TextInput(
            label="Defensive CC",
            style=discord.TextStyle.short,
            required=True
            )
        builder_notes = discord.ui.TextInput(
            label="Builder Notes",
            style=discord.TextStyle.long,
            required=False
            )        
        m.add_item(defensive_cc)
        m.add_item(builder_notes)
        return m

    async def _get_builder_notes(self,interaction:discord.Interaction,modal:DiscordModal):
        await interaction.response.defer(ephemeral=True)
        modal.defensive_cc = modal.children[0].value
        modal.notes = modal.children[1].value if len(modal.children[1].value) > 0 else "*"
        modal.stop()
    
    @app_commands.command(name="add-base",
        description="[Owner-only] Add a Base to the E.C.L.I.P.S.E. Base Vault.")
    @app_commands.guild_only()
    @app_commands.check(is_owner)
    @app_commands.choices(base_source=[
        app_commands.Choice(name="RH Base Building",value="<:RHBB:1041627382018211900> RH Base Building"),
        app_commands.Choice(name="Blueprint Base Building",value="<:BPBB:1043081040090107968> Blueprint Base Building")
        ])
    @app_commands.choices(base_type=[
        app_commands.Choice(name="War Base: Anti-3 Star",value="War Base: Anti-3 Star"),
        app_commands.Choice(name="War Base: Anti-2 Star",value="War Base: Anti-2 Star"),
        app_commands.Choice(name="Legends Base",value="Legends Base"),
        app_commands.Choice(name="Trophy/Farm Base",value="Trophy/Farm Base")
        ])
    async def appcommand_eclipse_add_base(self,
        interaction:discord.Interaction,
        base_link:str,
        base_image:discord.Attachment,
        base_type:str,
        base_source:str,
        base_builder:Optional[str] = "*"):

        modal = self.builder_notes_modal
        await interaction.response.send_modal(modal)

        wait = await modal.wait()
        if wait:
            return await interaction.followup.send(content="Did not receive a response.",ephemeral=True)
        
        new_base = await eWarBase.new_base(
            base_link=base_link,
            source=base_source,
            base_builder=base_builder,
            base_type=base_type,
            defensive_cc=modal.defensive_cc,
            notes=modal.notes,
            image_attachment=base_image)

        embed,image = await new_base.base_embed()
        embed.add_field(name="Base Link",value=new_base.base_link)

        return await interaction.followup.send(content="Base Added!",embed=embed,files=[image])