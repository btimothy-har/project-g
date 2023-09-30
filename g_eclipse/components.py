import discord
import pendulum

from typing import *

from redbot.core.bot import Red
from redbot.core import commands


async def eclipse_embed(
    context: Union[Red, commands.Context, discord.Interaction],
    title: Optional[str] = None,
    message: Optional[str] = None,
    url: Optional[str] = None,
    success: Optional[bool] = None,
    embed_color: Optional[Union[discord.Color, int, str]] = None,
    thumbnail: Optional[str] = None,
    timestamp: Optional[pendulum.datetime] = None,
    image: Optional[str] = None) -> discord.Embed:
    
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
    elif embed_color is not None:
        try:
            color = discord.Colour.from_str(embed_color)
        except (ValueError, TypeError):
            color = discord.Colour.light_embed()
    else:
        color = discord.Colour.light_embed()
    
    embed = discord.Embed(
        title=f"{title if title else ''}",
        url=f"{url if url else ''}",
        description=f"{message if message else ''}",
        color=color
        )
    
    embed.set_author(name="E.C.L.I.P.S.E.",icon_url=bot.user.display_avatar.url)
    
    if timestamp:
        embed.timestamp = timestamp
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if image:
        embed.set_image(url=image)
        
    embed.set_footer(text=f"{bot.user.display_name}")
    return embed