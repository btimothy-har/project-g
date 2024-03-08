# import asyncio
# import coc
# import discord
# import pendulum
# import logging

# from typing import *

# from art import text2art
# from collections import deque
# from discord.ext import tasks

# from redbot.core import commands
# from redbot.core.bot import Red
# from redbot.core.utils import AsyncIter,bounded_gather

# from .api_client import BotClashClient, aClashSeason

# from .coc_objects.players.player import BasicPlayer, aPlayer
# from .coc_objects.players.townhall import aTownHall
# from .coc_objects.clans.clan import BasicClan, aClan
# from .coc_objects.events.clan_war import aClanWar
# from .coc_objects.events.clan_war_leagues import WarLeagueGroup
# from .coc_objects.events.raid_weekend import aRaidWeekend

# from .exceptions import InvalidTag, ClashAPIError, InvalidAbbreviation

# from .utils.constants.coc_constants import ClanRanks, MultiplayerLeagues
# from .utils.components import clash_embed, DefaultView, DiscordButton, EmojisUI

# bot_client = BotClashClient()

# ############################################################
# ############################################################
# #####
# ##### CLIENT COG
# #####
# ############################################################
# ############################################################
# class ClashOfClansClient(commands.Cog):
#     """
#     API Client Manager for Clash of Clans.

#     This cog provides a wrapper for key COC API calls, facilitates the cache/API interaction, and tracks API response time(s).
#     """

#     __author__ = bot_client.author
#     __version__ = bot_client.version

#     def __init__(self,bot:Red):
#         self.bot = bot
#         self.season_lock = asyncio.Lock()

#     def format_help_for_context(self, ctx: commands.Context) -> str:
#         context = super().format_help_for_context(ctx)
#         return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"
    
#     @property
#     def client(self) -> BotClashClient:
#         return bot_client
    
#     @property
#     def api_maintenance(self) -> bool:
#         return bot_client.api_maintenance
    
#     @property
#     def player_api(self) -> deque:
#         return bot_client.player_api
#     @property
#     def player_api_avg(self) -> float:
#         return bot_client.player_api_avg
    
#     @property
#     def clan_api(self) -> deque:
#         return bot_client.clan_api
#     @property
#     def clan_api_avg(self) -> float:
#         return bot_client.clan_api_avg

#     ##################################################
#     ### COG LOAD
#     ##################################################
#     async def cog_load(self):
#         bot_client.coc.player_cls = aPlayer
#         bot_client.coc.clan_cls = aClan

#         self.bot_status_update_loop.start() 
#         self.clash_season_check.start()
        
#     async def cog_unload(self):
#         self.bot_status_update_loop.cancel()
#         self.clash_season_check.cancel()

#         BasicPlayer.clear_cache()
#         BasicClan.clear_cache()
        
#         aClanWar._cache = {}
#         aRaidWeekend._cache = {}        
#         aClashSeason._cache = {}
        
#     ############################################################
#     #####
#     ##### LISTENERS
#     #####
#     ############################################################    
#     @commands.Cog.listener("on_shard_connect")
#     async def status_on_connect(self,shard_id):
#         await self.bot.change_presence(
#             activity=discord.Activity(
#                 type=discord.ActivityType.listening,
#                 name=f"$help!")
#                 )
    
#     @tasks.loop(minutes=10.0)
#     async def bot_status_update_loop(self):
#         try:
#             if self.client.last_status_update != None and (pendulum.now().int_timestamp - self.client.last_status_update.int_timestamp) < (6* 3600):
#                 return            
#             await self.bot.change_presence(
#                 activity=discord.Activity(
#                     type=discord.ActivityType.listening,
#                     name=f"$help!")
#                     )              
#         except Exception:
#             #await self.bot.send_to_owners(f"An error occured during the Bot Status Update Loop. Check logs for details.")
#             self.client.coc_main_log.exception(
#                 f"Error in Bot Status Loop"
#                 )
    
#     @tasks.loop(seconds=10.0)
#     async def clash_season_check(self):
#         if self.season_lock.locked():
#             return
        
#         try:
#             async with self.season_lock:
#                 season = await aClashSeason.get_current_season()

