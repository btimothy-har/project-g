import os
from aiolimiter import AsyncLimiter
import logging
import pendulum
import random
import asyncio
import motor.motor_asyncio

import coc
from coc.ext import discordlinks

from typing import *
from mongoengine import *

from art import text2art
from time import process_time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
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

clashhttp_log = logging.getLogger("coc.http")

############################################################
############################################################
#####
##### DATA QUEUE
#####
############################################################
############################################################
class DataQueue(asyncio.Queue):
    def __init__(self,bot,cache_name):
        self.bot = bot
        self.cache_name = cache_name
        super().__init__()
        self._items_set = set()
    
    def __len__(self):
        return len(self._items_set)
    
    async def put(self,tag):
        n_tag = coc.utils.correct_tag(tag)
        if n_tag not in self._items_set:
            await super().put(n_tag)
            self._items_set.add(n_tag)
    
    async def get(self):
        tag = await super().get()
        self._items_set.discard(tag)
        return tag

    def add(self,key:str):
        def schedule_coroutine():
            asyncio.create_task(self.put(key))
        loop = asyncio.get_running_loop()       
        loop.call_soon_threadsafe(schedule_coroutine)
    
    async def add_many(self,keys:List[str]):
        a_iter = AsyncIter(keys)
        async for key in a_iter:
            await self.put(key)

############################################################
############################################################
#####
##### THROTTLER
#####
############################################################
############################################################
class CustomThrottler(coc.BasicThrottler):
    def __init__(self,sleep_time):
        self.rate_limit = 1 / sleep_time
        self.limiter = AsyncLimiter(1,sleep_time)
        super().__init__(sleep_time)
    
    @property
    def client(self) -> 'BotClashClient':
        return BotClashClient()
    
    async def __aenter__(self):
        # if not self.limiter.has_capacity():
        #     self.client.coc_main_log.debug(f"Throttling request.")
        await self.limiter.acquire()
        await self.client.api_counter.increment_sent()
        return self
            
        # async with self.lock:
        #     self.increment_sent()
        #     last_run = self.last_run
        #     if last_run:
        #         difference = process_time() - last_run
        #         need_to_sleep = (self.sleep_time * 1) - difference
        #         if need_to_sleep > 0:
        #             clashhttp_log.debug("Request throttled. Sleeping for %s", need_to_sleep)
        #             await asyncio.sleep(need_to_sleep)

        #     self.last_run = process_time()
        #     return self
    
    async def __aexit__(self, exc_type, exc, tb):
        await self.client.api_counter.increment_rcvd()
        return self

