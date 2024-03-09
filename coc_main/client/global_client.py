import asyncio
import discord
import random
import logging
import pendulum
import coc
import motor.motor_asyncio

from typing import *
from redbot.core.bot import Red
from redbot.core import commands, app_commands
from redbot.core.commands import Context
from concurrent.futures import ThreadPoolExecutor

from .coc_client import ClashClient
from ..exceptions import ProjectGError

COC_LOG = logging.getLogger("coc.main")

class GlobalClient():
    coc_client:ClassVar[ClashClient] = None
    database:ClassVar[motor.motor_asyncio.AsyncIOMotorDatabase] = None
    thread_pool:ClassVar[ThreadPoolExecutor] = ThreadPoolExecutor(max_workers=4)
    task_queue = asyncio.Queue(maxsize=1000)

    bot:ClassVar[Red] = None
    _ready = False

    @classmethod
    def start_client(cls,bot:Red) -> 'GlobalClient':        
        GlobalClient.bot = bot
        return cls
    
    @classmethod
    def run_in_thread(cls,func,*args):
        def _run_func(func, *args):
            try:
                return func(*args)
            except Exception as exc:
                COC_LOG.exception(f"Error in thread: {exc}")
        loop = asyncio.get_running_loop()
        return loop.run_in_executor(cls.thread_pool, _run_func, func, *args)

    @classmethod
    async def update_bot_status(cls,cooldown:int,text:str):
        #cooldown in minutes
        diff = pendulum.now().int_timestamp - getattr(cls.bot.last_status_update,'int_timestamp',0)
        if cls.bot.last_status_update and diff < (cooldown*60):
            return
        
        activity_types = [
            discord.ActivityType.playing,
            discord.ActivityType.listening,
            discord.ActivityType.watching
            ]
        activity_select = random.choice(activity_types)

        try:
            await cls.bot.wait_until_ready()
            await cls.bot.change_presence(
                activity=discord.Activity(
                    type=activity_select,
                    name=text))
        except Exception as exc:
            COC_LOG.exception(f"Bot Status Update Error: {exc}")
        else:
            cls.bot.last_status_update = pendulum.now()
            COC_LOG.info(f"Bot Status Updated: {text}.")
    
    @staticmethod
    def get_exception_response(exception:Exception) -> str:
        if isinstance(exception,coc.HTTPException):
            if exception.status == 404:
                COC_LOG.exception(f"Clash of Clans API HTTP Error: {exception}")
                return "The requested Tag doesn't seem to be valid."
                
            elif exception.status in [502,503,504]:
                COC_LOG.exception(f"Clash of Clans API HTTP Error: {exception}")
                return "The Clash of Clans API is currently unavailable."

            else:
                COC_LOG.exception(f"Clash of Clans API HTTP Error: {exception}")
                return "The Clash of Clans API is currently unavailable."
        else:
            COC_LOG.exception(f"{exception}")
            return f"{exception}"

    @classmethod
    async def handle_command_error(cls,
        exception:Exception,
        context:Union[discord.Interaction,commands.Context]=None,
        message:Optional[discord.Message]=None):

        if isinstance(exception,coc.ClashOfClansException) or isinstance(exception,ProjectGError):
            response = cls.get_exception_response(exception)
            error_embed = discord.Embed(
                description=response,
                color=discord.Colour.dark_red(),
                timestamp=pendulum.now()
                )
            error_embed.set_footer(text=f"{cls.bot.user.display_name}",icon_url=cls.bot.user.display_avatar.url)
            
            if isinstance(context,discord.Interaction):
                try:
                    if context.response.is_done():
                        await context.edit_original_response(embed=error_embed,view=None)
                    else:
                        if context.type is discord.InteractionType.application_command:
                            await context.response.send_message(embed=error_embed,ephemeral=True)
                        else:
                            await context.response.edit_message(embed=error_embed)
                except:
                    return True
                
            elif isinstance(context,commands.Context):
                try:
                    if message:
                        await message.edit(embed=error_embed,view=None)
                    else:
                        await context.reply(embed=error_embed,view=None)
                except:
                    return True
        
        if isinstance(context,discord.Interaction):
            try:
                context = await Context.from_interaction(context)
            except:
                return
        await cls.bot.on_command_error(context,exception,unhandled_by_cog=True)