import discord

from typing import *

from redbot.core import commands

from coc_main.discord.recruiting_reminder import RecruitingReminder
from coc_main.utils.components import DiscordButton, DiscordModal, DefaultView

class CreateRecruitingReminder(DefaultView):
    def __init__(self,
        context:[Union[commands.Context,discord.Interaction]],
        channel:discord.TextChannel,
        user_to_review:discord.Member):

        self.reminder_channel = channel
        self.reminder_user = user_to_review

        self.open_modal_button = DiscordButton(
            function=self._send_post_modal,
            label="Click to Create Recruiting Reminder",
            style=discord.ButtonStyle.blurple
            )
        
        super().__init__(context,timeout=120)        
        self.add_item(self.open_modal_button)

        self.reminder_modal = DiscordModal(
            function=self._callback_create_reminder,
            title=f"Create Reminder",
            )
        name_field = discord.ui.TextInput(
            label="Ad/Reminder Name",
            placeholder="Descriptive Name of this Ad/Reminder.",
            max_length=30,
            style=discord.TextStyle.short,
            required=True
            )
        link_field = discord.ui.TextInput(
            label="Ad/Reminder Link",
            placeholder="Link to the Ad/Reminder",
            style=discord.TextStyle.short,
            required=True
            )
        interval_field = discord.ui.TextInput(
            label="Ad/Reminder Interval",
            placeholder="Reminder Interval in hours (max 99)",
            style=discord.TextStyle.short,
            max_length=2,
            required=True
            )
        self.reminder_modal.add_item(name_field)
        self.reminder_modal.add_item(link_field)
        self.reminder_modal.add_item(interval_field)

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
            await self.ctx.reply(f"Click the button below to create a new Recruiting Reminder in {self.reminder_channel.mention}.",view=self)
        elif isinstance(self.ctx,discord.Interaction):
            await self.ctx.edit_original_response(content=f"Click the button below to create a new Recruiting Reminder in {self.reminder_channel.mention}.",view=self)
        
    async def _send_post_modal(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.send_modal(self.reminder_modal)
    
    async def _callback_create_reminder(self,interaction:discord.Interaction,modal:DiscordModal):
        await interaction.response.defer(ephemeral=True)

        name = modal.children[0].value
        link = modal.children[1].value
        interval = modal.children[2].value

        new_reminder = await RecruitingReminder.create(
            channel=self.reminder_channel,
            user_to_remind=self.reminder_user,
            name=name,
            link=link,
            interval=int(interval)
            )
        await new_reminder.send_reminder()
        
        await interaction.followup.send(f"Your Recruiting Reminder has been created.",ephemeral=True)