#                 if season.id == bot_client.current_season.id:
#                     return None
                
#                 await season.set_as_current()
#                 await bot_client.load_seasons()
                
#                 bot_client.coc_main_log.info(f"New Season Started: {season.id} {season.description}\n"
#                     + text2art(f"{season.id}",font="small")
#                     )
#                 bot_client.coc_data_log.info(f"New Season Started: {season.id} {season.description}\n"
#                     + text2art(f"{season.id}",font="small")
#                     )
                
#                 await bot_client.bot.change_presence(
#                     activity=discord.Activity(
#                         type=discord.ActivityType.playing,
#                         name=f"start of the {bot_client.current_season.short_description} Season! Clash on!")
#                         )

#                 bank_cog = bot_client.bot.get_cog('Bank')
#                 if bank_cog:
#                     await bank_cog.apply_bank_taxes()
#                     await bank_cog.month_end_sweep()
        
#         except Exception as exc:
#             await self.bot.send_to_owners(f"An error occured during Season Refresh. Check logs for details."
#                 + f"```{exc}```")
#             bot_client.coc_main_log.exception(
#                 f"Error in Season Refresh"
#                 )        
#         finally:
#             bot_client.last_season_check = pendulum.now()

#     ############################################################
#     #####
#     ##### COC: CLAN WARS
#     #####
#     ############################################################    
#     async def get_clan_war(self,clan:aClan) -> aClanWar:
#         count = 0
#         api_war = None
        
#         while True:
#             try:
#                 count += 1
#                 api_war = await self.client.coc.get_clan_war(clan.tag)
#                 break
#             except coc.PrivateWarLog:
#                 return None
#             except coc.NotFound as exc:
#                 raise InvalidTag(clan.tag) from exc
#             except (coc.Maintenance,coc.GatewayError) as exc:
#                 raise ClashAPIError(exc) from exc
#             except:
#                 if count > 3:
#                     raise ClashAPIError()
#                 await asyncio.sleep(1)
        
#         if api_war:
#             if getattr(api_war,'state','notInWar') != 'notInWar':
#                 clan_war = await aClanWar.create_from_api(api_war)
#                 return clan_war
#         return None
            
    
                
#     ############################################################
#     #####
#     ##### COC: RAID WEEKEND
#     #####
#     ############################################################ 
#     async def get_raid_weekend(self,clan:aClan) -> aRaidWeekend:
#         count = 0
#         raidloggen = None
#         api_raid = None
        
#         while True:
#             try:
#                 count += 1
#                 raidloggen = await self.client.coc.get_raid_log(clan_tag=clan.tag,page=False,limit=1)
#                 break
#             except coc.PrivateWarLog:
#                 return None
#             except coc.NotFound as exc:
#                 raise InvalidTag(self.tag) from exc
#             except (coc.Maintenance,coc.GatewayError) as exc:
#                 raise ClashAPIError(exc) from exc
#             except:
#                 if count > 3:
#                     raise ClashAPIError()
#                 await asyncio.sleep(1)
                
#         if raidloggen and len(raidloggen) > 0:
#             api_raid = raidloggen[0]
#             if api_raid:
#                 raid_weekend = await aRaidWeekend.create_from_api(clan,api_raid)
#                 return raid_weekend
#         return None
            
#     ############################################################
#     #####
#     ##### STATUS REPORT
#     #####
#     ############################################################ 
#     async def status_embed(self):
#         embed = await clash_embed(self.bot,
#             title="**Clash of Clans API**",
#             message=f"### {pendulum.now().format('dddd, DD MMM YYYY HH:mm:ssZZ')}",
#             timestamp=pendulum.now()
#             )
        