############################################################
############################################################
#####
##### REQUEST COUNTER
#####
############################################################
############################################################
class RequestCounter():
    def __init__(self):
        self.sent_lock = asyncio.Lock()
        self.sent_time = process_time()
        self.current_sent = 0
        self.sent = deque(maxlen=3600)

        self.rcvd_lock = asyncio.Lock()
        self.rcvd_time = process_time()
        self.current_rcvd = 0
        self.rcvd = deque(maxlen=3600)
    
    @property
    def client(self) -> 'BotClashClient':
        return BotClashClient()

    async def reset_counter(self):
        async with self.sent_lock, self.rcvd_lock:
            self.sent = deque(maxlen=3600)
            self.sent_time = process_time()
            self.rcvd = deque(maxlen=3600)
            self.rcvd_time = process_time()
    
    async def increment_sent(self):
        async with self.sent_lock:
            nt = process_time()
            if nt - self.sent_time > 1:
                self.sent.append(self.current_sent / (nt - self.sent_time))
                self.current_sent = 0
                self.sent_time = nt
            self.current_sent += 1
    
    async def increment_rcvd(self):
        async with self.rcvd_lock:
            nt = process_time()
            if nt - self.rcvd_time > 1:
                self.rcvd.append(self.current_rcvd / (nt - self.rcvd_time))
                self.current_rcvd = 0
                self.rcvd_time = nt
            self.current_rcvd += 1

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
            self.thread_pool = ThreadPoolExecutor(max_workers=2)
            self.read_thread_pool = ThreadPoolExecutor(max_workers=2)
            self.write_thread_pool = ThreadPoolExecutor(max_workers=2)

            # LOGGERS
            self.coc_main_log = coc_main_logger
            self.coc_data_log = coc_data_logger
            self.discordlinks_log = clashlinks_log

            # BOT HELPERS
            self.bot = bot
            self.last_status_update = None

            # SEASONS
            self._current_season = None
            self._tracked_seasons = []

            # API HELPERS
            self.client_keys = []
            self.api_maintenance = False
            self.api_counter = RequestCounter()

            self._connector_task = None
            self._last_login = None

            # DISCORDLINKS
            self.discordlinks_sandbox = False
            self.discordlinks_client = None
            
            # LOGGER SET UP
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
    
    def run_in_thread(self, func, *args):
        def _run_func(func, *args):
            try:
                return func(*args)
            except Exception as exc:
                self.coc_main_log.exception(f"Error in thread: {exc}")
        loop = asyncio.get_running_loop()
        return loop.run_in_executor(self.thread_pool, _run_func, func, *args)
    
    def run_in_read_thread(self, func, *args):
        def _run_func(func, *args):
            try:
                return func(*args)
            except Exception as exc:
                self.coc_main_log.exception(f"Error in read thread: {exc}")
        loop = asyncio.get_running_loop()
        return loop.run_in_executor(self.read_thread_pool, _run_func, func, *args)
    
    def run_in_write_thread(self, func, *args):
        def _run_func(func, *args):
            try:
                return func(*args)
            except Exception as exc:
                self.coc_main_log.exception(f"Error in write thread: {exc}")
        loop = asyncio.get_running_loop()
        return loop.run_in_executor(self.write_thread_pool, _run_func, func, *args)
    
    @classmethod
    async def initialize(cls,
        bot:Red,
        author:str,
        version:str,
        client_keys:Optional[List[str]]=None):

        instance = cls(bot)

        if instance._is_initialized:
            return instance

        instance.author = author
        instance.version = version
        instance.client_keys = client_keys or []

        #instance._connector_task = asyncio.create_task(instance.api_reload())

        await instance.database_login()
        await instance.api_login()
        await instance.discordlinks_login()
        await instance.load_seasons()

        bot.coc_client.add_events(
            clash_maintenance_start,
            clash_maintenance_complete,
            end_of_trophy_season,
            end_of_clan_games
            )
        
        # loop = asyncio.get_running_loop()
        # loop.set_debug(True)

        instance._is_initialized = True
        return instance
    
    async def shutdown(self):
        #self._connector_task.cancel()
        #await self._connector_task
        await self.api_logout()

        for handler in self.discordlinks_log.handlers:
            self.discordlinks_log.removeHandler(handler)
            
        self._is_initialized = False
    
    @property
    def coc(self) -> coc.EventsClient:
        return self.bot.coc_client
    
    @property
    def throttle(self) -> CustomThrottler:
        return self.coc.http._HTTPClient__throttle
    
    @property
    def player_api(self) -> List[float]:
        try:
            a = self.coc.http.stats['/players/{}']
        except KeyError:
            a = []
        return list(a)
    @property
    def player_api_avg(self) -> float:
        return sum(self.player_api) / len(self.player_api) if len(self.player_api) > 0 else 0
    
    @property
    def clan_api(self) -> List[float]:
        try:
            a = self.coc.http.stats['/clans/{}']
        except KeyError:
            a = []
        return list(a)
        
    @property
    def clan_api_avg(self) -> float:
        return sum(self.clan_api)/len(self.clan_api) if len(self.clan_api) > 0 else 0
    
    @property
    def api_current_throughput(self) -> (float, float):
        nt = process_time()

        diff = nt - self.api_counter.sent_time
        sent_avg = self.api_counter.current_sent / diff if self.api_counter.current_sent > 0 else 0
        
        diff = nt - self.api_counter.rcvd_time
        rcvd_avg = self.api_counter.current_rcvd / diff if self.api_counter.current_rcvd > 0 else 0
        return sent_avg, rcvd_avg
    
    @property
    def rcvd_stats(self) -> (float, float, float):
        if len(self.api_counter.rcvd) == 0:
            return 0,0,0
        avg = sum(self.api_counter.rcvd)/len(self.api_counter.rcvd)
        last = list(self.api_counter.rcvd)[-1]
        maxr = max(self.api_counter.rcvd)
        return avg, last, maxr
    
    @property
    def sent_stats(self) -> (float, float, float):
        if len(self.api_counter.sent) == 0:
            return 0,0,0
        avg = sum(self.api_counter.sent)/len(self.api_counter.sent)
        last = list(self.api_counter.sent)[-1]
        maxr = max(self.api_counter.sent)
        return avg, last, maxr
    
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
    def player_queue(self) -> DataQueue:
        if not hasattr(self.bot,"coc_player_queue"):
            self.bot.coc_player_queue = DataQueue(self.bot,"players")
        return self.bot.coc_player_queue

    @property
    def clan_queue(self) -> DataQueue:
        if not hasattr(self.bot,"coc_clan_queue"):
            self.bot.coc_clan_queue = DataQueue(self.bot,"clans")
        return self.bot.coc_clan_queue    
    
    ############################################################
    #####
    ##### CLIENT API LOGIN / LOGOUT
    #####
    ############################################################
    async def api_reload(self):
        async def reconnect():
            await self.api_logout()
            await self.api_login()
        
        try:
            while True:
                try:
                    await asyncio.sleep(1)
                    connect = pendulum.now() - self._last_login
                    if self.player_api_avg > 3000:
                        await reconnect()
                        self.coc_main_log.warning(
                            f"Player API exceeds average threshold. Refreshing Clash API Client Connection. Uptime: {connect.total_seconds()}."
                            )
                        continue
                        
                    # if max(self.player_api[-100:]) > 20000:
                    #     await reconnect()
                    #     self.coc_main_log.warning(
                    #         f"Player API exceeds maximum threshold. Refreshing Clash API Client Connection. Uptime: {connect.total_seconds()}."
                    #         )
                    #     continue

                    if self.clan_api_avg > 3000:
                        await reconnect()
                        self.coc_main_log.warning(
                            f"Clan API exceeds average threshold. Refreshing Clash API Client Connection. Uptime: {connect.total_seconds()}."
                            )
                        continue
                        
                    # if max(self.clan_api[-100:]) > 20000:
                    #     await reconnect()
                    #     self.coc_main_log.warning(
                    #         f"Clan API exceeds maximum threshold. Refreshing Clash API Client Connection. Uptime: {connect.total_seconds()}."
                    #         )
                    #     continue
                        
                    # if connect.total_seconds() > 600:
                    #     await reconnect()
                    #     self.coc_main_log.warning(
                    #         f"Clash API Client Connection Refreshed. Uptime: {connect.total_seconds()}."
                    #         )
                    #     continue
                
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    continue
                    
        except asyncio.CancelledError:
            pass

    async def api_login(self,rate_limit:int=30):
        try:
            await self.api_login_keys(rate_limit)
        except:
            await self.api_login_username(rate_limit)
        
        self.num_keys = len(self.coc.http._keys)
        self.rate_limit = self.num_keys * rate_limit
        self._api_logged_in = True

    async def api_login_keys(self,rate_limit):
        if len(self.client_keys) == 0:
            raise LoginNotSet(f"Clash API Keys are not set.")
                
        if not getattr(self.bot,"coc_client",None):
            self.bot.coc_client = coc.EventsClient(
                load_game_data=coc.LoadGameData(always=True),
                throttler=CustomThrottler,
                throttle_limit=rate_limit,
                cache_max_size=1000000
                )
            self.coc_main_log.info(f"New Client Created: {self.bot.coc_client} with {len(self.client_keys)} keys.")

        #keys = random.sample(self.client_keys,min(100,len(self.client_keys)))
        keys = self.client_keys
            
        await self.bot.coc_client.login_with_tokens(*keys)
        self._last_login = pendulum.now()
        self.coc_main_log.debug(
            f"Logged into Clash API client with {len(keys)} keys."
            + f"\n\tClient: {self.bot.coc_client}"
            )
    
    async def api_login_username(self,rate_limit):
        clashapi_login = await self.bot.get_shared_api_tokens('clashapi')

        if clashapi_login.get("username") is None:
            raise LoginNotSet(f"Clash API Username is not set.")
        if clashapi_login.get("password") is None:
            raise LoginNotSet(f"Clash API Password is not set.")

        if not getattr(self.bot,"coc_client",None):
            self.bot.coc_client = coc.EventsClient(
                key_count=int(clashapi_login.get("keys",1)),
                key_names='project-g',
                load_game_data=coc.LoadGameData(always=True),
                throttler=CustomThrottler,
                throttle_limit=rate_limit,
                cache_max_size=1000000
                )
            self.coc_main_log.info(f"New Client Created: {self.bot.coc_client} with Username/Password.")

        await self.bot.coc_client.login(clashapi_login.get("username"),clashapi_login.get("password"))
        self._last_login = pendulum.now()
        self.coc_main_log.debug(
            f"Logged into Clash API client with Username/Password."
            + f"\n\tClient: {self.bot.coc_client}"
            )

    async def api_logout(self):
        await self.coc.close()
        self.coc_main_log.debug(f"Logged out of Clash API client.")

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

        client = motor.motor_asyncio.AsyncIOMotorClient(
            f'mongodb://{clash_database.get("username")}:{clash_database.get("password")}@localhost:27017/admin',
            uuidRepresentation="pythonLegacy",
            maxPoolSize=1000,
            )
        self.coc_db = client[clash_database.get("dbprimary")]

    ############################################################
    #####
    ##### CLASH DISCORD LINKS LOGIN / LOGOUT
    #####
    ############################################################
    async def discordlinks_login(self):
        if self.bot.user.id in [828838353977868368,1176156235167449139]:
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
    await client.api_counter.reset_counter()
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