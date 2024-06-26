import asyncio
import discord
import pendulum

from typing import *
from redbot.core import commands,bank

from coc_main.utils.components import DefaultView, DiscordButton, DiscordSelectMenu
from coc_main.utils.constants.coc_emojis import EmojisTownHall
from coc_main.utils.constants.ui_emojis import EmojisUI

from ..objects.war_base import eWarBase
from ..components import eclipse_embed

base_price = 5000
max_th = 16

def calculate_price(townhall:int):
    return max(base_price - ((max_th - townhall) * 500),1000)

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
    def has_pass(self) -> bool:
        cog = self.bot.get_cog("ECLIPSE")
        if not cog.vault_pass_guild:
            return False
        if not cog.vault_pass:
            return False
        
        guild_user = cog.vault_pass_guild.get_member(self.user.id)
        if not guild_user:
            return False
        if cog.vault_pass in guild_user.roles:
            return True
        return False
    
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
            label="Claim Base",
            emoji=EmojisUI.DOWNLOAD,
            row=0
            )
    
    @property
    def base_unsave(self):
        return DiscordButton(
            function=self._callback_unsave_base,
            label="Delete Claim",
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
            for th in [16,15,14,13,12,11,10,9]]
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
            for th in [16,15,14,13,12,11,10,9]]
        
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

        base = self.all_bases[self.base_index]
        price = 0 if self.has_pass else calculate_price(base.town_hall)

        if self.user.id not in base.claims:
            if not await bank.can_spend(self.bot.get_user(interaction.user.id),price):
                embed3 = await eclipse_embed(
                    context=interaction,
                    message=f"You don't have enough coins to claim this base. You need {price:,} {await bank.get_currency_name()}. You have {await bank.get_balance(self.user):,} {await bank.get_currency_name()}.",
                    success=False
                    )
            else:
                await base.add_claim(self.user.id)
                embed3 = await self._send_base_link_embed()
                if not embed3:
                    embed3 = await eclipse_embed(
                        context=interaction,
                        message=f"This base has been added to your vault.",
                        success=True
                        )
                if price > 0:
                    await bank.withdraw_credits(self.user,price)
                    embed3.description += f"\n\nYou have {await bank.get_balance(self.user):,} {await bank.get_currency_name()} left."
        
        else:
            embed3 = await self._send_base_link_embed()
            if not embed3:
                embed3 = await eclipse_embed(
                    context=interaction,
                    message=f"I've sent you the base link via DMs.",
                    success=True
                    )
            
        embed1 = await self._browse_bases_embed()
        embed2 = await self._show_base_embed()
        
        embeds = [embed1,embed2,embed3]

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
        curr = await bank.get_currency_name()

        base_vault_intro = (f"Welcome to the **E.C.L.I.P.S.E. Base Vault**. "
            + f"\n\nWe have a curated collection of bases ranging from **TH9 {EmojisTownHall.get(9)}** to **TH16 {EmojisTownHall.get(16)}**. "
            + f"Bases are refreshed periodically, and expire after a certain period of time:"
            + f"\n- {EmojisTownHall.get(max_th)} TH{max_th}: after 4 month(s)"
            + f"\n- {EmojisTownHall.get(max_th-1)} TH{max_th-1}: after 6 month(s)"
            + f"\n- {EmojisTownHall.get(max_th-2)} TH{max_th-2}: after 9 month(s)"
            + f"\n- Other THs: after 12 month(s)"
            + f"\n\n**It is your responsibility to ensure that no one else in Clan Wars are using the same base as you.**"
            + f"\n\n**__Getting Base Links__**"
            + f"\n- Base Links are provided as-is. Supercell expires base links from time to time, and you may occassionally encounter expired links."
            + f"\n- To get a base link, you will need to claim a base. Claiming a base costs 5,000 {curr} for the highest TH. Lower TH levels cost less."
            + f"\n- Purchasing a Vault Pass lets you access bases for free for a limited period. Vault Passes can only be purchased from The Assassins Guild."
            + f"\n- Once claimed, the base link is sent to your DMs and added to your Personal Vault."
            + f"\n\n**__Personal Vault__**"
            + f"\n- Bases that you have claimed are added to your personal vault. You may retrieve their base links at any time from here."
            + f"\n- You may delete claims from your personal vault."
            + f"\n- Bases in your personal vault are not subject to the expiration, unless you delete the claim."
            )        
        embed = await eclipse_embed(
            context=self.ctx,
            title="**E.C.L.I.P.S.E. Base Vault**",
            message=(f"## Oops!\n**We currently don't have any bases for Townhall {no_base}.**\n\n" if no_base else '')
                + base_vault_intro
                + "\n\n"
                + "*The Base Vault is supplied by <:RHBB:1223194612902920234> **RH Base Building** and <:BPBB:1043081040090107968> **Blueprint Base Building**.*"
                + "\n\u200b"
            )
        return embed

    async def _browse_bases_embed(self):
        if self.vault_mode:
            embed = await eclipse_embed(
                context=self.ctx,
                title="**Welcome to your Personal Base Vault!**",
                message=f"This is where your base claims will be saved to.\n**You have a total of {len(self.all_bases)} base(s) claimed.**"
                    + (f"\n\n**You don't have any bases in your personal vault.** Start by saving some bases from the Assassins Vault." if len(self.all_bases) == 0 else '')
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

        if self.has_pass:
            price_text = f"Claiming this base is free thanks to your Vault Pass!\n\u200b"
        else:
            price_text = f"Claiming will cost: **{calculate_price(show_base.town_hall):,} {await bank.get_currency_name()}**. You have: {await bank.get_balance(self.user):,} {await bank.get_currency_name()}.\n\u200b"

        embed.add_field(
            name=f"🔍 Claimed by: {len(show_base.claims)} member(s)",
            value=f"**You have already claimed this base.**" + ("\nYou may claim again for free to receive the Base Link in your DMs.\n\u200b" if not self.vault_mode else "\n\u200b")
                if self.user.id in show_base.claims else 
                f"\nTo claim this Base, use the {EmojisUI.DOWNLOAD} button.\n{price_text}",
            inline=False
            )
        
        if self.user.id in show_base.claims:
            embed.add_field(
                name="**Base Link**",
                value=f"[Click here to open in-game.]({show_base.base_link})",
                inline=False
                )
        
        if file:
            dump_message = await self.cog.dump_channel.send(f"{self.user.id} {self.user.name} @ {self.channel.mention}",file=file)
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
                message="This base has been added to your claims. I couldn't send it to you by DM.",
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