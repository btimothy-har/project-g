import os
import logging
import coc
import asyncio

from coc.ext import discordlinks
from redbot.core.utils import AsyncIter

from .exceptions import *

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
    def values(self):
        return list(self.cache.values())
    def get(self,key):
        return self.cache.get(key,None)    
    def set(self,key,value):
        self.cache[key] = value
    def delete(self,key):
        if key in self.cache:
            del self.cache[key]
    def add_to_queue(self,key):
        if key not in self.queue:
            self.queue.append(key)
    def remove_from_queue(self,key):
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

    def __new__(cls,bot=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._is_initialized = False
        return cls._instance
    
    def __init__(self,bot=None):
        if not bot and not self._is_initialized:
            raise Exception("BotClashClient must be initialized with a bot instance.")
        
        if not self._is_initialized:
            self.bot = bot
            self.discordlinks_sandbox = False
            self.discordlinks_client = None

            self.discordlinks_log = clashlinks_log

            self.player_cache = DataCache(self.bot,"players")
            self.clan_cache = DataCache(self.bot,"clans")

            clashlinks_logpath = f"{self.bot.coc_log_path}/discordlinks"
            if not os.path.exists(clashlinks_logpath):
                os.makedirs(clashlinks_logpath)

            log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
            clashlinks_log_handler = logging.handlers.RotatingFileHandler(
                f"{clashlinks_logpath}/discordlinks.log",
                maxBytes=3*1024*1024,
                backupCount=9
                )
            clashlinks_log_handler.setFormatter(log_formatter)
            self.discordlinks_log.addHandler(clashlinks_log_handler)

    @property
    def cog(self):
        return self.bot.get_cog("ClashOfClansData")
    
    @classmethod
    async def initialize(cls,bot):
        instance = cls(bot)
        if instance._is_initialized:
            return instance
        
        asyncio.create_task(instance.api_login())
        asyncio.create_task(instance.discordlinks_login())

        instance._is_initialized = True
        return instance
    
    async def shutdown(self):
        await self.api_logout()
        await self._events_handler.stop()
        await self._data_cache.logout()

        for handler in self.discordlinks_log.handlers:
            self.discordlinks_log.removeHandler(handler)
            
        self._is_initialized = False
    
    ##################################################
    ### COC API LOGIN / LOGOUT
    ##################################################
    async def api_login(self):

        available_clients = ['clashapi']
        for i in range(1,10):
            available_clients.append(f'clashapi{i}')

        keys = []
        
        async for client in AsyncIter(available_clients):
            clashapi_login = await self.bot.get_shared_api_tokens(client)

            if clashapi_login.get("username") is None:
                if client == 'clashapi':
                    raise LoginNotSet(f"Clash API Username is not set.")
                else:
                    continue
            if clashapi_login.get("password") is None:
                if client == 'clashapi':
                    raise LoginNotSet(f"Clash API Password is not set.")
                else:
                    continue
            
            client = coc.Client(
                key_count=int(clashapi_login.get("keys",1)),
                key_names='Created for Project G, from coc.py',
                load_game_data=coc.LoadGameData(always=True),
                throttle_limit=10,
                timeout=30,
                )
            await client.login(clashapi_login.get("username"),clashapi_login.get("password"))
            keys.extend(client.http._keys)
            await client.close()
        
        if len(keys) == 0:
            raise LoginNotSet(f"No Clash API keys were found.")
        
        client = coc.EventsClient(
            load_game_data=coc.LoadGameData(always=True),
            throttle_limit=10,
            timeout=30
            )
        await client.login_with_tokens(*keys)
        self.bot.coc_client = client
    
    async def api_logout(self):
        await self.bot.coc_client.close()
        del self.bot.coc_client

    ##################################################
    ### CLASH DISCORD LINKS: LOGIN / LOGOUT
    ##################################################
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

    ##################################################
    ### CLASH DISCORD LINKS: CLIENT API METHODS
    ##################################################
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