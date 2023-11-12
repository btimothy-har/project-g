import os
import logging
import pendulum
import random
import asyncio

import coc
from coc.ext import discordlinks

from typing import *
from mongoengine import *

from art import text2art
from concurrent.futures import ThreadPoolExecutor
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import humanize_list

from .coc_objects.season.mongo_season import dSeason
from .coc_objects.season.season import aClashSeason
from .exceptions import *

coc_main_logger = logging.getLogger("coc.main")
coc_main_logger.setLevel(logging.INFO)

coc_data_logger = logging.getLogger("coc.data")
coc_data_logger.setLevel(logging.INFO)

clashlinks_log = logging.getLogger("coc.links")
clashlinks_log.setLevel(logging.INFO)

############################################################
############################################################
#####
##### CACHE CLASS
#####
############################################################
############################################################
class DataCache():
    def __init__(self,bot,cache_name):
        self.bot = bot
        self.cache_name = cache_name
        self.cache = {}    
        self.queue = []

    def __len__(self):
        return len(self.cache)
    
    @property
    def keys(self):
        return list(self.cache.keys())
    
    @property
    def values(self):
        return list(self.cache.values())
    
    def set(self,key,value):
        self.cache[key] = value

    def get(self,key):
        return self.cache.get(key,None)
    
    def delete(self,key:str):
        if key in self.cache:
            del self.cache[key]

    def add_to_queue(self,key:str):
        if key not in self.queue and key not in self.cache:
            self.queue.append(key)
    
    async def add_many_to_queue(self,keys:List[str]):
        aiter = AsyncIter(keys)
        async for key in aiter:
            self.add_to_queue(key)

    def remove_from_queue(self,key:str):
        if key in self.queue:
            self.queue.remove(key)

