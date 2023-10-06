import discord

from typing import *
from redbot.core import commands

from coc_data.constants.coc_emojis import *
from coc_data.constants.ui_emojis import *

from coc_data.utilities.components import *
from coc_data.utilities.utils import *

from coc_data.exceptions import *

_ACCEPTABLE_PAGE_TYPES = Union[Dict[str, Union[str, discord.Embed]], discord.Embed, str]

####################################################################################################
#####
##### VIEW MENU: YES/NO CONFIRMATION
#####
####################################################################################################
class MenuConfirmation(discord.ui.View):
    def __init__(self,
        context: Union[commands.Context,discord.Interaction]):

        self.confirmation = None

        if isinstance(context, commands.Context):
            self.user = context.author
            self.channel = context.channel
            self.guild = context.guild
        elif isinstance(context, discord.Interaction):
            self.user = context.user
            self.channel = context.channel
            self.guild = context.guild
        
        self.yes_button = DiscordButton(
            function=self.yes_callback,
            label="",
            emoji=EmojisUI.YES,
            style=discord.ButtonStyle.green,
            )
        self.no_button = DiscordButton(
            function=self.no_callback,
            label="",
            emoji=EmojisUI.NO,
            style=discord.ButtonStyle.grey,
            )

        super().__init__(timeout=60)

        self.add_item(self.yes_button)
        self.add_item(self.no_button)
    
    ##################################################
    ### OVERRIDE BUILT IN METHODS
    ##################################################
    async def interaction_check(self, interaction:discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                content="This doesn't belong to you!", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        self.clear_items()
        self.stop()
    
    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        await handle_command_error(interaction,error)
    
    ##################################################
    ### CALLBACKS
    ##################################################
    async def yes_callback(self,interaction:discord.Interaction,button:DiscordButton):
        self.confirmation = True
        await interaction.response.edit_message(view=None)
        self.clear_items()
        self.stop()
    
    async def no_callback(self,interaction:discord.Interaction,button:DiscordButton):
        self.confirmation = False
        await interaction.response.edit_message(view=None)
        self.clear_items()
        self.stop()

    # async def run_token_confirmation(self):
    #     util_msgs = []
    #     def token_check(m):
    #         return m.author.id == self.ctx.author.id and ((m.channel.id == self.ctx.channel.id) or (m.channel.type == self.ctx.channel.type == discord.ChannelType.private)) and m.content.strip() == self.token

    #     self.token = "".join(random.choices((*ascii_letters, *digits), k=16))

    #     confirm_embed = await clash_embed(self.ctx,
    #         message=f"Please confirm the requested action by sending the token below as your next message.\n**You have 60 seconds to respond.**")
    #     confirm_msg = await self.ctx.send(content=f"{ctx.author.mention}",embed=confirm_embed)
    #     token_msg = await self.ctx.send(f"```{confirm_token}```")

    #     util_msgs.append(confirm_msg)

    #     try:
    #         reply_message = await self.ctx.bot.wait_for("message",timeout=60,check=token_check)
    #     except asyncio.TimeoutError:
    #         timeout_embed = await clash_embed(self.ctx,message="Did not receive a valid confirmation.",color='fail')
    #         await confirm_msg.edit(embed=timeout_embed)
    #         await token_msg.delete()
    #         await self.run_clean_up(messages=util_msgs,delay=15)
    #         return False
    #     else:
    #         success_embed = await clash_embed(self.ctx,message="Confirmation successful.",color='success')
    #         await token_msg.edit(embed=success_embed)
    #         await reply_message.delete()
    #         await token_msg.delete()
    #         await self.run_clean_up(messages=util_msgs,delay=15)
    #         return True

####################################################################################################
#####
##### VIEW MENU: MULTIPLE CHOICE SELECT
#####
####################################################################################################
class MultipleChoiceSelectionMenu(discord.ui.View):
    def __init__(self,
        context: Union[commands.Context,discord.Interaction],
        timeout:int = 180,
        timeout_function:Optional[Coroutine] = None,
        error_function:Optional[Coroutine] = None):
        
        self.timeout_function = timeout_function
        self.error_function = error_function
        self.return_value = None

        if isinstance(context, commands.Context):
            self.user = context.author
            self.channel = context.channel
            self.guild = context.guild
        elif isinstance(context, discord.Interaction):
            self.user = context.user
            self.channel = context.channel
            self.guild = context.guild

        super().__init__(timeout=timeout)

        self.stop_button = DiscordButton(
            function=self.stop_menu,
            label="",
            emoji=EmojisUI.EXIT,
            style=discord.ButtonStyle.red,
            )
        self.add_item(self.stop_button)        
    
    ##################################################
    ### OVERRIDE BUILT IN METHODS
    ##################################################
    async def interaction_check(self, interaction:discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                content="This doesn't belong to you!", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        self.clear_items()
        self.stop()
        if self.timeout_function:
            await self.timeout_function()        
    
    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        if self.error_function:
            await self.error_function(interaction,error)
        else:
            await handle_command_error(interaction,error)

    ##################################################
    ### STOP / CALLBACKS
    ##################################################
    async def stop_menu(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.edit_message(view=None)
        self.stop()
    
    async def callback_select_item(self,interaction:discord.Interaction,button:DiscordButton):
        self.return_value = button.reference
        await interaction.response.edit_message(view=None)
        self.stop()
    
    ##################################################
    ### ADD ITEM HELPER
    ##################################################
    def add_list_item(self,
        reference:str,
        label:str,
        emoji:Optional[Union[discord.PartialEmoji,discord.Emoji,str]] = None):

        self.remove_item(self.stop_button)
        self.add_item(DiscordButton(
            function=self.callback_select_item,
            label=label,
            emoji=emoji,
            reference=reference))
        self.add_item(self.stop_button)

####################################################################################################
#####
##### VIEW MENU: PAGINATOR
#####
####################################################################################################
class MenuPaginator(discord.ui.View):
    def __init__(self,
        context: Union[commands.Context,discord.Interaction],
        message_list: List[_ACCEPTABLE_PAGE_TYPES],
        timeout:int = 300):

        self.ctx = context
        if isinstance(context, commands.Context):
            self.bot = context.bot
            self.user = context.author
            self.channel = context.channel
            self.guild = context.guild
        elif isinstance(context, discord.Interaction):
            self.bot = context.client
            self.user = context.user
            self.channel = context.channel
            self.guild = context.guild
    
        self.page_index = 0
        self.paginate_options = message_list

        self.message = None

        self.first_page_button = DiscordButton(function=self.to_first_page,style=discord.ButtonStyle.gray,emoji=EmojisUI.GREEN_FIRST)
        self.previous_page_button = DiscordButton(function=self.to_previous_page,style=discord.ButtonStyle.gray,emoji=EmojisUI.GREEN_PREVIOUS)
        self.next_page_button = DiscordButton(function=self.to_next_page,style=discord.ButtonStyle.gray,emoji=EmojisUI.GREEN_NEXT)
        self.last_page_button = DiscordButton(function=self.to_last_page,style=discord.ButtonStyle.gray,emoji=EmojisUI.GREEN_LAST)
        self.stop_button = DiscordButton(function=self.stop_menu,style=discord.ButtonStyle.red,emoji=EmojisUI.EXIT)
        
        super().__init__(timeout=timeout)
    
    async def start(self):
        if len(self.paginate_options) > 3:
            self.add_item(self.first_page_button)

        self.add_item(self.previous_page_button)
        self.add_item(self.next_page_button)
        if len(self.paginate_options) > 3:
            self.add_item(self.last_page_button)
        self.add_item(self.stop_button)

        kwargs = self.get_content()
        if isinstance(self.ctx,discord.Interaction):
            await self.ctx.edit_original_response(**kwargs)
        else:
            self.message = await self.ctx.reply(**kwargs)
    
    ##################################################
    ### OVERRIDE BUILT IN METHODS
    ##################################################    
    async def interaction_check(self, interaction:discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                content="This doesn't belong to you!", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        self.clear_items()
        self.stop()
        if self.message:
            await self.message.edit(view=None)
        else:
            await self.ctx.edit_original_response(view=None)        
    
    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        await handle_command_error(error,interaction,self.message)

    ##################################################
    ### NAVIGATION CALLBACKS
    ##################################################
    async def to_first_page(self,interaction:discord.Interaction,button:DiscordButton):
        self.page_index = 0
        kwargs = self.get_content()
        await interaction.response.edit_message(**kwargs)

    async def to_previous_page(self,interaction:discord.Interaction,button:DiscordButton):
        if self.page_index-1 < 0:
            self.page_index = len(self.paginate_options)-1
        else:
            self.page_index -= 1
        kwargs = self.get_content()
        await interaction.response.edit_message(**kwargs)

    async def to_next_page(self,interaction:discord.Interaction,button:DiscordButton):
        if self.page_index+1 >= len(self.paginate_options):
            self.page_index = 0
        else:
            self.page_index += 1
        kwargs = self.get_content()
        await interaction.response.edit_message(**kwargs)

    async def to_last_page(self,interaction:discord.Interaction,button:DiscordButton):
        self.page_index = len(self.paginate_options)-1
        kwargs = self.get_content()
        await interaction.response.edit_message(**kwargs)
    
    async def stop_menu(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.edit_message(view=None)
        self.stop()
    
    ##################################################
    ### CONTENT / MENU BUILDERS
    ##################################################
    def get_content(self):
        content = self.paginate_options[self.page_index]
        ret: Dict[str, Any] = {'view':self}

        if isinstance(content,str):
            ret.update({'content':content,'embed':None})
        elif isinstance(content,discord.Embed):
            if not getattr(content.footer,'text','').startswith('Page'):
                content.set_footer(
                    text=f"Page {self.page_index+1}/{len(self.paginate_options)} - {getattr(content.footer,'text','')}",
                    icon_url=getattr(content.footer,'icon_url',None)
                    )
            ret.update({'content':None,'embed':content})
        elif isinstance(content,dict):
            ret.update({'content':content.get('content'),'embed':content.get('embed')})
        return ret