#         waiters = len(bot_client.coc.http._HTTPClient__lock._waiters) if bot_client.coc.http._HTTPClient__lock._waiters else 0
#         embed.add_field(
#             name="**API Client**",
#             value="```ini"
#                 + f"\n{'[Maintenance]':<15} {self.api_maintenance}"
#                 + f"\n{'[API Keys]':<15} " + f"{bot_client.num_keys:,}"
#                 + f"\n{'[API Requests]':<15} " + f"{bot_client.coc.http.key_count - bot_client.coc.http._HTTPClient__lock._value:,} / {bot_client.coc.http.key_count:,}" + f" (Waiting: {waiters:,})"
#                 + "```",
#             inline=False
#             )
#         embed.add_field(
#             name="**Player API**",
#             value="```ini"
#                 + f"\n{'[Last]':<10} {(self.player_api[-1] if len(self.player_api) > 0 else 0)/1000:.3f}s"
#                 + f"\n{'[Mean]':<10} {self.player_api_avg/1000:.3f}s"
#                 + f"\n{'[Min/Max]':<10} {(min(self.player_api) if len(self.player_api) > 0 else 0)/1000:.3f}s ~ {(max(self.player_api) if len(self.player_api) > 0 else 0)/1000:.3f}s"
#                 + "```",
#             inline=False
#             )
#         embed.add_field(
#             name="**Clan API**",
#             value="```ini"
#                 + f"\n{'[Last]':<10} {(self.clan_api[-1] if len(self.clan_api) > 0 else 0)/1000:.3f}s"
#                 + f"\n{'[Mean]':<10} {self.clan_api_avg/1000:.3f}s"
#                 + f"\n{'[Min/Max]':<10} {(min(self.clan_api) if len(self.clan_api) > 0 else 0)/1000:.3f}s ~ {(max(self.clan_api) if len(self.clan_api) > 0 else 0)/1000:.3f}s"
#                 + "```",
#             inline=False
#             )
        
#         sent, rcvd = bot_client.api_current_throughput
#         avg_rcvd, last_rcvd, max_rcvd = bot_client.rcvd_stats
#         avg_sent, last_sent, max_sent = bot_client.sent_stats
        
#         embed.add_field(
#             name="**Throughput (sent / rcvd, per second)**",
#             value="```ini"
#                 + f"\n{'[Now]':<6} {sent:.2f} / {rcvd:.2f}"
#                 + f"\n{'[Last]':<6} {last_sent:.2f} / {last_rcvd:.2f}"
#                 + f"\n{'[Avg]':<6} {avg_sent:.2f} / {avg_rcvd:.2f}"
#                 + f"\n{'[Max]':<6} {max_sent:.2f} / {max_rcvd:.2f}"
#                 + "```",
#             inline=False
#             )
#         return embed
    
#     @commands.group(name="cocapi")
#     @commands.is_owner()
#     async def command_group_coc_api_client(self,ctx):
#         """Manage the Clash of Clans API Client."""
#         if not ctx.invoked_subcommand:
#             pass
    
#     @command_group_coc_api_client.command(name="status")
#     @commands.is_owner()
#     async def _status_report(self,ctx:commands.Context):
#         """Status of the Clash of Clans API Client."""
#         embed = await self.status_embed()
#         view = RefreshStatus(ctx)
#         await ctx.reply(embed=embed,view=view)
    
#     @command_group_coc_api_client.command(name="httplog")
#     @commands.is_owner()
#     async def command_httplog(self,ctx:commands.Context):
#         """
#         Turns on HTTP logging for the Clash of Clans API.
#         """
#         current = logging.getLogger("coc.http").level
#         if current == logging.DEBUG:
#             logging.getLogger("coc.http").setLevel(logging.INFO)
#             await ctx.tick()
#         else:
#             logging.getLogger("coc.http").setLevel(logging.DEBUG)
#             await ctx.tick()

# class RefreshStatus(DefaultView):
#     def __init__(self,context:Union[discord.Interaction,commands.Context]):

#         button = DiscordButton(
#             function=self._refresh_embed,
#             emoji=EmojisUI.REFRESH,
#             label="Refresh",
#             )

#         super().__init__(context,timeout=9999999)
#         self.is_active = True
#         self.add_item(button)
    
#     @property
#     def client_cog(self) -> ClashOfClansClient:
#         return bot_client.bot.get_cog("ClashOfClansClient")
    
#     async def _refresh_embed(self,interaction:discord.Interaction,button:DiscordButton):
#         await interaction.response.defer()
#         embed = await self.client_cog.status_embed()
#         await interaction.followup.edit_message(interaction.message.id,embed=embed)