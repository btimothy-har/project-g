import asyncio
import discord
import pendulum
import logging
import coc

from typing import *

from discord.ext import tasks

from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter

from coc_main.api_client import BotClashClient as client
from coc_main.cog_coc_client import ClashOfClansClient

from coc_main.coc_objects.players.player import BasicPlayer, aPlayer
from coc_main.coc_objects.clans.clan import aClan

from coc_main.discord.member import aMember
from coc_main.discord.clan_link import ClanGuildLink
from coc_main.discord.feeds.donations import ClanDataFeed
from coc_main.discord.feeds.reminders import EventReminder
from coc_main.discord.application_panel import GuildApplicationPanel, listener_user_application

from coc_main.utils.components import DefaultView, DiscordButton, clash_embed
from coc_main.utils.constants.ui_emojis import EmojisUI

from .tasks.player_tasks import PlayerTasks
from .tasks.clan_tasks import ClanTasks
from .tasks.war_tasks import ClanWarLoop
from .tasks.raid_tasks import ClanRaidLoop
from .tasks.guild_tasks import DiscordGuildLoop

bot_client = client()

default_global = {
    "global_scope": 0,
    }

############################################################
############################################################
#####
##### TASKS COG
#####
############################################################
############################################################
class ClashOfClansData(commands.Cog):
    """
    Clash of Clans Data Client. Handles background loops/sync.
    """

    __author__ = bot_client.author
    __version__ = bot_client.version

    def __init__(self,bot:Red):
        self.bot = bot        
        self.config = Config.get_conf(self,identifier=644530507505336330,force_registration=True)        
        self.config.register_global(**default_global)        
        self.is_global = False

        self.player_queue_task = None
        self.clan_queue_task = None

        # DATA QUEUE
        self._lock_player_loop = asyncio.Lock()
        self._lock_clan_loop = asyncio.Lock()
        self._war_loop = ClanWarLoop()
        self._raid_loop = ClanRaidLoop()
        self._discord_loop = DiscordGuildLoop()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"

    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog('ClashOfClansClient')
    
    @property
    def api_maintenance(self) -> bool:
        return self.client.api_maintenance

    ##################################################
    ### COG LOAD
    ##################################################
    async def cog_load(self):
        self.is_global = await self.config.global_scope() == 1
        asyncio.create_task(self.start_task_cog())
        self.clan_queue_task = asyncio.create_task(self.clan_queue_loop())
        self.player_queue_task = asyncio.create_task(self.player_queue_loop())
    
    async def start_task_cog(self):
        async def load_nebula_tasks():
            bot_client.coc.add_events(                
                ClanTasks.on_clan_donation_change,
                ClanTasks.on_clan_member_join_feed,
                ClanTasks.on_clan_member_leave_feed,
                ClanTasks.on_clan_member_join_role,
                ClanTasks.on_clan_member_leave_role,
                )
            try:
                self.update_clan_loop.start()
            except:
                pass
            asyncio.create_task(self._war_loop.start())
            asyncio.create_task(self._raid_loop.start())
            asyncio.create_task(self._discord_loop.start())
            
        async def load_meteor_tasks():
            bot_client.coc.add_events(
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
                ClanTasks.on_clan_member_leave_capture
                )
            try:
                self.update_player_loop.start()
            except:
                pass
            try:
                self.update_clan_loop.start()
            except:
                pass
            
        while True:
            if getattr(bot_client,'_is_initialized',False):
                break
            await asyncio.sleep(1)

        await bot_client.bot.wait_until_ready()
        bot_client.coc.player_cls = aPlayer
        bot_client.coc.clan_cls = aClan

        #NEBULA Bot
        if self.bot.user.id == 1031240380487831664:
            await load_nebula_tasks()        
        #METEOR Bot
        if self.bot.user.id == 1176156235167449139:
            await load_meteor_tasks()
        #test bot
        if self.bot.user.id == 828838353977868368:
            await load_meteor_tasks()
            await load_nebula_tasks()

    ##################################################
    ### COG UNLOAD
    ##################################################
    async def cog_unload(self):

        async def unload_nebula_tasks():
            try:
                self.update_clan_loop.cancel()
            except:
                pass
            await self._war_loop.stop()
            await self._raid_loop.stop()
            await self._discord_loop.stop()

            bot_client.coc.remove_events(
                ClanTasks.on_clan_donation_change,
                ClanTasks.on_clan_member_join_feed,
                ClanTasks.on_clan_member_leave_feed,
                ClanTasks.on_clan_member_join_role,
                ClanTasks.on_clan_member_leave_role,
                )
            
        async def unload_meteor_tasks():
            try:
                self.update_player_loop.cancel()
            except:
                pass
            try:
                self.update_clan_loop.cancel()
            except:
                pass

            bot_client.coc.remove_events(
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
                ClanTasks.on_clan_member_join_capture,
                ClanTasks.on_clan_member_leave_capture
                )
            
        bot_client.coc.remove_clan_updates(*list(bot_client.coc._clan_updates))
        bot_client.coc.remove_player_updates(*list(bot_client.coc._player_updates))

        try:
            self.clan_queue_task.cancel()
        except:
            pass
        try:
            self.player_queue_task.cancel()
        except:
            pass
            
        #NEBULA Bot
        if self.bot.user.id == 1031240380487831664:
            await unload_nebula_tasks()        
        #METEOR Bot
        if self.bot.user.id == 1176156235167449139:
            await unload_meteor_tasks()
        #test bot
        if self.bot.user.id == 828838353977868368:
            await unload_nebula_tasks()
            await unload_meteor_tasks()
        
        bot_client.coc_main_log.info(f"Stopped Clash Data Loop.")

        aMember._global = {}
        aMember._local = {}
    
    ############################################################
    #####
    ##### CLASH OF CLANS CORE DATA LOOPS
    #####
    ############################################################
    @commands.Cog.listener("on_member_join")
    async def new_discord_member(self,member:discord.Member):
        linked_accounts = await bot_client.get_linked_players(member.id)
        async for player in bot_client.coc.get_players(linked_accounts):
            if player.discord_user == 0:
                await BasicPlayer.set_discord_link(player.tag,member.id)
    
    @commands.Cog.listener("on_guild_channel_create")
    async def recruiting_ticket_listener(self,channel):
        application_id = None
        await asyncio.sleep(2)        
        
        panels = await GuildApplicationPanel.get_for_guild(channel.guild.id)
        if len(panels) == 0:
            return
        
        async for message in channel.history(limit=1,oldest_first=True):
            for embed in message.embeds:
                if embed.footer.text == "Application ID":                    
                    application_id = embed.description
                    break
        if not application_id:
            return        
        await listener_user_application(channel, application_id)

    @tasks.loop(minutes=1)    
    async def update_player_loop(self):
        if self._lock_player_loop.locked():
            return
        
        limit = 1000
        
        async with self._lock_player_loop:
            current = list(bot_client.coc._player_updates)
            query = {
                "$and": [
                    {"_id": {"$nin": current}},
                    {"$or": [
                        {"discord_user": {"$exists":True,"$gt":0}},
                        {"is_member": True}
                        ]}
                    ]
                }
            db_query = bot_client.coc_db.db__player.find(query,{'_id':1})
            user_tags = [p['_id'] async for p in db_query]
            limit -= len(user_tags)
            bot_client.coc.add_player_updates(*user_tags)

            rem_query = {
                "$and": [
                    {"_id": {"$in": current}},
                    {"$or": [
                        {"discord_user": {"$exists":False}},
                        {"discord_user": {"$lte":0}}
                        ]}
                    ]
                }
            
            rem_db_query = bot_client.coc_db.db__player.find(rem_query,{'_id':1})
            user_tags = [p['_id'] async for p in rem_db_query]
            bot_client.coc.remove_player_updates(*user_tags)

            if self.is_global and limit > 0:
                current = list(bot_client.coc._player_updates)
                query = {"_id": {"$nin": current}}
                db_query = bot_client.coc_db.db__player.find(query,{'_id':1}).limit(limit)
                tags = [p['_id'] async for p in db_query]
                bot_client.coc.add_player_updates(*tags)  
    
    @tasks.loop(minutes=1)    
    async def update_clan_loop(self):
        if self._lock_clan_loop.locked():
            return
        
        limit = 1000
        
        async with self._lock_clan_loop:
            if bot_client.api_maintenance:
                return
            
            current = list(bot_client.coc._clan_updates)

            tags = []
            tags.extend([clan.tag for clan in await bot_client.coc.get_registered_clans()])
            tags.extend([clan.tag for clan in await bot_client.coc.get_alliance_clans()])
            tags.extend([clan.tag for clan in await bot_client.coc.get_war_league_clans()])

            guild_iter = AsyncIter(bot_client.bot.guilds)
            async for guild in guild_iter:
                links = await ClanGuildLink.get_for_guild(guild.id)
                tags.extend([link.tag for link in links])

            feeds = await ClanDataFeed.get_all()
            tags.extend([feed.tag for feed in feeds])

            reminders = await EventReminder.get_all()
            tags.extend([reminder.tag for reminder in reminders])

            loop_tags = list(set([t for t in tags if t not in current]))
            limit -= len(loop_tags)
            bot_client.coc.add_clan_updates(*loop_tags)
            self._war_loop.add_to_loop(*loop_tags)
            self._raid_loop.add_to_loop(*loop_tags)

            if self.is_global and limit > 0:
                current = list(bot_client.coc._clan_updates)
                query = {"_id": {"$nin": current}}
                db_query = bot_client.coc_db.db__clan.find(query,{'_id':1}).limit(limit)
                tags = [p['_id'] async for p in db_query]
                bot_client.coc.add_clan_updates(*tags)
    
    async def clan_queue_loop(self):
        sleep = 0.1
        try:
            while True:
                try:
                    tag = await bot_client.clan_queue.get()
                    n_tag = coc.utils.correct_tag(tag)

                    if n_tag in bot_client.coc._clan_updates:
                        bot_client.clan_queue.task_done()
                        continue

                    try:
                        clan = await bot_client.coc.get_clan(n_tag)
                    except:
                        continue
                    await clan._sync_cache()
                    bot_client.clan_queue.task_done()
                    await asyncio.sleep(sleep)

                except asyncio.CancelledError:
                    raise
                except Exception:
                    bot_client.coc_main_log.exception(f"Error in Clan Queue Task")
                    if not bot_client._is_initialized:
                        break
                    continue
        except asyncio.CancelledError:
            return
    
    async def player_queue_loop(self):
        sleep = 0.1
        try:
            while True:
                try:
                    tag = await bot_client.player_queue.get()
                    n_tag = coc.utils.correct_tag(tag)

                    if n_tag in bot_client.coc._player_updates:
                        bot_client.player_queue.task_done()
                        continue

                    try:
                        player = await bot_client.coc.get_player(n_tag)
                    except:
                        continue
                    await player._sync_cache()
                    bot_client.player_queue.task_done()
                    await asyncio.sleep(sleep)

                except asyncio.CancelledError:
                    raise
                except Exception:
                    bot_client.coc_main_log.exception(f"Error in Clan Queue Task")
                    if not bot_client._is_initialized:
                        break
                    continue
        except asyncio.CancelledError:
            return
        
    async def status_embed(self):
        embed = await clash_embed(self.bot,
            title="**Clash of Clans Data Status**",
            message=f"### {pendulum.now().format('dddd, DD MMM YYYY HH:mm:ssZZ')}"
                + f"\n\n**Current Season: {bot_client.current_season.description}**",
            timestamp=pendulum.now()
            )

        embed.add_field(
            name="**Data Client**",
            value=f"Season Check: " + (f"<t:{bot_client.last_season_check.int_timestamp}:R>" if bot_client.last_season_check else "None")
                + f"\nIs Global: {self.is_global}",
            inline=False
            )
        
        embed.add_field(
            name="**Player Loops**",
            value=f"Last: " + (f"<t:{getattr(bot_client.last_loop.get('player'),'int_timestamp')}:R>" if bot_client.last_loop.get('player') else "None")
                + "```ini"
                + f"\n{'[Refresh]':<10} {True if self._lock_player_loop.locked() else False}"
                + f"\n{'[Running]':<10} {bot_client.player_loop_status}"
                + f"\n{'[Tags]':<10} {len(bot_client.coc._player_updates):,}"
                + f"\n{'[RunTime]':<10} " + (f"{sum(bot_client.player_loop_runtime)/len(bot_client.player_loop_runtime):.2f}" if len(bot_client.player_loop_runtime) > 0 else "0") + "s"
                + f"\n{'[Last]':<10} " + (f"{bot_client.player_loop_runtime[-1]:.2f}" if len(bot_client.player_loop_runtime) > 0 else "0") + "s"
                + "```",
            inline=True
            )
        embed.add_field(
            name="**Clan Loops**",
            value=f"Last: " + (f"<t:{getattr(bot_client.last_loop.get('clan'),'int_timestamp',0)}:R>" if bot_client.last_loop.get('clan') else "None")
                + "```ini"
                + f"\n{'[Refresh]':<10} {True if self._lock_clan_loop.locked() else False}"
                + f"\n{'[Running]':<10} {bot_client.clan_loop_status}"
                + f"\n{'[Tags]':<10} {len(bot_client.coc._clan_updates):,}"
                + f"\n{'[RunTime]':<10} " + (f"{sum(bot_client.clan_loop_runtime)/len(bot_client.clan_loop_runtime):.2f}" if len(bot_client.clan_loop_runtime) > 0 else "0") + "s"
                + f"\n{'[Last]':<10} " + (f"{bot_client.clan_loop_runtime[-1]:.2f}" if len(bot_client.clan_loop_runtime) > 0 else "0") + "s"
                + "```",
            inline=True
            )
        embed.add_field(name="\u200b",value="\u200b",inline=True)
        embed.add_field(
            name="**Clan Wars**",
            value="Last: " + (f"<t:{getattr(bot_client.last_loop.get('war'),'int_timestamp',0)}:R>" if bot_client.last_loop.get('war') else "None")
                + "```ini"                
                + f"\n{'[Running]':<10} {self._war_loop._running}"
                + f"\n{'[Tags]':<10} {len(self._war_loop._tags):,}"
                + f"\n{'[RunTime]':<10} " + (f"{sum(bot_client.war_loop_runtime)/len(bot_client.war_loop_runtime):.2f}" if len(bot_client.war_loop_runtime) > 0 else "0") + "s"
                + "```",
            inline=True
            )
        embed.add_field(
            name="**Capital Raids**",
            value="Last: " + (f"<t:{getattr(bot_client.last_loop.get('raid'),'int_timestamp',0)}:R>" if bot_client.last_loop.get('raid') else "None")
                + "```ini"     
                + f"\n{'[Running]':<10} {self._raid_loop._running}"
                + f"\n{'[Tags]':<10} {len(self._raid_loop._tags):,}"
                + f"\n{'[RunTime]':<10} " + (f"{sum(bot_client.raid_loop_runtime)/len(bot_client.raid_loop_runtime):.2f}" if len(bot_client.raid_loop_runtime) > 0 else "0") + "s"
                + "```",
            inline=True
            )
        embed.add_field(name="\u200b",value="\u200b",inline=True)

        embed.add_field(
            name="**Discord**",
            value="Last: " + (f"<t:{getattr(bot_client.last_loop.get('guild'),'int_timestamp',0)}:R>" if bot_client.last_loop.get('guild') else "None")
                + "```ini"                
                + f"\n{'[Running]':<10} {self._discord_loop._running}"
                + f"\n{'[Guilds]':<10} {len(bot_client.bot.guilds):,}"
                + f"\n{'[Users]':<10} {len(bot_client.bot.users):,}"
                + f"\n{'[RunTime]':<10} " + (f"{sum(bot_client.discord_loop_runtime)/len(bot_client.discord_loop_runtime):.2f}" if len(bot_client.discord_loop_runtime) > 0 else "0") + "s"
                + "```",
            inline=True
            )
        embed.add_field(name="\u200b",value="\u200b",inline=True)
        embed.add_field(name="\u200b",value="\u200b",inline=True)
        return embed
    
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

        if not getattr(bot_client,'_is_initialized',False):
            return await ctx.reply("Clash of Clans API Client not yet initialized.")

        embed = await self.status_embed()
        view = RefreshStatus(ctx)
        await ctx.reply(embed=embed,view=view)
    
    @command_group_clash_data.command(name="setglobal")
    @commands.is_owner()
    async def subcommand_clash_data_setglobal(self,ctx:commands.Context,scope:int):
        """Toggle if the Data loop should accept a global scope."""

        if scope == 1:
            self.is_global = True
            await self.config.global_scope.set(1)
            await ctx.reply("Global Scope enabled.")
        else:
            self.is_global = False
            await self.config.global_scope.set(0)
            await ctx.reply("Global Scope disabled.")
    
    @command_group_clash_data.command(name="resetloops")
    @commands.is_owner()
    async def subcommand_clash_data_resetloops(self,ctx:commands.Context):
        """Reset all Data Loops."""

        async with self._lock_player_loop:
            current_list = list(bot_client.coc._player_updates)
            bot_client.coc.remove_player_updates(*current_list)

        async with self._lock_clan_loop:
            current_list = list(bot_client.coc._clan_updates)
            bot_client.coc.remove_clan_updates(*current_list)

        await ctx.reply("Data Loops reset.")
    
    @command_group_clash_data.command(name="stream")
    @commands.is_owner()
    async def subcommand_clash_data_stream(self,ctx:commands.Context):
        """Toggle the Clash of Clans Data Stream."""

        current_data_level = bot_client.coc_data_log.level

        if current_data_level == logging.INFO:
            bot_client.coc_main_log.setLevel(logging.DEBUG)
            bot_client.coc_data_log.setLevel(logging.DEBUG)
            bot_client.coc_main_log.debug("Clash Data Stream enabled.")
            await ctx.reply("Clash Data Stream enabled.")
        
        else:
            bot_client.coc_main_log.setLevel(logging.INFO)
            bot_client.coc_data_log.setLevel(logging.INFO)
            bot_client.coc_main_log.info("Clash Data Stream disabled.")
            await ctx.reply("Clash Data Stream disabled.")

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
        return bot_client.bot.get_cog("ClashOfClansData")
    
    async def _refresh_embed(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        embed = await self.task_cog.status_embed()
        await interaction.followup.edit_message(interaction.message.id,embed=embed)