############################################################
############################################################
#####
##### CLIENT CLASS
#####
############################################################
############################################################
class BotClashClient():
    _instance = None

    def __new__(cls,bot:Optional[Red]=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._is_initialized = False
            cls._instance._api_logged_in = False
        return cls._instance
    
    def __init__(self,bot:Optional[Red]=None):
        if not bot and not self._is_initialized:
            raise Exception("BotClashClient must be initialized with a bot instance.")
        
        if not self._is_initialized:
            self.bot = bot
            self.api_maintenance = False
            self._current_season = None
            self._tracked_seasons = []

            self.thread_pool = ThreadPoolExecutor(max_workers=16)

            self.last_status_update = None
            self.client_keys = []

            self.coc_main_log = coc_main_logger
            self.coc_data_log = coc_data_logger
            self.discordlinks_log = clashlinks_log

            log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
            main_logpath = f"{self.bot.coc_log_path}/main"
            if not os.path.exists(main_logpath):
                os.makedirs(main_logpath)
            cocmain_log_handler = logging.handlers.RotatingFileHandler(
                f"{main_logpath}/main.log",
                maxBytes=3*1024*1024,
                backupCount=9
                )
            cocmain_log_handler.setFormatter(log_formatter)
            self.coc_main_log.addHandler(cocmain_log_handler)

            data_logpath = f"{self.bot.coc_log_path}/data"
            if not os.path.exists(data_logpath):
                os.makedirs(data_logpath)
            cocdata_log_handler = logging.handlers.RotatingFileHandler(
                f"{data_logpath}/data.log",
                maxBytes=10*1024*1024,
                backupCount=9
                )
            cocdata_log_handler.setFormatter(log_formatter)
            self.coc_data_log.addHandler(cocdata_log_handler)

            clashlinks_logpath = f"{self.bot.coc_log_path}/discordlinks"
            if not os.path.exists(clashlinks_logpath):
                os.makedirs(clashlinks_logpath)
            clashlinks_log_handler = logging.handlers.RotatingFileHandler(
                f"{clashlinks_logpath}/discordlinks.log",
                maxBytes=3*1024*1024,
                backupCount=9
                )
            clashlinks_log_handler.setFormatter(log_formatter)
            self.discordlinks_log.addHandler(clashlinks_log_handler)

            self.coc_client = None

            self.discordlinks_sandbox = False
            self.discordlinks_client = None
    
    def run_in_thread(self, func, *args):
        def _run_func(func, *args):
            try:
                return func(*args)
            except Exception as exc:
                self.coc_main_log.exception(f"Error in thread: {exc}")
        loop = asyncio.get_running_loop()
        return loop.run_in_executor(self.thread_pool, _run_func, func, *args)
    
    @classmethod
    async def initialize(cls,
        bot:Red,
        author:str,
        version:str,
        client_keys:Optional[List[str]]=None,
        throttler:Optional[int]=None):

        instance = cls(bot)

        if instance._is_initialized:
            return instance

        instance.author = author
        instance.version = version
        instance.client_keys = client_keys or []
        instance.throttler = throttler or 0

        await instance.database_login()
        await instance.api_login()
        await instance.discordlinks_login()
        await instance.load_seasons()

        instance._is_initialized = True
        return instance
    
    async def shutdown(self):
        await self.api_logout()

        for handler in self.discordlinks_log.handlers:
            self.discordlinks_log.removeHandler(handler)
            
        self._is_initialized = False
    
    @property
    def coc(self) -> coc.EventsClient:
        return self.bot.coc_client
    
    ##################################################
    #####
    ##### CLASH SEASONS
    #####
    ##################################################  
    async def load_seasons(self):
        def _find_current():
            try:
                s = dSeason.objects.get(s_is_current=True)
            except DoesNotExist:
                s = None
            return getattr(s,'s_id',None)

        def _find_tracked():
            s = dSeason.objects(s_is_current=False).only('s_id')
            return [ss.s_id for ss in s]
        
        def _delete_invalid(ss):
            dSeason.objects(s_id=ss).delete()
        
        season_id = await self.run_in_thread(_find_current)
        if season_id:
            self._current_season = aClashSeason(str(season_id))
        else:
            self._current_season = aClashSeason.get_current_season()
            await self._current_season.set_as_current()
        
        self.coc_main_log.info(f"Current Season: {self.current_season.description}")

        tracked_seasons = await self.run_in_thread(_find_tracked)
        aiter = AsyncIter(tracked_seasons)
        async for ss in aiter:
            try:
                s = aClashSeason(str(ss))
            except:
                await self.run_in_thread(_delete_invalid,ss)
                self.coc_main_log.warning(f"Invalid Season: {ss} deleted.")
            else:
                self._tracked_seasons.append(s)

        self.coc_main_log.info(f"Tracked Seasons: {humanize_list([ss.description for ss in self.tracked_seasons])}")
    
    @property
    def current_season(self) -> aClashSeason:
        return self._current_season
    
    @property
    def tracked_seasons(self) -> list[aClashSeason]:
        return sorted(self._tracked_seasons,key=lambda x:x.season_start,reverse=True)

    ##################################################
    #####
    ##### CACHE
    #####
    ##################################################
    @property
    def player_cache(self) -> DataCache:
        if not hasattr(self.bot,"coc_player_cache"):
            self.bot.coc_player_cache = DataCache(self.bot,"players")
        return self.bot.coc_player_cache

    @property
    def clan_cache(self) -> DataCache:
        if not hasattr(self.bot,"coc_clan_cache"):
            self.bot.coc_clan_cache = DataCache(self.bot,"clans")
        return self.bot.coc_clan_cache    
    
    ############################################################
    #####
    ##### CLIENT API LOGIN / LOGOUT
    #####
    ############################################################
    async def api_login(self):
        try:
            await self.api_login_keys()
        except:
            clashapi_login = await self.bot.get_shared_api_tokens('clashapi')

            if clashapi_login.get("username") is None:
                raise LoginNotSet(f"Clash API Username is not set.")
            if clashapi_login.get("password") is None:
                raise LoginNotSet(f"Clash API Password is not set.")
            
            throttler = coc.BatchThrottler if self.throttler == 2 else coc.BasicThrottler
            str_throttler = "Batch" if self.throttler == 2 else "Basic"

            self.bot.coc_client = coc.EventsClient(
                key_count=int(clashapi_login.get("keys",1)),
                key_names='Created for Project G, from coc.py',
                load_game_data=coc.LoadGameData(always=True),
                throttle_limit=40,
                throttler=throttler,
                cache_max_size=None
                )
            await self.bot.coc_client.login(clashapi_login.get("username"),clashapi_login.get("password"))
            self.coc_main_log.info(f"Logged into Clash API client with Username/Password. Using {str_throttler} throttler.")
        
        self.num_keys = len(self.coc.http._keys)
        self.rate_limit = self.num_keys * 30        
        self._api_logged_in = True

        self.bot.coc_client.add_events(
            clash_maintenance_start,
            clash_maintenance_complete,
            end_of_trophy_season,
            end_of_clan_games
            )

    async def api_login_keys(self):
        if len(self.client_keys) == 0:
            raise LoginNotSet(f"Clash API Keys are not set.")
        
        throttler = coc.BasicThrottler if self.throttler == 1 else coc.BatchThrottler
        str_throttler = "Basic" if self.throttler == 1 else "Batch"
                
        self.bot.coc_client = coc.EventsClient(
            load_game_data=coc.LoadGameData(always=True),
            throttle_limit=40,
            throttler=throttler,
            cache_max_size=None
            )
        await self.bot.coc_client.login_with_tokens(*self.client_keys)
        self.coc_main_log.info(f"Logged into Clash API client with {len(self.client_keys)} keys. Using {str_throttler} throttler.")

    async def api_logout(self):
        await self.coc.close()

    ############################################################
    #####
    ##### DATABASE CONNECT
    #####
    ############################################################
    async def database_login(self):        
        clash_database = await self.bot.get_shared_api_tokens("clash_db")
        if clash_database.get("dbprimary") is None:
            raise LoginNotSet(f"Clash of Clans Database Name not set.")
        if clash_database.get("username") is None:
            raise LoginNotSet(f"Clash of Clans Database Username not set.")
        if clash_database.get("password") is None:
            raise LoginNotSet(f"Clash of Clans Database Password not set.")
        
        #connect to mongoengine
        connect(
            db=clash_database.get("dbprimary"),
            username=clash_database.get("username"),
            password=clash_database.get("password"),
            uuidRepresentation="pythonLegacy"
            )

    ############################################################
    #####
    ##### CLASH DISCORD LINKS LOGIN / LOGOUT
    #####
    ############################################################
    async def discordlinks_login(self):
        if self.bot.user.id == 828838353977868368:
            self.discordlinks_log.warning(
                f"Clash DiscordLinks initialized in Sandbox mode."
                )
            self.discordlinks_sandbox = True
            return
        
        discordlinks_login = await self.bot.get_shared_api_tokens("clashlinks")

        if discordlinks_login.get("username") is None:
            self.discordlinks_log.error(
                f"Clash DiscordLinks Username is not set. Skipping login."
                )            
        if discordlinks_login.get("password") is None:
            self.discordlinks_log.error(
                f"Clash DiscordLinks Password is not set. Skipping login."
                )

        try:
            self.discordlinks_client = await discordlinks.login(
                discordlinks_login.get("username"),
                discordlinks_login.get("password"))
        except:
            self.discordlinks_log.exception(
                f"Error logging into Clash DiscordLinks. Skipping login."
                )
        else:
            self.discordlinks_log.info(f"Clash DiscordLinks initialized.")
    
    async def logout(self):
        if self.discordlinks_sandbox:
            return
        await self.discordlinks_client.close()
        del self.discordlinks_client
        self.discordlinks_log.info(
            f"Clash DiscordLinks disconnected."
            )

    ############################################################
    #####
    ##### CLASH DISCORD LINKS METHODS
    #####
    ############################################################
    async def add_link(self,tag:str,user:int):
        try:
            if not self.discordlinks_sandbox:
                await self.discordlinks_client.add_link(tag,user)
        except:
            self.discordlinks_log.exception(
                f"Error while adding link for {tag}. User ID: {user}"
                )
        else:
            self.discordlinks_log.info(
                f"Link added for {tag}. User ID: {user}"
                )

    async def delete_link(self,tag:str):
        try:
            if not self.discordlinks_sandbox:
                await self.discordlinks_client.delete_link(tag)
        except:
            self.discordlinks_log.exception(
                f"Error while deleting link for {tag}."
                )
        else:
            self.discordlinks_log.info(
                f"Link deleted for {tag}."
                )

    async def get_linked_user(self,tag:str):
        try:
            get_link = None
            if not self.discordlinks_sandbox:
                get_link = await self.discordlinks_client.get_link(tag)
        except:
            self.discordlinks_log.exception(
                f"Error while retrieving link for {tag}."
                )
        else:
            self.discordlinks_log.info(
                f"Link retrieved for {tag}."
                )
        return get_link

    async def get_linked_players(self,user:int):
        try:
            get_linked_players = []
            if not self.discordlinks_sandbox:
                get_linked_players = await self.discordlinks_client.get_linked_players(user)
        except:
            self.discordlinks_log.exception(
                f"Error while retrieving accounts for {user}."
                )
        else:
            self.discordlinks_log.info(
                f"Accounts retrieved for {user}."
                )
        return get_linked_players

    async def get_many_linked_users(self,player_tags:list[str]):
        try:
            get_linked_users = ()
            if not self.discordlinks_sandbox:
                get_linked_users = await self.discordlinks_client.get_links(*player_tags)
        except:
            self.discordlinks_log.exception(
                f"Error in mass operation for retrieving links. {len(player_tags)} accounts queried."
                )
        else:
            self.discordlinks_log.info(
                f"Retrieved links for multiple accounts: {len(player_tags)} accounts queried."
                )
        return get_linked_users

    async def get_many_linked_players(self,user_ids:list[int]):
        try:
            get_linked_players = ()
            if not self.discordlinks_sandbox:
                get_linked_players = await self.discordlinks_client.get_many_linked_players(*user_ids)
        except:
            self.discordlinks_log.exception(
                f"Error in mass operation for retrieving linked accounts. {len(user_ids)} users queried."
                )
        else:
            self.discordlinks_log.info(
                f"Retrieved accounts for multiple users: {len(user_ids)} users queried."
                )
        return get_linked_players

    ############################################################
    #####
    ##### UPDATE BOT STATUS
    #####
    ############################################################    
    async def update_bot_status(self,cooldown:int,text:str):
        #cooldown in minutes
        diff = pendulum.now().int_timestamp - getattr(self.last_status_update,'int_timestamp',0)
        if self.last_status_update and diff < (cooldown*60):
            return
        
        activity_types = [
            discord.ActivityType.playing,
            discord.ActivityType.listening,
            discord.ActivityType.watching
            ]
        activity_select = random.choice(activity_types)

        try:
            await self.bot.wait_until_ready()
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=activity_select,
                    name=text))
        except Exception as exc:
            self.coc_main_log.exception(f"Bot Status Update Error: {exc}")
        else:
            self.last_status_update = pendulum.now()
            self.coc_main_log.info(f"Bot Status Updated: {text}.")

