import asyncio
import os
import discord
import pendulum
import logging
import coc
import random

from typing import *

from discord.ext import tasks

from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.utils import AsyncIter

from coc_main.cog_coc_main import ClashOfClansMain as coc_main
from coc_main.client.global_client import GlobalClient

from coc_main.coc_objects.season.season import aClashSeason
from coc_main.coc_objects.players.player import BasicPlayer, aPlayer, aPlayerSeason
from coc_main.coc_objects.players.player_activity import aPlayerActivity
from coc_main.coc_objects.clans.clan import aClan
from coc_main.coc_objects.events.clan_war_leagues import WarLeagueGroup
from coc_main.coc_objects.events.clan_war import aClanWar
from coc_main.coc_objects.events.clan_war_v2 import bClanWar, bWarLeagueGroup

from coc_main.utils.components import DefaultView, DiscordButton, clash_embed
from coc_main.utils.constants.ui_emojis import EmojisUI

from .tasks.player_tasks import PlayerTasks
from .tasks.clan_tasks import ClanTasks
from .tasks.war_tasks import DefaultWarTasks
from .tasks.raid_tasks import ClanRaidLoop

default_global = {
    "global_scope": 0,
    "cycle_id": -1
    }

# NEBULA CYCLE ID = -10

LOG = logging.getLogger("coc.data")

