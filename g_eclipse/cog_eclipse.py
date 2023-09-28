import os
import discord
import pendulum
import urllib
import asyncio


from redbot.core import commands, app_commands
from redbot.core.data_manager import cog_data_path

from coc_data.objects.discord.member import aMember
from coc_data.constants.coc_constants import *

from coc_data.utilities.utils import *
from coc_data.utilities.components import *
from coc_data.exceptions import *

from coc_commands.helpers.components import *
from coc_commands.helpers.checks import *

from .components import *
from .views.base_vault import BaseVaultMenu
from .objects.war_base import eWarBase


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

    __author__ = "bakkutteh"
    __version__ = "1.0.0"

    def __init__(self,bot):        
        self.bot = bot

        self.resource_path = f"{cog_data_path(self)}"
        self.base_image_path = f"{self.resource_path}/base_images"
        if not os.path.exists(self.base_image_path):
            os.makedirs(self.base_image_path)

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
    
    ############################################################
    ############################################################
    #####
    ##### COMMAND DIRECTORY
    ##### - eclipse
    #####
    ############################################################
    ############################################################

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

        member = aMember(ctx.author.id)
        if ((pendulum.now().int_timestamp - member.member_start.int_timestamp)/86400) < 14:
            embed = await eclipse_embed(
                context=ctx,
                message=f"Sorry, you must be a member for at least 14 days to access the E.C.L.I.P.S.E. Base Vault.",
                success=False,
                timestamp=pendulum.now()
                )
            await ctx.reply(embed=embed,delete_after=60)
            return
    
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

        member = aMember(interaction.user.id)
        if ((pendulum.now().int_timestamp - member.member_start.int_timestamp)/86400) < 14:
            embed = await eclipse_embed(
                context=interaction,
                message=f"Sorry, you must be a member of the Alliance for at least 14 days to access the E.C.L.I.P.S.E. Base Vault.",
                success=False,
                timestamp=pendulum.now()
                )
            await interaction.followup.send(embed=embed,ephemeral=True)
            return
    
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
    
    @commands.command(name="addbase")
    @commands.guild_only()
    @commands.is_owner()
    async def command_add_base(self,ctx,base_link:str):

        timeout_embed = await eclipse_embed(context=ctx,message=f"Operation timed out.",success=False,timestamp=pendulum.now())

        def armylink_check(m):
            msg_check = False
            if m.author.id == ctx.author.id:
                if m.channel.id == ctx.channel.id:
                    msg_check = True
                elif m.channel.type == ctx.channel.type == discord.ChannelType.private:
                    msg_check = True
            if msg_check:
                try:
                    link_parse = urllib.parse.urlparse(m.content)
                    link_action = urllib.parse.parse_qs(link_parse.query)['action'][0]

                    if link_parse.netloc == "link.clashofclans.com" and link_action == "CopyArmy":
                        check_url = True
                except:
                    pass
                return check_url
        
        def response_check(m):
            if m.author.id == ctx.author.id:
                if m.channel.id == ctx.channel.id:
                    return True
                elif m.channel.type == ctx.channel.type == discord.ChannelType.private:
                    return True
                else:
                    return False                

        msg = await ctx.send("Processing base link...")

        link_parse = urllib.parse.urlparse(base_link)
        base_id = urllib.parse.quote_plus(urllib.parse.parse_qs(link_parse.query)['id'][0])
        try:
            base_townhall = int(base_id.split('TH',1)[1][:2])
        except:
            base_townhall = int(base_id.split('TH',1)[1][:1])

        # BASE SOURCE
        select_view = MultipleChoiceSelectionMenu(ctx)
        select_view.add_list_item(
            reference='<:RHBB:1041627382018211900> RH Base Building',
            label="RH Base Building",
            emoji="<:RHBB:1041627382018211900>",
            )
        select_view.add_list_item(
            reference='<:BPBB:1043081040090107968> Blueprint Base Building',
            label="Blueprint Base Building",
            emoji='<:BPBB:1043081040090107968>',
            )
        select_view.add_list_item(
            reference="<a:aa_AriX:1031773589231374407> Others",
            label="Others",
            emoji="<a:aa_AriX:1031773589231374407>",
            )
        base_source_embed = await eclipse_embed(
            context=ctx,
            title="Add Base -- Step 2/7",
            message=f"Where is this Base from?")
        
        await msg.edit(embed=base_source_embed,view=select_view)
        timed_out = await select_view.wait()

        if timed_out:
            return await msg.edit(embed=timeout_embed,view=None)
        base_source = select_view.return_value


        # BASE BUILDER
        base_builder_embed = await eclipse_embed(
            context=ctx,
            title="Add Base -- Step 3/7",
            message=f"Provide the Name of the Builder. If no Builder is specified, please respond with an asterisk [`*`].")
        await msg.edit(embed=base_builder_embed,view=None)

        try:
            builder_response = await ctx.bot.wait_for("message",timeout=60,check=response_check)
        except asyncio.TimeoutError:
            return await msg.edit(embed=timeout_embed)
        else:
            base_builder = builder_response.content
            await builder_response.delete()

        #BASE TYPE
        base_type_view = MultipleChoiceSelectionMenu(ctx)
        base_type_view.add_list_item(
            reference='War Base: Anti-3 Star',
            label="War Base: Anti-3 Star",
            emoji='<:3_Star:1043063806378651720>',
            )
        base_type_view.add_list_item(
            reference='War Base: Anti-2 Star',
            label="War Base: Anti-2 Star",
            emoji='<:Attack_Star:1043063829430542386>',
            )
        base_type_view.add_list_item(
            reference='Legends Base',
            label="Legends Base",
            emoji='<:legend_league_star:1043062895652655125>',
            )
        base_type_view.add_list_item(
            reference='Trophy/Farm Base',
            label="Trophy/Farm Base",
            emoji='<:HomeTrophies:825589905651400704>',
            )

        base_type_embed = await eclipse_embed(
            context=ctx,
            title="Add Base -- Step 4/7",
            message=f"Select the type of base this is.")
        
        await msg.edit(embed=base_type_embed,view=base_type_view)
        timed_out = await base_type_view.wait()

        if timed_out:
            return await msg.edit(embed=timeout_embed,view=None)
        base_type = base_type_view.return_value


        #DEFENSIVE CC
        defensive_cc_embed = await eclipse_embed(
            context=ctx,
            title="Add Base -- Step 5/7",
            message=f"Provide the Army Link for the Defensive Clan Castle.")
        await msg.edit(embed=defensive_cc_embed,view=None)
        try:
            army_link_response = await ctx.bot.wait_for("message",timeout=60,check=armylink_check)
        except asyncio.TimeoutError:
            return await msg.edit(embed=timeout_embed)
        else:
            defensive_cc = army_link_response.content

            parsed_cc = ctx.bot.coc_client.parse_army_link(defensive_cc)
            cc_space = 0
            for troop in parsed_cc[0]:
                if troop[0].name in coc.HOME_TROOP_ORDER:
                    cc_space += (TroopCampSize.get(troop[0].name) * troop[1])

            if cc_space > clan_castle_size[base_townhall][0]:
                invalid_cc = await eclipse_embed(
                    context=ctx,
                    message=f"This Clan Castle composition has more troops than available for this Townhall level."
                    )
                return await msg.edit(embed=invalid_cc,view=None)
            await army_link_response.delete()
        
        
        #BUIDLER NOTES
        builder_notes_embed = await eclipse_embed(
            context=ctx,
            title="Add Notes -- Step 6/7",
            message=f"Add any Notes from the Builder, if any. If there are no notes, please respond with an asterisk [`*`].")
        await msg.edit(embed=builder_notes_embed,view=None)
        
        try:
            builder_notes_response = await ctx.bot.wait_for("message",timeout=120,check=response_check)
        except asyncio.TimeoutError:
            return await msg.edit(embed=timeout_embed)
        else:
            builder_notes = builder_notes_response.content
            await builder_notes_response.delete()
        

        ## BASE IMAGE
        base_image_embed = await eclipse_embed(
            context=ctx,
            title="Add Base -- Step 7/7",
            message=f"Upload the Base Image.")
        await msg.edit(embed=base_image_embed,view=None)

        try:
            base_image_response = await ctx.bot.wait_for("message",timeout=60,check=response_check)
        except asyncio.TimeoutError:
            return await msg.edit(embed=timeout_embed)
        else:
            base_image = base_image_response.attachments[0]
            await base_image_response.delete()

        new_base = await eWarBase.new_base(
            base_link=base_link,
            source=base_source,
            base_builder=base_builder,
            base_type=base_type,
            defensive_cc=defensive_cc,
            notes=builder_notes,
            image_attachment=base_image)

        embed,image = await new_base.base_embed()
        embed.add_field(name="Base Link",value=new_base.base_link)

        return await msg.edit(content="Base Added!",embed=embed,attachments=[image])