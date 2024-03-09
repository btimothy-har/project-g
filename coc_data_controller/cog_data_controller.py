import asyncio
import os
import discord
import pendulum
import logging

from typing import *

from discord.ext import tasks

from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.utils import AsyncIter

from coc_main.cog_coc_main import ClashOfClansMain as coc_main
from coc_main.client.global_client import GlobalClient

from coc_main.utils.components import DefaultView, DiscordButton, clash_embed
from coc_main.utils.constants.ui_emojis import EmojisUI

LOG = logging.getLogger("coc.controller")

############################################################
############################################################
#####
##### TASKS COG
#####
############################################################
############################################################
class ClashOfClansDataController(commands.Cog,GlobalClient):
    """
    Clash of Clans Data Controller. Assigns players and clans to data cycles.
    """

    __author__ = coc_main.__author__
    __version__ = coc_main.__version__

    def __init__(self):
        self.slots_per_cycle = 0
        self.max_cycle = 0

        self.cycle_availability = {}

        #CONFIG
        self.config:Config = Config.get_conf(self,identifier=644530507505336330,force_registration=True)        

        default_global = {
            "slots_per_cycle": 10000,
            "max_cycle": 1
            }
        self.config.register_global(**default_global)
        self.control_lock = asyncio.Lock()

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
            f"{log_path}/coc_controller.log",
            maxBytes=3*1024*1024,
            backupCount=9
            )
        data_log_handler.setFormatter(log_formatter)
        LOG.addHandler(data_log_handler)

        self.slots_per_cycle = await self.config.slots_per_cycle()
        self.max_cycle = await self.config.max_cycle()

        asyncio.create_task(self.start_cog())

    async def start_cog(self):
        await self.bot.wait_until_ready()

        db_state = await self.database.db_data_controller.find_one({"_id": "env_control"})
        if db_state and db_state.get('active',False):
            if db_state.get('process_id',0) != self.bot.user.id:
                raise ValueError("Data Controller already active.")
        
        await self.database.db_data_controller.update_one(
            {"_id": "env_control"},
            {"$set": {
                "active": True,
                "process_id":self.bot.user.id
                }
            },
            upsert=True
            )
        LOG.info(f"Clash of Clans Data Controller started by {self.bot.user.id}.")        
        
        self.update_cycles.start()

    ##################################################
    ### COG UNLOAD
    ##################################################
    async def cog_unload(self):
        self.update_cycles.stop()       

        await self.database.db_data_controller.update_one(
            {"_id": "env_control"},
            {"$set": {"active": False}},
            upsert=True
            )
        LOG.info(f"Clash of Clans Data Controller stopped.")
    
    ############################################################
    #####
    ##### LOOPS
    #####
    ############################################################
    @tasks.loop(minutes=1)    
    async def update_cycles(self):
        if self.control_lock.locked():
            return
        
        async with self.control_lock:
            await self.cleanup_cycle()

            cycles = [0,1,2]
            c_iter = AsyncIter(cycles)
            async for cycle_num in c_iter:
                await self.assign_to_cycle(cycle_num)

    async def assign_to_cycle(self,cycle_num:int):
        if cycle_num == 0:
            query = {
                "$and": [
                    {"$or": [
                        {"_cycle_id": {"$exists": False}},
                        {"_cycle_id": {"$lt": 0}}
                        ]
                    },
                    {"$or": [
                        {"discord_user": {"$exists":True,"$gt":0}},
                        {"is_member": True}
                        ]}
                    ]
                }
        elif cycle_num == 1:
            query = {
                "$or": [
                    {"_cycle_id": {"$exists": False}},
                    {"_cycle_id": {"$lt": 0}}
                    ]
                }
        
            count = 0
            find_players = self.database.db__player.find(query).limit(1000)
            async for player in find_players:
                await self.database.db__player.update_one(
                    {"_id": player['_id']},
                    {"$set": {"_cycle_id": cycle_num}}
                    )
                count += 1
            if count > 0:
                LOG.info(f"Assigned {count} Players to Cycle {cycle_num}.")
        
        elif cycle_num == 2:
            query = {
                "$or": [
                    {"_cycle_id": {"$exists": False}},
                    {"_cycle_id": {"$lt": 0}}
                    ]
                }
        
            count = 0
            find_clans = self.database.db__clan.find(query).limit(1000)
            async for clan in find_clans:
                await self.database.db_clan.update_one(
                    {"_id": clan['_id']},
                    {"$set": {"_cycle_id": cycle_num}}
                    )
                count += 1
            if count > 0:
                LOG.info(f"Assigned {count} Clans to Cycle {cycle_num}.")

    async def cleanup_cycle(self):
        query = {
            "$and": [
                {"_cycle_id": {"$exists": True}},
                {"_cycle_id": {"$gt": 1}}
                ]
            }
        find_players = self.database.db__player.find(query).limit(1000)
        async for player in find_players:
            await self.database.db__player.update_one(
                {"_id": player['_id']},
                {"$unset": {"_cycle_id": 1}}
                )

    ############################################################
    #####
    ##### COMMANDS
    #####
    ############################################################
    @commands.group(name="cocdatacon",aliases=["controller"])
    @commands.is_owner()
    async def command_group_clash_data(self,ctx):
        """Manage the Clash of Clans Data Controller."""
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
    
    @command_group_clash_data.command(name="maxslots")
    @commands.is_owner()
    async def subcommand_clash_data_maxslots(self,ctx:commands.Context,slots:int):
        """Set the number of available slots per cycle."""

        await self.config.slots_per_cycle.set(slots)
        self.slots_per_cycle = slots
        await ctx.reply(f"Slots per cycle set to {slots}.")

    @command_group_clash_data.command(name="maxcycle")
    @commands.is_owner()
    async def subcommand_clash_data_maxcycle(self,ctx:commands.Context,cycle:int):
        """Set the maximum number of cycles."""

        await self.config.max_cycle.set(cycle)
        self.max_cycle = cycle
        await ctx.reply(f"Maximum cycle set to {cycle}.")
        await self._refresh_cycle_availability()

    async def status_embed(self):
        embed = await clash_embed(self.bot,
            title="**Clash of Clans Data Controller**",
            message=f"### {pendulum.now().format('dddd, DD MMM YYYY HH:mm:ssZZ')}",
            timestamp=pendulum.now()
            )

        embed.add_field(
            name="**Controller Client**",
            value=f"Slots per Cycle: {self.slots_per_cycle:,}"
                + f"\nMax Cycles: {self.max_cycle}"
                + f"\nControl Lock: {self.control_lock.locked()}",
            inline=True
            )
        
        embed.add_field(
            name="**Cycle Availability**",
            value='\n'.join([f"Cycle {k}: {v:,}" for k,v in self.cycle_availability.items()]),
            inline=True
            )
        return embed

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
    def cog(self) -> ClashOfClansDataController:
        return self.bot.get_cog("ClashOfClansDataController")
    
    async def _refresh_embed(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        embed = await self.cog.status_embed()
        await interaction.followup.edit_message(interaction.message.id,embed=embed)