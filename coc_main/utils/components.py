import discord
import pendulum

from typing import *
from redbot.core import commands

from ..api_client import BotClashClient as client

from .constants.coc_constants import *
from .constants.coc_emojis import *
from .constants.ui_emojis import *

from .utils import *
from ..exceptions import ClashOfClansError

_ACCEPTABLE_PAGE_TYPES = Union[Dict[str, Union[str, discord.Embed]], discord.Embed, str]

async def handle_command_error(
    exception:Exception,
    context:Union[discord.Interaction,commands.Context]=None,
    message:Optional[discord.Message]=None):

    bot_client = client()
    
    if isinstance(exception,ClashOfClansError):
        error_embed = await clash_embed(
            context=bot_client.bot,
            message=f"**Error**: {exception.message}",
            success=False,
            timestamp=pendulum.now())
    else:
        error_embed = await clash_embed(
            context=bot_client.bot,
            message=f"An unexpected error occurred. I've forwarded this error to my owners. You may also report this error with `/report`."
                + f"\n\nI apologise for the inconvenience.",
            success=False,
            timestamp=pendulum.now())
    
    if isinstance(context,discord.Interaction):
        try:
            if context.response.is_done():
                await context.edit_original_response(embed=error_embed,view=None)
            else:
                if context.type is discord.InteractionType.application_command:
                    await context.response.send_message(embed=error_embed,ephemeral=True)
                else:
                    await context.response.edit_message(embed=error_embed)
        except discord.NotFound:
            return True
    elif isinstance(context,commands.Context):
        if message:
            await message.edit(embed=error_embed,view=None)
        else:
            await context.reply(embed=error_embed,view=None)
    
    if not isinstance(exception,ClashOfClansError):
        raise

####################################################################################################
#####
##### EMBEDS
#####
####################################################################################################
async def clash_embed(
    context: Union[Red, commands.Context, discord.Interaction],
    title: Optional[str] = None,
    message: Optional[str] = None,
    url: Optional[str] = None,
    show_author: bool = True,
    success: Optional[bool] = None,
    embed_color: Optional[Union[discord.Color, int, str]] = None,
    thumbnail: Optional[str] = None,
    timestamp: Optional[pendulum.datetime] = None,
    image: Optional[str] = None) -> discord.Embed:
    
    bot = None
    user = None
    channel = None    
    if isinstance(context, Red):
        bot = context
        user = None
        channel = await bot.get_or_fetch_user(list(bot.owner_ids)[0])

    elif isinstance(context, commands.Context):
        bot = context.bot
        user = context.author
        channel = context.channel

    elif isinstance(context, discord.Interaction):
        bot = context.client
        user = context.user
        channel = context.channel

    if success is True:
        color = discord.Colour.dark_green()
        
    elif success is False:
        color = discord.Colour.dark_red()

    elif bot and embed_color is not None:
        try:
            color = discord.Colour.from_str(embed_color)
        except (ValueError, TypeError):
            color = await bot.get_embed_color(channel)

    else:
        color = discord.Colour.default()
    
    embed = discord.Embed(
        title=f"{title if title else ''}",
        url=f"{url if url else ''}",
        description=f"{message if message else ''}",
        color=color
        )
    
    if timestamp:
        embed.timestamp = timestamp
    if user and show_author:
        embed.set_author(name=user.display_name,icon_url=user.display_avatar.url)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if image:
        embed.set_image(url=image)
    
    embed.set_footer(text=f"{bot.user.display_name}",icon_url=bot.user.display_avatar.url)
    return embed

####################################################################################################
#####
##### DISCORD UI COMPONENTS
#####
####################################################################################################
class DefaultView(discord.ui.View):
    def __init__(self,context,timeout=120):

        self.is_active = False
        self.waiting_for = False
        self.message = None

        self.ctx = context
        if isinstance(context,commands.Context):
            self.bot = self.ctx.bot
            self.user = self.ctx.author
            self.channel = self.ctx.channel
            self.guild = self.ctx.guild
        elif isinstance(context,discord.Interaction):
            self.bot = self.ctx.client
            self.user = self.ctx.user
            self.channel = self.ctx.channel
            self.guild = self.ctx.guild
        
        super().__init__(timeout=timeout)
    
    ##################################################
    ### OVERRIDE BUILT IN METHODS
    ##################################################
    async def interaction_check(self, interaction:discord.Interaction):
        if not self.is_active:
            await interaction.response.send_message(
                content="This menu is not active.", ephemeral=True
                )
            return False
        if self.waiting_for and interaction.user.id == self.user.id:
            await interaction.response.send_message(
                content="Please respond first!", ephemeral=True
                )
            return False
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                content="This doesn't belong to you!", ephemeral=True
                )
            return False
        self.message = interaction.message
        return True

    async def on_timeout(self):
        timeout_embed = await clash_embed(
            context=self.ctx,
            message="Menu timed out.",
            success=False
            )
        try:
            if self.message:
                await self.message.edit(embed=timeout_embed,view=None)
            elif isinstance(self.ctx,discord.Interaction):
                if self.ctx.response.is_done():
                    await self.ctx.edit_original_response(embed=timeout_embed,view=None)
        except:
            pass
        self.stop_menu()
    
    async def on_error(self, interaction:discord.Interaction, error:Exception, item):
        err = await handle_command_error(error,interaction,self.message)
        if err:
            return
        self.stop_menu()
    
    def stop_menu(self):
        self.is_active = False
        self.waiting_for = False
        self.stop()