@coc.ClientEvents.maintenance_start()
async def clash_maintenance_start():
    client = BotClashClient()
    client.api_maintenance = True

    client.coc_main_log.warning(f"Clash Maintenance Started.\n"
        + text2art("Clash Maintenance Started",font="small")
        )
    await client.update_bot_status(
        cooldown=0,
        text="Clash Maintenance!"
        )

@coc.ClientEvents.maintenance_completion()
async def clash_maintenance_complete(time_started):
    client = BotClashClient()
    client.api_maintenance = False

    maint_start = pendulum.instance(time_started)
    maint_end = pendulum.now()

    client.coc_main_log.warning(f"Clash Maintenance Completed. Maintenance took: {maint_end.diff(maint_start).in_minutes()} minutes. Sync loops unlocked.\n"
        + text2art("Clash Maintenance Completed",font="small")
        )
    await client.update_bot_status(
        cooldown=0,
        text="Clash of Clans!"
        )

@coc.ClientEvents.new_season_start()
async def end_of_trophy_season():
    await asyncio.sleep(1800)
    client = BotClashClient()
    cog = client.bot.get_cog("Bank")
    if cog:
        await cog.member_legend_rewards()

@coc.ClientEvents.clan_games_end()
async def end_of_clan_games(self):
    await asyncio.sleep(900)
    client = BotClashClient()
    cog = client.bot.get_cog("Bank")
    if cog:
        await cog.member_clan_games_rewards()