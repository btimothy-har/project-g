import discord
import pendulum

from typing import *

from redbot.core.bot import Red
from redbot.core import commands

from coc_client.exceptions import *

from ..constants.coc_emojis import EmojisClash

async def handle_command_error(
    exception:Exception,
    context:Union[discord.Interaction,commands.Context]=None,
    message:Optional[discord.Message]=None):
    
    if isinstance(exception,ClashOfClansError):
        error_embed = await clash_embed(
            context=context,
            message=f"**Error**: {exception.message}",
            success=False,
            timestamp=pendulum.now())
    else:
        error_embed = await clash_embed(
            context=context,
            message=f"An unexpected error occurred. I've forwarded this error to my owners."
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