class ClanLinkMenu(discord.ui.View):
    def __init__(self,list_of_clans):

        super().__init__(timeout=300)

        for clan in list_of_clans:
            self.add_item(discord.ui.Button(
            label=f"{clan.name}",
            emoji=(f"{clan.emoji}" if clan.is_registered_clan else f"{EmojisClash.CLAN}"),
            style=discord.ButtonStyle.link,
            url=clan.share_link)
            )        
        
    async def on_timeout(self):
        pass

class DiscordModal(discord.ui.Modal):
    def __init__(self,
        function:Coroutine,
        title:str):

        self.function = function
        super().__init__(title=title)
    
    async def on_submit(self,interaction:discord.Interaction):
        await self.function(interaction,self)
    
    def add_field(self,
        label:str,
        style:discord.TextStyle = discord.TextStyle.short,
        placeholder:str = None,
        default:str = None,
        required:bool = False,
        min_length:int = None,
        max_length:int = None):

        self.add_item(discord.ui.TextInput(
            label=label,
            style=style,
            placeholder=placeholder,
            default=default,
            required=required,
            min_length=min_length,
            max_length=max_length))

class DiscordButton(discord.ui.Button):
    def __init__(self,
        function:Coroutine,
        label:Optional[str] = None,
        emoji:Optional[Union[discord.PartialEmoji,discord.Emoji,str]] = None,
        style:Optional[discord.ButtonStyle] = discord.ButtonStyle.gray,
        row:Optional[int] = None,
        reference:Optional[str]=None):
        
        self.function = function
        self.reference = reference
        super().__init__(label=label,emoji=emoji,style=style,row=row)

    async def callback(self,interaction:discord.Interaction):
        await self.function(interaction,self)

class DiscordSelectMenu(discord.ui.Select):
    def __init__(self,
        function:Coroutine,
        options:List[discord.SelectOption],
        placeholder:Optional[str] = "Select an option...",
        min_values:Optional[int] = 1,
        max_values:Optional[int] = 1,
        row:Optional[int] = None,
        reference:Optional[str]=None):
        
        self.function = function
        self.reference = reference
        super().__init__(placeholder=placeholder,min_values=min_values,max_values=max_values,options=options,row=row)
    
    async def callback(self,interaction:discord.Interaction):
        await self.function(interaction,self)

class DiscordUserSelect(discord.ui.UserSelect):
    def __init__(self,
        function:Coroutine,
        placeholder:Optional[str] = "Select a user...",
        min_values:Optional[int] = 1,
        max_values:Optional[int] = 1,
        row:Optional[int] = None):

        self.function = function
        super().__init__(placeholder=placeholder,min_values=min_values,max_values=max_values,row=row)
    
    async def callback(self,interaction:discord.Interaction):
        await self.function(interaction,self)

class DiscordRoleSelect(discord.ui.RoleSelect):
    def __init__(self,
        function:Coroutine,
        placeholder:Optional[str] = "Select a role...",
        min_values:Optional[int] = 1,
        max_values:Optional[int] = 1,
        row:Optional[int] = None):
        
        self.function = function        
        super().__init__(placeholder=placeholder,min_values=min_values,max_values=max_values,row=row)
    
    async def callback(self,interaction:discord.Interaction):
        await self.function(interaction,self)

class DiscordChannelSelect(discord.ui.ChannelSelect):
    def __init__(self,
        function:Coroutine,
        channel_types:Optional[List[discord.ChannelType]],
        placeholder:Optional[str] = "Select a channel...",
        min_values:Optional[int] = 1,
        max_values:Optional[int] = 1,
        row:Optional[int] = None):
        
        self.function = function        
        super().__init__(channel_types=channel_types,placeholder=placeholder,min_values=min_values,max_values=max_values,row=row)
    
    async def callback(self,interaction:discord.Interaction):
        await self.function(interaction,self)

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