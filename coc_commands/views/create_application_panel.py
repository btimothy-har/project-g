import discord
import asyncio

from typing import *

from coc_data.objects.discord.guild import aGuild

from coc_data.utilities.components import *

from coc_data.constants.ui_emojis import *
from coc_data.constants.coc_emojis import *
from coc_data.constants.coc_constants import *

from coc_data.exceptions import *

class CreateApplicationMenu(DefaultView):
    def __init__(self,
        context:[Union[commands.Context,discord.Interaction]],
        channel:discord.TextChannel,
        listener:discord.TextChannel,
        choose_clans:bool=True,):

        self.target_channel = channel
        self.listener_channel = listener
        self.choose_clans = choose_clans

        self.open_modal_button = DiscordButton(
            function=self._send_post_modal,
            label="Click to Create Application Menu",
            style=discord.ButtonStyle.blurple
            )
        
        super().__init__(context,timeout=120)        
        self.add_item(self.open_modal_button)

        self.application_modal = DiscordModal(
            function=self._callback_create_application,
            title=f"Create Application Menu",
            )
        prefix_field = discord.ui.TextInput(
            label="Specify the TicketTool bot prefix.",
            style=discord.TextStyle.short,
            max_length=3,
            required=True
            )
        q1_field = discord.ui.TextInput(
            label="Q1.",
            placeholder="Question can only be 45 characters long. If you wish to add a placeholder, add it on a new line.",
            style=discord.TextStyle.long,
            required=True
            )
        q2_field = discord.ui.TextInput(
            label="Q2.",
            placeholder="Question can only be 45 characters long. If you wish to add a placeholder, add it on a new line.",
            style=discord.TextStyle.long,
            required=True
            )
        q3_field = discord.ui.TextInput(
            label="Q3.",
            placeholder="Question can only be 45 characters long. If you wish to add a placeholder, add it on a new line.",
            style=discord.TextStyle.long,
            required=True
            )
        q4_field = discord.ui.TextInput(
            label="Q4.",
            placeholder="Question can only be 45 characters long. If you wish to add a placeholder, add it on a new line.",
            style=discord.TextStyle.long,
            required=True
            )
        self.application_modal.add_item(prefix_field)
        self.application_modal.add_item(q1_field)
        self.application_modal.add_item(q2_field)
        self.application_modal.add_item(q3_field)
        self.application_modal.add_item(q4_field)

    ##################################################
    ### OVERRIDE BUILT IN METHODS
    ##################################################
    async def on_timeout(self):
        self.is_active = False
        self.open_modal_button.label = "Sorry, you timed out! Please try again."
        self.open_modal_button.disabled = True
        await self.message.edit(view=self)
        self.stop_menu()

    ##################################################
    ### CALLBACK METHODS
    ################################################## 
    async def start(self):
        self.is_active = True
        if isinstance(self.ctx,commands.Context):
            await self.ctx.reply(f"Click the button below to create a new Clan Application Menu in {self.target_channel.mention}.",view=self)
        elif isinstance(self.ctx,discord.Interaction):
            await self.ctx.edit_original_response(content=f"Click the button below to create a new Clan Application Menu in {self.target_channel.mention}.",view=self)
        
    async def _send_post_modal(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.send_modal(self.application_modal)
    
    async def _callback_create_application(self,interaction:discord.Interaction,modal:DiscordModal):
        await interaction.response.defer(ephemeral=True)

        prefix = modal.children[0].value
        q1 = modal.children[1].value.split('\n')
        q2 = modal.children[2].value.split('\n')
        q3 = modal.children[3].value.split('\n')
        q4 = modal.children[4].value.split('\n')

        guild = aGuild(interaction.guild.id)
        new_panel = await guild.create_apply_panel(self.target_channel)

        new_panel.tickettool_prefix = prefix
        new_panel._tickettool_channel = self.listener_channel.id
        new_panel.can_user_select_clans = self.choose_clans

        new_panel.text_q1 = q1[0][:45]
        if len(q1) > 1:
            new_panel.placeholder_q1 = q1[1]

        new_panel.text_q2 = q2[0][:45]
        if len(q2) > 1:
            new_panel.placeholder_q2 = q2[1]

        new_panel.text_q3 = q3[0][:45]
        if len(q3) > 1:
            new_panel.placeholder_q3 = q3[1]

        new_panel.text_q4 = q4[0][:45]
        if len(q4) > 1:
            new_panel.placeholder_q4 = q4[1]

        new_panel.save()
        while True:
            try:
                await aGuild.update_apply_panels(interaction.guild.id)
            except CacheNotReady:
                await asyncio.sleep(10)
            else:
                break
        await interaction.followup.send(f"Your Application Menu has been created.",ephemeral=True)