############################################################
############################################################
#####
##### TASKS COG
#####
############################################################
############################################################
class ClashOfClansData(commands.Cog,GlobalClient):
    """
    Clash of Clans Data Client. Handles background loops/sync.
    """

    __author__ = coc_main.__author__
    __version__ = coc_main.__version__

    def __init__(self):

        #Config
        self.config:Config = Config.get_conf(self,identifier=644530507505336330,force_registration=True)        
        self.config.register_global(**default_global)        
        
        self.is_global = False
        self.cycle_id = -1

        self._leaderboard_discovery_lock = asyncio.Lock()
        self.player_cache = None
        self.clan_cache = None

        #PLAYER LOOP
        self._player_loop_lock = asyncio.Lock()
        self._player_loop_num = 0
        self._player_loop_tracker = {}        
        self.player_loop_runtime = []
        self.player_loop_status = False
        self.player_loop_last = None

        #CLAN LOOP
        self._clan_loop_lock = asyncio.Lock()
        self._clan_loop_num = 0
        self._clan_loop_tracker = {}        
        self.clan_loop_runtime = []
        self.clan_loop_status = False
        self.clan_loop_last = None

        #CLAN LOOP
        self._war_loop_num = 0
        self._war_loop_tracker = {}        
        self.war_loop_runtime = []
        self.war_loop_status = False
        self.war_loop_last = None

        # DATA QUEUE        
        self._raid_loop = ClanRaidLoop()

        self.player_activity_loop = None

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"
    
    @property
    def bot(self) -> Red:
        return GlobalClient.bot

    ##################################################
    ### COG LOAD
    ##################################################
    async def cog_load(self):
        log_path = f"{cog_data_path(self)}/logs"
        if not os.path.exists(log_path):
            os.makedirs(log_path)

        log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        data_log_handler = logging.handlers.RotatingFileHandler(
            f"{log_path}/coc_data.log",
            maxBytes=3*1024*1024,
            backupCount=9
            )
        data_log_handler.setFormatter(log_formatter)
        LOG.addHandler(data_log_handler)

        self.is_global = await self.config.global_scope() == 1
        self.cycle_id = await self.config.cycle_id()
        asyncio.create_task(self.start_task_cog())
    
    async def start_task_cog(self):
        while True:
            if getattr(self,'_ready',False):
                break
            await asyncio.sleep(1)

        await self.bot.wait_until_ready()

        if self.cycle_id == -10 or self.cycle_id >= 0:
            chk_state = await self.database.db_data_controller.find_one({"_id":self.cycle_id})
            if chk_state and chk_state.get('active',False) and chk_state.get('process_id',0) != self.bot.user.id:
                self.cycle_id = -1
                LOG.error(f"Cycle ID {self.cycle_id} is currently being used by <@{chk_state.get('process_id',0)}>.")
            
            else:            
                await self.database.db_data_controller.update_one(
                    {"_id": self.cycle_id},
                    {"$set": {
                        "active": True,
                        "process_id": self.bot.user.id
                        }},
                    upsert=True
                    )
                LOG.info(f"Cycle ID {self.cycle_id} assigned to {self.bot.user.id}.")
        
        self.coc_client.player_cls = aPlayer
        self.coc_client.clan_cls = aClan
        self.coc_client.war_cls = bClanWar

        self.coc_client._use_discovery = True
        
        self.player_cache = asyncio.create_task(self._player_cache_task())
        self.clan_cache = asyncio.create_task(self._clan_cache_task())

        self.coc_client.add_events(
            self.player_loop_start,
            self.player_loop_end,
            self.insert_player_activities,
            self.clan_loop_start,
            self.clan_loop_end,
            self.war_loop_start,
            self.war_loop_end
            )
        
        await self.refresh_event_tasks()
        try:
            self.update_player_loop.start()
        except:
            pass
        try:
            self.update_clan_loop.start()
        except:
            pass
        try:
            self.leaderboard_discovery.start()
        except:
            pass
        try:
            self.refresh_player_snapshot.start()
        except:
            pass

    ##################################################
    ### COG UNLOAD
    ##################################################
    async def cog_unload(self):
        self.coc_client._use_discovery = False
        self.player_cache.cancel()
        self.clan_cache.cancel()
        self.leaderboard_discovery.cancel()
        self.refresh_player_snapshot.cancel()
        
        await self.unload_event_tasks()
        try:
            self.update_player_loop.stop()
        except:
            pass
        try:
            self.update_clan_loop.stop()
        except:
            pass

        if self.cycle_id == -10 or self.cycle_id >= 0:
            await self.database.db_data_controller.update_one(
                {"_id": self.cycle_id},
                {"$set": {
                    "active": False,
                    "process_id": self.bot.user.id
                    }
                },
                upsert=True
                )
            LOG.info(f"Cycle ID {self.cycle_id} released by {self.bot.user.id}.")

    ##################################################
    ### REFRESH TASKS
    ##################################################
    async def refresh_event_tasks(self):
        if self.cycle_id == -10:
            self.coc_client.add_events(
                DefaultWarTasks.check_war_role,
                DefaultWarTasks.war_start_status_update,
                DefaultWarTasks.war_end_status_update,
                DefaultWarTasks.ongoing_war_status_update
                )
            asyncio.create_task(self._raid_loop.start())
        
        elif self.cycle_id >= 0:
            self.coc_client.add_events(
                PlayerTasks.on_player_update_name,
                PlayerTasks.on_player_update_war_opted_in,
                PlayerTasks.on_player_update_labels,
                PlayerTasks.on_player_upgrade_townhall,
                PlayerTasks.on_player_upgrade_hero,
                PlayerTasks.on_player_upgrade_troops,
                PlayerTasks.on_player_upgrade_spells,
                PlayerTasks.on_player_update_clan,
                PlayerTasks.on_player_update_trophies,
                PlayerTasks.on_player_update_attack_wins,
                PlayerTasks.on_player_update_defense_wins,
                PlayerTasks.on_player_update_war_stars,
                PlayerTasks.on_player_update_donations,
                PlayerTasks.on_player_update_received,
                PlayerTasks.on_player_update_capital_contributions,
                PlayerTasks.on_player_update_loot_capital_gold,
                PlayerTasks.on_player_update_loot_gold,
                PlayerTasks.on_player_update_loot_elixir,
                PlayerTasks.on_player_update_loot_darkelixir,
                PlayerTasks.on_player_update_clan_games,
                ClanTasks.on_clan_member_join_capture,
                ClanTasks.on_clan_member_leave_capture,
                DefaultWarTasks.save_war_on_new_attack,
                DefaultWarTasks.save_war_on_change,
                DefaultWarTasks.sync_clan_war_leagues,
                DefaultWarTasks.sync_war_participants
                )

    async def unload_event_tasks(self):
        if self.cycle_id == -10:
            self.coc_client.remove_events(
                DefaultWarTasks.check_war_role,
                DefaultWarTasks.war_start_status_update,
                DefaultWarTasks.war_end_status_update,
                DefaultWarTasks.ongoing_war_status_update
                )
            await self._raid_loop.stop()
        
        elif self.cycle_id >= 0:
            self.coc_client.remove_events(
                PlayerTasks.on_player_check_snapshot,
                PlayerTasks.on_player_update_name,
                PlayerTasks.on_player_update_war_opted_in,
                PlayerTasks.on_player_update_labels,
                PlayerTasks.on_player_upgrade_townhall,
                PlayerTasks.on_player_upgrade_hero,
                PlayerTasks.on_player_upgrade_troops,
                PlayerTasks.on_player_upgrade_spells,
                PlayerTasks.on_player_update_clan,
                PlayerTasks.on_player_update_trophies,
                PlayerTasks.on_player_update_attack_wins,
                PlayerTasks.on_player_update_defense_wins,
                PlayerTasks.on_player_update_war_stars,
                PlayerTasks.on_player_update_donations,
                PlayerTasks.on_player_update_received,
                PlayerTasks.on_player_update_capital_contributions,
                PlayerTasks.on_player_update_loot_capital_gold,
                PlayerTasks.on_player_update_loot_gold,
                PlayerTasks.on_player_update_loot_elixir,
                PlayerTasks.on_player_update_loot_darkelixir,
                PlayerTasks.on_player_update_clan_games,
                ClanTasks.on_clan_activity,
                ClanTasks.on_clan_member_join_capture,
                ClanTasks.on_clan_member_leave_capture,
                DefaultWarTasks.save_war_on_new_attack,
                DefaultWarTasks.save_war_on_change,
                DefaultWarTasks.sync_clan_war_leagues,
                DefaultWarTasks.sync_war_participants
                )

    ############################################################
    #####
    ##### DATA LOOP UPDATES
    #####
    ############################################################
    @tasks.loop(hours=4)
    async def refresh_player_snapshot(self):
        return

    @tasks.loop(minutes=10)    
    async def update_player_loop(self):
        async with self._player_loop_lock:
            if self.coc_client.maintenance:
                return
            
            query = {
                "_cycle_id": 1,
                "discord_user": {"$exists":True,"$gt":0},
                "is_member": True
                }
            
            db_query = self.database.db__player.find(query,{'_id':1})
            async for p in db_query:
                await self.database.db__player.update_one(
                    {"_id": p['_id']},
                    {"$unset": {"_cycle_id": 1}}
                    )
            
            query = {"_cycle_id": 1}
            db_query = self.database.db__player.find(query,{'_id':1})
            async for p in db_query:
                await self.coc_client._player_cache_queue.put(p['_id'])
                
            if self.cycle_id in [0]:
                current = list(self.coc_client._player_updates)
                query = {
                    "$and": [
                        {"_id": {"$nin": current}},
                        {"_cycle_id": self.cycle_id}
                        ]
                    }

                db_query = self.database.db__player.find(query,{'_id':1})
                self.coc_client.add_player_updates(*[p['_id'] async for p in db_query])
    
    @tasks.loop(minutes=10)
    async def update_clan_loop(self):
        async with self._clan_loop_lock:
            if self.coc_client.maintenance:
                return            
            
            if self.cycle_id == 1:
                current = list(self.coc_client._clan_updates)
                   
                clans = []
                try:
                    registered_clans = await self.coc_client.get_registered_clans()
                except:
                    pass
                else:
                    clans.extend([c.tag for c in registered_clans])
                                
                try:
                    war_league_clans = await self.coc_client.get_war_league_clans()
                except:
                    pass
                else:
                    clans.extend([c.tag for c in war_league_clans])

                current_clan = list(self.coc_client._clan_updates)
                current_war = list(self.coc_client._war_updates)

                query = {"_id": {"$in": current,"$in":clans}}
                db_query = await self.database.db__clan.find(query,{'_id':1}).to_list(length=None)
                for p in db_query:
                    if p['_id'] in current_clan:
                        self.coc_client.remove_clan_updates(p['_id'])
                    if p['_id'] in current_war:
                        self.coc_client.remove_war_updates(p['_id'])

                    await self.database.db__clan.update_one(
                        {"_id": p['_id']},
                        {"$unset": {"_cycle_id": 1}}
                        )
            
            if self.cycle_id in [0,1]:
                current_clan = list(self.coc_client._clan_updates)
                query = {
                    "$and": [
                        {"_id": {"$nin": current_clan}},
                        {"_cycle_id": self.cycle_id}
                        ]
                    }
                db_query = await self.database.db__clan.find(query,{'_id':1}).to_list(length=None)
                self.coc_client.add_clan_updates(*[p['_id'] for p in db_query])

                current_war = list(self.coc_client._war_updates)
                query = {
                    "$and": [
                        {"_id": {"$nin": current_war}},
                        {"_cycle_id": self.cycle_id}
                        ]
                    }
                db_query = await self.database.db__clan.find(query,{'_id':1}).to_list(length=None)
                self.coc_client.add_war_updates(*[p['_id'] for p in db_query])
    
    ############################################################
    #####
    ##### LEADERBOARD DISCOVERY LOOP
    #####
    ############################################################
    @tasks.loop(minutes=30)    
    async def leaderboard_discovery(self):    
        if self._leaderboard_discovery_lock.locked():
            return
        
        async with self._leaderboard_discovery_lock:
            if self.coc_client.maintenance:
                return
            
            if self.cycle_id == 0:
                add_tasks = []            
                locations = await self.coc_client.search_locations()
                l_iter = AsyncIter(locations)
            
                async for location in l_iter:
                    try:
                        location_players = await self.coc_client.get_location_players(location.id)
                    except coc.ClashOfClansException:
                        pass
                    except:
                        LOG.exception(f"Error in Player Discovery for Location {location.id}.")
                    else:
                        add_tasks.extend([self.coc_client._player_cache_queue.put(p.tag) for p in location_players])

                    try:
                        builderbase_players = await self.coc_client.get_location_players_builder_base(location.id)
                    except coc.ClashOfClansException:
                        pass
                    except:
                        LOG.exception(f"Error in Player Discovery for Location {location.id}.")
                    else:
                        add_tasks.extend([self.coc_client._player_cache_queue.put(p.tag) for p in builderbase_players])
            
                    try:
                        location_clans = await self.coc_client.get_location_clans(location.id)
                    except coc.ClashOfClansException:
                        pass
                    except:
                        LOG.exception(f"Error in Clan Discovery for Location {location.id}.")
                    else:
                        add_tasks.extend([self.coc_client._clan_cache_queue.put(c.tag) for c in location_clans])
                    
                    try:
                        builderbase_clans = await self.coc_client.get_location_clans_builder_base(location.id)
                    except coc.ClashOfClansException:
                        pass
                    except:
                        LOG.exception(f"Error in Clan Discovery for Location {location.id}.")
                    else:
                        add_tasks.extend([self.coc_client._clan_cache_queue.put(c.tag) for c in builderbase_clans])
                    
                    try:
                        capital_clans = await self.coc_client.get_location_clans_capital(location.id)
                    except coc.ClashOfClansException:
                        pass
                    except:
                        LOG.exception(f"Error in Clan Discovery for Location {location.id}.")
                    else:
                        add_tasks.extend([self.coc_client._clan_cache_queue.put(c.tag) for c in capital_clans])
            
                if len(add_tasks) > 0:
                    await asyncio.gather(*add_tasks)

    ############################################################
    #####
    ##### CACHE REFRESH
    #####
    ############################################################    
    async def _player_cache_task(self):
        while True:
            try:
                if self.coc_client.maintenance:
                    await asyncio.sleep(600)
                    return

                tag = await self.coc_client._player_cache_queue.get()

                try:
                    player = await self.coc_client.get_player(tag)

                except coc.NotFound:
                    self.coc_client._player_cache_queue.task_done()

                    basic_player = await BasicPlayer(tag)
                    await basic_player._attributes.load_data()

                    if basic_player.discord_user:
                        await basic_player.unlink_discord()

                    if basic_player.is_member:
                        await basic_player.remove_member()
                
                except (coc.Maintenance,coc.GatewayError):
                    await self.coc_client._player_cache_queue.put(tag)
                
                else:            
                    self.coc_client._player_cache_queue.task_done()
                    await aPlayer._sync_cache(player)

                    seasons = aClashSeason.all_seasons()
                    snapshot_tasks = [player._update_snapshots(season) for season in seasons]
                    await asyncio.gather(*snapshot_tasks)

                    if player.clan:
                        await self.coc_client._clan_cache_queue.put(player.clan.tag)
            
            except asyncio.CancelledError:
                return

            except Exception:
                LOG.exception("Error in Player Discovery.")
        
    async def _clan_cache_task(self):
        while True:
            try:
                if self.coc_client.maintenance:
                    await asyncio.sleep(600)
                    return

                tag = await self.coc_client._clan_cache_queue.get()

                try:
                    clan = await self.coc_client.get_clan(tag)

                except coc.NotFound:
                    self.coc_client._clan_cache_queue.task_done()
                    
                except (coc.Maintenance,coc.GatewayError):
                    await self.coc_client._clan_cache_queue.put(tag)
                
                else:            
                    self.coc_client._clan_cache_queue.task_done()
                    await aClan._sync_cache(clan)

                save_members = [self.coc_client._player_cache_queue.put(m.tag) for m in clan.members]
                await asyncio.gather(*save_members)
                
            except asyncio.CancelledError:
                return
            
            except Exception:
                LOG.exception("Error in Clan Discovery.")
    
    ############################################################
    #####
    ##### COMMANDS
    #####
    ############################################################
    async def status_embed(self):
        embed = await clash_embed(self.bot,
            title="**Clash of Clans Data Status**",
            message=f"### {pendulum.now().format('dddd, DD MMM YYYY HH:mm:ssZZ')}"
                + f"\n\n**Current Season: {aClashSeason.current().description}**",
            timestamp=pendulum.now()
            )

        embed.add_field(
            name="**Data Client**",
            value=f"Cycle ID: {self.cycle_id}",
            inline=False
            )
        
        embed.add_field(
            name="**Player Loops**",
            value=f"Last: " + (f"<t:{getattr(self.player_loop_last,'int_timestamp')}:R>" if self.player_loop_last else "None")
                + "```ini"
                + f"\n{'[Refresh]':<10} {True if self._player_loop_lock.locked() else False}"
                + f"\n{'[Running]':<10} {self.player_loop_status}"
                + f"\n{'[Tags]':<10} {len(self.coc_client._player_updates):,}"
                + f"\n{'[RunTime]':<10} " + (f"{sum(self.player_loop_runtime)/len(self.player_loop_runtime):.2f}" if len(self.player_loop_runtime) > 0 else "0") + "s"
                + f"\n{'[Last]':<10} " + (f"{self.player_loop_runtime[-1]:.2f}" if len(self.player_loop_runtime) > 0 else "0") + "s"
                + "```",
            inline=True
            )
        embed.add_field(
            name="**Clan Loops**",
            value=f"Last: " + (f"<t:{getattr(self.clan_loop_last,'int_timestamp')}:R>" if self.clan_loop_last else "None") 
                + "```ini"
                + f"\n{'[Refresh]':<10} {True if self._clan_loop_lock.locked() else False}"
                + f"\n{'[Running]':<10} {self.clan_loop_status}"
                + f"\n{'[Tags]':<10} {len(self.coc_client._clan_updates):,}"
                + f"\n{'[RunTime]':<10} " + (f"{sum(self.clan_loop_runtime)/len(self.clan_loop_runtime):.2f}" if len(self.clan_loop_runtime) > 0 else "0") + "s"
                + f"\n{'[Last]':<10} " + (f"{self.clan_loop_runtime[-1]:.2f}" if len(self.clan_loop_runtime) > 0 else "0") + "s"
                + "```",
            inline=True
            )
        embed.add_field(name="\u200b",value="\u200b",inline=True)
        embed.add_field(
            name="**Clan Wars**",
            value="Last: " + (f"<t:{getattr(self.war_loop_last,'int_timestamp',0)}:R>" if self.war_loop_last else "None")
                + "```ini"                
                + f"\n{'[Running]':<10} {self.war_loop_status}"
                + f"\n{'[Tags]':<10} {len(self.coc_client._war_updates):,}"
                + f"\n{'[RunTime]':<10} " + (f"{sum(self.war_loop_runtime)/len(self.war_loop_runtime):.2f}" if len(self.war_loop_runtime) > 0 else "0") + "s"
                + f"\n{'[Last]':<10} " + (f"{self.war_loop_runtime[-1]:.2f}" if len(self.war_loop_runtime) > 0 else "0") + "s"
                + "```",
            inline=True
            )
        embed.add_field(
            name="**Capital Raids**",
            value="Last: " + (f"<t:{getattr(self._raid_loop.last_loop,'int_timestamp',0)}:R>" if self._raid_loop.last_loop else "None")
                + "```ini"     
                + f"\n{'[Running]':<10} {self._raid_loop._running}"
                + f"\n{'[Tags]':<10} {len(self._raid_loop._tags):,}"
                + f"\n{'[RunTime]':<10} " + (f"{sum(self._raid_loop.run_time)/len(self._raid_loop.run_time):.2f}" if len(self._raid_loop.run_time) > 0 else "0") + "s"
                + "```",
            inline=True
            )
        embed.add_field(name="\u200b",value="\u200b",inline=True)
        return embed

    @commands.command(name="convwar")
    @commands.is_owner()
    async def cmd_convwar(self,ctx:commands.Context):
        wars = self.database.db__clan_war.find({})
        async for war in wars:
            war = await aClanWar(war['_id'])
            try:
                await war._convert()
                q = await self.database.db__nclan_war.find_one({"_id":war._id})
                nwar = bClanWar(data=q,client=self.coc_client,clan_tag=q['clan']['tag'])
                await nwar.load()
                LOG.info(f"Converted {nwar} {nwar.type}.")
            except:
                LOG.exception(f"Error converting {war._id}.")
        
        league_groups = self.database.db__war_league_group.find({})
        async for group in league_groups:
            league_group = await WarLeagueGroup(group['_id'])
            try:
                await league_group._convert()
                q = await self.database.db__nwar_league_group.find_one({"_id":league_group.id})
                nleague_group = bWarLeagueGroup(data=q,client=self.coc_client)
                await nleague_group.load()
                LOG.info(f"Converted {nleague_group}")
            except:
                LOG.exception(f"Error converting {league_group.id}.")
        
        await ctx.tick()
    
    @commands.group(name="cocdata")
    @commands.is_owner()
    async def command_group_clash_data(self,ctx):
        """Manage the Clash of Clans Data Client."""
        if not ctx.invoked_subcommand:
            pass

    @command_group_clash_data.command(name="status")
    @commands.is_owner()
    async def subcommand_clash_data_status(self,ctx:commands.Context):
        """Clash of Clans Data Status."""

        if not getattr(self,'_ready',False):
            return await ctx.reply("Clash of Clans API Client not yet initialized.")

        embed = await self.status_embed()
        view = RefreshStatus(ctx)
        await ctx.reply(embed=embed,view=view)
    
    @command_group_clash_data.command(name="resetloops")
    @commands.is_owner()
    async def subcommand_clash_data_resetloops(self,ctx:commands.Context):
        """Reset all Data Loops."""

        async with self._player_loop_lock, self._clan_loop_lock:
            current_list = list(self.coc_client._player_updates)
            self.coc_client.remove_player_updates(*current_list)

            current_list = list(self.coc_client._clan_updates)
            self.coc_client.remove_clan_updates(*current_list)

        await ctx.reply("Data Loops reset.")
    
    @command_group_clash_data.command(name="stream")
    @commands.is_owner()
    async def subcommand_clash_data_stream(self,ctx:commands.Context):
        """Toggle the Clash of Clans Data Stream."""

        current_data_level = LOG.level

        if current_data_level == logging.INFO:
            LOG.setLevel(logging.DEBUG)
            LOG.debug("Clash Data Stream enabled.")
            await ctx.reply("Clash Data Stream enabled.")
        
        else:
            LOG.setLevel(logging.INFO)
            LOG.info("Clash Data Stream disabled.")
            await ctx.reply("Clash Data Stream disabled.")
    
    @command_group_clash_data.command(name="cycle")
    @commands.is_owner()
    async def subcommand_clash_data_setcycle(self,ctx:commands.Context,cycle:int):
        """Set the current cycle ID."""

        chk_state = await self.database.db_data_controller.find_one({"_id":cycle})
        if chk_state and chk_state.get('active',False) and chk_state.get('process_id',0) != self.bot.user.id:
            return await ctx.reply(f"This cycle is currently being used by <@{chk_state.get('process_id',0)}>.")
        
        await self.database.db_data_controller.update_one(
            {"_id": cycle},
            {"$set": {
                "active": True,
                "process_id": self.bot.user.id
                }},
            upsert=True
            )
        await self.unload_event_tasks()
        await self.config.cycle_id.set(cycle)
        self.cycle_id = cycle
        await ctx.reply(f"Cycle ID now assigned to {self.bot.user.mention}.")

        await self.refresh_event_tasks()
    
    ############################################################
    #####
    ##### EVENTS
    #####
    ############################################################    
    @coc.ClientEvents.player_loop_start()
    async def player_loop_start(self,iteration_number:int):
        self._player_loop_tracker[iteration_number] = pendulum.now()
        self._player_loop_num = iteration_number
        self.player_loop_status = True

    @coc.ClientEvents.player_loop_finish()
    async def player_loop_end(self,iteration_number:int):
        start = self._player_loop_tracker.get(iteration_number,None)
        if start:
            self.player_loop_last = end = pendulum.now()
            self.player_loop_status = False
            self.player_loop_runtime.append(end.diff(start).in_seconds())
            del self._player_loop_tracker[iteration_number]
    
    @coc.ClientEvents.player_loop_finish()
    async def insert_player_activities(self,iteration_number:int):
        async with aPlayerActivity._queue_lock:
            pending = list(aPlayerActivity._queue)
            aPlayerActivity._queue.clear()

        if len(pending) > 0:
            st = pendulum.now()
            await self.database.db__player_activity.insert_many(pending)
            LOG.info(f"Inserted {len(pending)} Player Activities. Took {pendulum.now().diff(st).in_seconds()}s.")

            handled_tags = []
            p_iter = AsyncIter(pending)
            async for p in p_iter:
                tag = p['tag']
                season = aClashSeason.current()
                if tag in handled_tags:
                    continue

                await aPlayerSeason.create_member_snapshot(tag,season)
                await aPlayerSeason.create_stats_snapshot(tag,season)
                handled_tags.append(tag)

    @coc.ClientEvents.clan_loop_start()
    async def clan_loop_start(self,iteration_number:int):
        self._clan_loop_tracker[iteration_number] = pendulum.now()
        self.clan_loop_status = True
        self._clan_loop_num = iteration_number

    @coc.ClientEvents.clan_loop_finish()
    async def clan_loop_end(self,iteration_number:int):
        start = self._clan_loop_tracker.get(iteration_number,None)
        if start:
            self.clan_loop_last = end = pendulum.now()
            self.clan_loop_status = False
            self.clan_loop_runtime.append(end.diff(start).in_seconds())
            del self._clan_loop_tracker[iteration_number]

    @coc.ClientEvents.war_loop_start()
    async def war_loop_start(self,iteration_number:int):
        self._war_loop_tracker[iteration_number] = pendulum.now()
        self.war_loop_status = True
        self._war_loop_num = iteration_number

    @coc.ClientEvents.war_loop_finish()
    async def war_loop_end(self,iteration_number:int):
        start = self._war_loop_tracker.get(iteration_number,None)
        if start:
            self.war_loop_last = end = pendulum.now()
            self.war_loop_status = False
            self.war_loop_runtime.append(end.diff(start).in_seconds())
            del self._war_loop_tracker[iteration_number]

class RefreshStatus(DefaultView):
    def __init__(self,context:Union[discord.Interaction,commands.Context]):

        button = DiscordButton(
            function=self._refresh_embed,
            emoji=EmojisUI.REFRESH,
            label="Refresh",
            )

        super().__init__(context,timeout=9999999)
        self.is_active = True

        self.add_item(button)
    
    @property
    def task_cog(self) -> ClashOfClansData:
        return self.bot.get_cog("ClashOfClansData")
    
    async def _refresh_embed(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        embed = await self.task_cog.status_embed()
        await interaction.followup.edit_message(interaction.message.id,embed=embed)