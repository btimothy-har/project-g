import discord
import pendulum
import asyncio

from typing import *
from ..components import eclipse_embed

from redbot.core import commands

from coc_main.utils.components import DefaultView, DiscordButton, DiscordSelectMenu
from coc_main.utils.constants.coc_emojis import EmojisTownHall
from coc_main.utils.constants.ui_emojis import EmojisUI

from ..objects.war_base import eWarBase

class BaseVaultMenu(DefaultView):
    def __init__(self,
        context:Union[commands.Context,discord.Interaction]):
        
        self.vault_mode = False
        self.base_th = 0
        self.base_index = 0
        self.all_bases = []
        self.base_selector = []

        self.base_select_menu = None
        super().__init__(context,timeout=900)
    
    @property
    def home_button(self):
        return DiscordButton(
            function=self._callback_home,
            label="Home",
            emoji=EmojisUI.HOME,
            row=0,
            style=discord.ButtonStyle.blurple
            )
    
    @property
    def vault_button(self):
        return DiscordButton(
            function=self._callback_vault,
            label="Personal Vault",
            emoji=EmojisUI.LOCK,
            row=0
            )
    
    @property
    def base_save(self):
        return DiscordButton(
            function=self._callback_save_base,
            label="Bookmark Base",
            emoji=EmojisUI.DOWNLOAD,
            row=0
            )
    
    @property
    def base_unsave(self):
        return DiscordButton(
            function=self._callback_unsave_base,
            label="Delete Bookmark",
            emoji=EmojisUI.DELETE,
            row=0
            )
    
    @property
    def exit_button(self):
        return DiscordButton(
            function=self._callback_exit,
            emoji=EmojisUI.EXIT,
            style=discord.ButtonStyle.danger,
            row=0
            )
    
    ##################################################
    ### OVERRIDE BUILT IN METHODS
    ##################################################
    async def on_timeout(self):
        try:
            embed = await eclipse_embed(context=self.ctx,message=f"Logged out of **E.C.L.I.P.S.E.**.")
            await self.ctx.followup.edit_message(self.message.id,embed=embed,view=None)
        except:
            pass        
        self.stop_menu()
    
    @property
    def cog(self):
        return self.bot.get_cog("ECLIPSE")
    
    ####################################################################################################
    #####
    ##### VIEW HELPERS
    #####
    ####################################################################################################
    
    ##################################################
    ### START / STOP 
    ##################################################
    async def start(self):
        self.is_active = True
        if not isinstance(self.ctx,discord.Interaction):
            start_button = DiscordButton(
                function=self._callback_start,
                label="Open E.C.L.I.P.S.E.",
                )
            self.add_item(start_button)
            return await self.ctx.reply(
                content="Click on the button below to open the **E.C.L.I.P.S.E. Base Vault**.",
                view=self)

        self._base_vault_main_menu()
        self.home_button.disabled = True
        dropdown_list = [discord.SelectOption(
            label=f"TH{th}",
            value=th,
            emoji=EmojisTownHall.get(th),
            )
            for th in range(16-1,9-1,-1)]        
        th_select_menu = DiscordSelectMenu(
            function=self._callback_dropdown_th_select,
            options=dropdown_list,
            placeholder="Select a Townhall level.",
            min_values=1,
            max_values=1,
            row=1
            )
        self.add_item(th_select_menu)

        embed = await self._base_vault_home_embed()        
        self.message = await self.ctx.followup.send(
            wait=True,
            embed=embed,
            view=self,
            ephemeral=True
            )
    
    ##################################################
    ### START BUTTON CALLBACK
    ##################################################
    # used when BaseVault is accessed with the text command
    async def _callback_start(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer(ephemeral=True)
        self.ctx = interaction

        await interaction.message.delete()
        await self.start()

    ##################################################
    ### CALLBACKS
    ##################################################    
    async def _callback_exit(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer(ephemeral=True)
        embed = await eclipse_embed(context=self.ctx,message=f"Logged out of **E.C.L.I.P.S.E.**.")
        await interaction.followup.edit_message(
            interaction.message.id,
            embed=embed,
            view=None
            )
        self.stop_menu()

    async def _callback_home(self,interaction:discord.Interaction,button:Union[DiscordButton,DiscordSelectMenu],no_base=None):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
            self.ctx = interaction

        for item in self.children:
            item.disabled = True        
        await interaction.followup.edit_message(interaction.message.id,view=self)

        self._base_vault_main_menu()
        self.vault_mode = False
        self.home_button.disabled = True
        self.vault_button.disabled = False

        dropdown_list = [discord.SelectOption(
            label=f"TH{th}",
            value=th,
            emoji=EmojisTownHall.get(th),
            )
            for th in range(16-1,9-1,-1)]
        
        th_select_menu = DiscordSelectMenu(
            function=self._callback_dropdown_th_select,
            options=dropdown_list,
            placeholder="Select a Townhall level.",
            min_values=1,
            max_values=1,
            row=1
            )
        self.add_item(th_select_menu)

        embed = await self._base_vault_home_embed(no_base=no_base)
        await interaction.followup.edit_message(
            interaction.message.id,
            embed=embed,
            view=self
            )
    
    async def _callback_vault(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer(ephemeral=True)
        self.ctx = interaction

        for item in self.children:
            item.disabled = True        
        await interaction.followup.edit_message(interaction.message.id,view=self)

        self.vault_mode = True

        self.base_index = 0
        self.all_bases = await eWarBase.by_user_claim(self.user.id)

        if not self.all_bases or len(self.all_bases) == 0:
            embed = await self._browse_bases_embed()
            self._base_vault_main_menu()
            return await interaction.edit_original_response(embed=embed,view=self)

        self.base_selector = [
            discord.SelectOption(
                label=f"#{i}: TH{base.town_hall} {base.base_type}",
                value=i-1,
                description=f"Added: {pendulum.from_timestamp(base.added_on).format('DD MMM YYYY')}",
                emoji=f"{base.source.split(' ',1)[0]}")
                for i,base in enumerate(self.all_bases,1)
                ]        
        self.clear_items()
        self.add_item(self.home_button)
        #self.add_item(self.base_save)
        self.add_item(self.base_unsave)
        self.add_item(self.exit_button)
        self._build_base_select_menu()

        embed1 = await self._browse_bases_embed()
        embed2 = await self._show_base_embed()

        await interaction.followup.edit_message(
            interaction.message.id,
            embeds=[embed1,embed2],
            view=self
            )
    
    async def _callback_dropdown_th_select(self,interaction:discord.Interaction,menu:DiscordSelectMenu):
        await interaction.response.defer(ephemeral=True)
        self.ctx = interaction

        for item in self.children:
            item.disabled = True        
        await interaction.followup.edit_message(interaction.message.id,view=self)

        self.base_th = int(menu.values[0])
        self.base_index = 0
        self.all_bases = await eWarBase.by_townhall_level(self.base_th)

        if len(self.all_bases) == 0:
            return await self._callback_home(interaction,self.home_button,no_base=self.base_th)
        
        self.base_selector = [
            discord.SelectOption(
                label=f"#{i}: TH{base.town_hall} {base.base_type}",
                value=i-1,
                description=f"Added: {pendulum.from_timestamp(base.added_on).format('DD MMM YYYY')}",
                emoji=f"{base.source.split(' ',1)[0]}")
                for i,base in enumerate(self.all_bases,1)
                ]
        self.clear_items()
        self.add_item(self.home_button)
        self.add_item(self.base_save)
        self.add_item(self.exit_button)
        self._build_base_select_menu()

        embed1 = await self._browse_bases_embed()
        embed2 = await self._show_base_embed()
        await interaction.followup.edit_message(
            interaction.message.id,
            embeds=[embed1,embed2],
            view=self
            )
    
    async def _callback_select_base(self,interaction:discord.Interaction,menu:DiscordSelectMenu):
        await interaction.response.defer(ephemeral=True)
        self.ctx = interaction

        for item in self.children:
            item.disabled = True        
        await interaction.followup.edit_message(interaction.message.id,view=self)

        self.base_index = int(menu.values[0])
        self._build_base_select_menu()
        
        embed1 = await self._browse_bases_embed()
        embed2 = await self._show_base_embed()
        for item in self.children:
            item.disabled = False
        await interaction.followup.edit_message(
            interaction.message.id,
            embeds=[embed1,embed2],
            view=self
            )        
 
    async def _callback_save_base(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer(ephemeral=True)
        self.ctx = interaction

        for item in self.children:
            item.disabled = True        
        await interaction.followup.edit_message(interaction.message.id,view=self)

        await self.all_bases[self.base_index].add_claim(self.user.id)

        embed1 = await self._browse_bases_embed()
        embed2 = await self._show_base_embed()
        embed3 = await eclipse_embed(
            context=interaction,
            message=f"This base has been added to your bookmarks.",
            success=True
            )
        embed4 = await self._send_base_link_embed()
        embeds = [embed1,embed2,embed4] if embed4 else [embed1,embed2,embed3]

        for item in self.children:
            item.disabled = False

        await interaction.followup.edit_message(
            interaction.message.id,
            embeds=embeds,
            view=self
            )
        
    async def _callback_unsave_base(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer(ephemeral=True)
        self.ctx = interaction

        for item in self.children:
            item.disabled = True        
        await interaction.followup.edit_message(interaction.message.id,view=self)

        await self.all_bases[self.base_index].remove_claim(self.user.id)

        del self.all_bases[self.base_index]
        self.base_index = 0

        embed3 = await eclipse_embed(
            context=interaction,
            message=f"This base has been removed from your bookmarks.",
            success=True
            )
        await interaction.followup.send(embed=embed3,ephemeral=True) 

        if len(self.all_bases) == 0:
            self.vault_button.disabled = True
            embed = await self._browse_bases_embed()
            self._base_vault_main_menu()
            return await interaction.edit_original_response(embed=embed,view=self)

        self.base_selector = [
            discord.SelectOption(
                label=f"#{i}: TH{base.town_hall} {base.base_type}",
                value=i-1,
                description=f"Added: {pendulum.from_timestamp(base.added_on).format('DD MMM YYYY')}",
                emoji=f"{base.source.split(' ',1)[0]}")
                for i,base in enumerate(self.all_bases,1)
                ]
        embed1 = await self._browse_bases_embed()
        embed2 = await self._show_base_embed()
        
        for item in self.children:
            item.disabled = False
            
        await interaction.followup.edit_message(
            interaction.message.id,
            embeds=[embed1,embed2],
            view=self
            )
    
    ##################################################
    ### CONTENT BUILDERS
    ##################################################
    async def _base_vault_home_embed(self,no_base=None):
        base_vault_intro = (f"Welcome to the **E.C.L.I.P.S.E. Base Vault**. "
            + f"\n\nHere in the Base Vault, we have a curated collection of bases ranging from TH9 {EmojisTownHall.get(9)} to TH15 {EmojisTownHall.get(15)}. "
            + f"\n\nAccess to the base vault is a members' privilege. **DO NOT SHARE ANY BASE LINKS WITH ANYONE, INCLUDING FELLOW MEMBERS**."
            + f"\n\n**It is your responsibility to ensure that no one else in Clan Wars are using the same base as you.**"
            + f"\n\n**__Retrieving Bases__**"
            + f"\n- Base Links are provided as-is. Supercell expires base links from time to time, and you may occassionally encounter expired links."
            + f"\n- You may bookmark bases to your Personal Vault for easy retrieval."
            + f"\n- When bookmarking a base, you will also receive the Base Link in your DMs." 
            )        
        embed = await eclipse_embed(
            context=self.ctx,
            title="**E.C.L.I.P.S.E. Base Vault**",
            message=(f"**We don't have any bases currently for Townhall {no_base}.**\n\n" if no_base else '')
                + base_vault_intro
                + "\n\n"
                + "*The Base Vault is supplied by <:RHBB:1041627382018211900> **RH Base Building** and <:BPBB:1043081040090107968> **Blueprint Base Building**.*"
                + "\n\u200b"
            )
        return embed

    async def _browse_bases_embed(self):
        if self.vault_mode:
            embed = await eclipse_embed(
                context=self.ctx,
                title="**Welcome to your Personal Base Vault!**",
                message=f"This is where your bookmarked bases will be saved to, for future reference.\n**You have a total of {len(self.all_bases)} base(s) saved.**"
                    + (f"\n\n**You don't have any bases in your personal vault.** Start by saving some bases from our Members' Vault." if len(self.all_bases) == 0 else '')
                    + (f"\n\nRecently added bases are shown first. To view older bases, use the dropdown menu." if len(self.all_bases) > 0 else '')
                    + f"\n\u200b"
                )
        else:
            embed = await eclipse_embed(
                context=self.ctx,
                title="**E.C.L.I.P.S.E. Base Vault**",
                message=f"There are a total of **{len(self.all_bases)} bases for {EmojisTownHall.get(self.base_th)} Townhall {self.base_th}**."
                    + f"\n\nRecently added bases are shown first. To view older bases, use the dropdown menu."
                    + f"\n\u200b"
                )
        return embed
    
    async def _show_base_embed(self):
        show_base = self.all_bases[self.base_index]
        embed,file = await show_base.base_embed()

        dump_task = asyncio.create_task(self.cog.dump_channel.send(f"{self.user.id} {self.user.name} @ {self.channel.mention}",file=file))        

        embed.add_field(
            name=f"🔍 Bookmarked by: {len(show_base.claims)} member(s)",
            value=f"**You have bookmarked this base.\n\u200b**"
                if self.user.id in show_base.claims else f"\nTo bookmark this Base to your Vault, use the {EmojisUI.DOWNLOAD} button.\n\u200b",
            inline=False
            )
        embed.add_field(
            name="**Base Link**",
            value=f"[Click here to open in-game.]({show_base.base_link})",
            inline=False
            )
        
        dump_message = await dump_task
        embed.set_image(url=dump_message.attachments[0].url)
        self.cog.dump_messages.append(dump_message.id)
        return embed

    async def _send_base_link_embed(self):
        show_base = self.all_bases[self.base_index]
        embed,file = await show_base.base_embed()

        embed.add_field(
            name="**Base Link**",
            value=f"[Click here to open in-game.]({show_base.base_link})",
            inline=False
            )
        try:
            await self.user.send(embed=embed,file=file)
            return None
        except:
            return await eclipse_embed(
                context=self.ctx,
                message="This base has been added to your bookmarks. I couldn't send it to you by DM.",
                success=False
                )
        
    ##################################################
    ### MENU BUILDERS
    ##################################################
    def _base_vault_main_menu(self):
        self.clear_items()
        self.add_item(self.home_button)
        self.add_item(self.vault_button)
        self.add_item(self.exit_button)
 
    def _build_base_select_menu(self):
        if self.base_select_menu:
            self.remove_item(self.base_select_menu)

        if len(self.base_selector) > 25:
            minus_diff = None
            plus_diff = 25
            if 12 < self.base_index < len(self.base_selector) - 25:
                minus_diff = self.base_index - 12
                plus_diff = self.base_index + 13
            elif self.base_index >= len(self.base_selector) - 25:
                minus_diff = len(self.base_selector) - 25
                plus_diff = None
            options = self.base_selector[minus_diff:plus_diff]
        else:
            options = self.base_selector[:25]
        
        for option in options:
            if option.value == self.base_index:
                option.default = True
            else:
                option.default = False
            
        self.base_select_menu = DiscordSelectMenu(
            function=self._callback_select_base,
            options=options,
            placeholder="Select a base to view.",
            min_values=1,
            max_values=1,
            row=1
            )
        self.add_item(self.base_select_menu)