import coc
import discord
import asyncio
import hashlib
import pendulum

from typing import *

from discord.ext import tasks

from redbot.core import Config, commands, app_commands
from redbot.core.commands import Context
from redbot.core.bot import Red

from coc_main.api_client import BotClashClient as client
from coc_main.cog_coc_client import ClashOfClansClient
from coc_main.coc_objects.season.season import aClashSeason
from coc_main.coc_objects.players.player import aPlayer
from coc_main.discord.add_delete_link import AddLinkMenu
from coc_main.utils.components import clash_embed, DiscordButton, DiscordSelectMenu, DiscordModal
from coc_main.utils.constants.coc_emojis import EmojisTownHall, EmojisLeagues
from coc_main.exceptions import ClashAPIError, InvalidTag

bot_client = client()

default_global = {
    "global_scope": 0,
    }

class LegendsTourney(commands.Cog):
    """1LxGuild Legends League Tournament March 2024"""

    __author__ = bot_client.author
    __version__ = bot_client.version

    def __init__(self,bot:Red):
        self.bot: Red = bot
        _id = "1LxGuildLegendsLeagueTourneyMarch2024"
        self.event_id = hashlib.sha256(_id.encode()).hexdigest()

        default_global = {
            "info_channel": 1206586918066978826 if bot.user.id == 828838353977868368 else 0,
            "info_message": 0,
            "lb_channel": 1206586918066978826 if bot.user.id == 828838353977868368 else 0,
            "lb_messages": [],
            "season": "2-2024",
            }

        self._update_lock = asyncio.Lock()

        self.config = Config.get_conf(self,identifier=644530507505336330,force_registration=True)        
        self.config.register_global(**default_global)
    
    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"

    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")    
    @property
    def info_channel(self) -> Optional[discord.TextChannel]:
        return self.bot.get_channel(self._info_channel)
    @property
    def lb_channel(self) -> Optional[discord.TextChannel]:
        return self.bot.get_channel(self._lb_channel)    
    @property
    def guild(self) -> Optional[discord.Guild]:
        if self.info_channel:
            return self.info_channel.guild
        if self.lb_channel:
            return self.lb_channel.guild
        return None

    async def cog_load(self):
        self._info_channel = await self.config.info_channel()
        self._lb_channel = await self.config.lb_channel()
        self._tourney_season = await self.config.season()

        asyncio.create_task(self.load_info_embed())
    
    async def load_info_embed(self):
        info_message_id = await self.config.info_message()
        try:
            message = await self.info_channel.fetch_message(info_message_id)
        except:
            message = None
        if not message:
            embed = await clash_embed(
                context=self.bot,
                title="1LxGuild Legends League Tournament",
                description="### League Season: March 2024",
                show_author=False
                )
            view = TournamentApplicationMenu()
            message = await self.info_channel.send(embed=embed,view=view)
            await self.config.info_message.set(message.id)
        
    async def fetch_participant(self,tag:str) -> aPlayer:
        player = await self.client.fetch_player(tag)

        db_query = {'event_id':self.event_id,'tag':player.tag}
        tournament_db = await bot_client.coc_db.db__event_participant.find_one(db_query)
        
        player.is_participant = tournament_db.get('is_participant',False) if tournament_db else False
        player.discord_user = tournament_db.get('discord_user',0) if tournament_db else 0
        
        return player
    
    async def register_participant(self,tag:str,user_id:int) -> aPlayer:

        db_query = {'event_id':self.event_id,'tag':tag}
        await bot_client.coc_db.db__event_participant.update_one(
            db_query,
            {'$set':{
                'tag': tag,
                'event_id': self.event_id,
                'is_participant': True,
                'discord_user': user_id
                }},
            upsert=True
            )
        return await self.fetch_participant(tag)
    
    @tasks.loop(minutes=15.0)
    async def tourney_update_loop(self):
        if self._update_lock.locked():
            return
        
        
        async with self._update_lock:

            league_season = await bot_client.coc.get_seasons(29000022)

            # league_season[0] is in YYYY-MM format, change to MM-YYYY
            last_season = await aClashSeason(pendulum.from_format(league_season[-1], 'YYYY-MM').format('M-YYYY'))
            
            # is current season
            if self._tourney_season == last_season.next_season().id:
                return
            
            # update for previous season
            if self._tourney_season == last_season.id:
                return
    
    async def update_info_embed(self):
        pass

##################################################
#####
##### MAIN APPLICATION MENU
#####
##################################################
class TournamentApplicationMenu(discord.ui.View):
    def __init__(self):

        super().__init__(timeout=None)
        self.reload_items()

    @property
    def coc_client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    @property
    def button_registration(self) -> DiscordButton:
        return DiscordButton(
            function=self._callback_registration,
            label="Register",
            emoji=EmojisLeagues.LEGEND_LEAGUE,
            style=discord.ButtonStyle.blurple
            )

    async def on_timeout(self):
        pass

    def reload_items(self):
        self.clear_items()
        self.add_item(self.button_registration)
    
    async def _callback_registration(self,interaction:discord.Interaction,button:discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        self.reload_items()
        await interaction.followup.edit_message(interaction.message.id,view=self)
        
        add_link_view = RegistrationMenu(interaction,interaction.user)
        await add_link_view._start_add_link()

##################################################
#####
##### USER APPLICATION MENU
#####
##################################################
class RegistrationMenu(AddLinkMenu):

    def __init__(self,context:discord.Interaction,member:discord.Member):
        super().__init__(context,member)
        self.add_link_modal.title = 'Tournament Registration'

    @property
    def tournament_cog(self) -> LegendsTourney:
        return bot_client.bot.get_cog("LegendsTourney")
    
    async def interaction_check(self,interaction:discord.Interaction):
        if interaction.user.id != self.member.id:
            await interaction.response.send_message(
                content="This doesn't belong to you!", ephemeral=True
                )
            return False
        return True
    
    ##################################################
    #####
    ##### STANDARD APPLICATION FUNCTIONS
    #####
    ##################################################
    async def _start_add_link(self):
        self.is_active = True
        embed = await clash_embed(
            context=self.ctx,
            message=f"To register your Clash of Clans account for the Tournament, you will need:"
                + f"\n1. The Account Tag of your account"
                + f"\n2. An in-game API Token"
                + f"\n\n**Refer to the image below on how to retrieve the API Token.** When you are ready, click on the button below to submit your Tag/Token pair."
                + f"\n\u200b",
            image='https://i.imgur.com/Q1JwMzK.png'
            )
        embed.add_field(
            name="**Important Information**",
            value="- If an account is already linked to another Discord account, this will not modify the existing link."
                + f"\n- Link information is not shared with other Clash of Clans bots.",
            inline=False
            )
        self.message = await self.ctx.followup.send(embed=embed,view=self,ephemeral=True,wait=True)
    
    async def _callback_add_link_modal(self,interaction:discord.Interaction,modal:DiscordModal):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.edit_message(self.m_id,view=None)

        o_tag = modal.children[0].value
        api_token = modal.children[1].value

        if not coc.utils.is_valid_tag(o_tag):
            raise InvalidTag(o_tag)
        
        tag = coc.utils.correct_tag(o_tag)
        
        if self.bot.user.id == 828838353977868368:
            verify = True
        else:
            try:
                verify = await bot_client.coc.verify_player_token(player_tag=tag,token=api_token)
            except (coc.NotFound) as exc:
                raise InvalidTag(tag) from exc
            except (coc.Maintenance,coc.GatewayError) as exc:
                raise ClashAPIError(exc) from exc

        self.add_link_account = await self.tournament_cog.fetch_participant(tag)

        if self.add_link_account.is_participant:
            verify = False
            embed = await clash_embed(
                context=self.ctx,
                message=f"The account {self.add_link_account.tag} {self.add_link_account.name} is already registered as a participant.",
                success=False
                )
            await interaction.followup.edit_message(self.m_id,embed=embed,view=None)
            return self.stop_menu()

        if verify:
            await self.tournament_cog.register_participant(tag,self.member.id)
            embed = await clash_embed(
                context=self.ctx,
                message=f"The account **{self.add_link_account.tag}** is now registered for the 1LxGuild Legends League Tournament!",
                success=True
                )
            await interaction.followup.edit_message(self.m_id,embed=embed,view=None)
        else:
            embed = await clash_embed(
                context=self.ctx,
                message=f"The API Token provided is invalid. Please try again.",
                success=False
                )
            await interaction.followup.edit_message(self.m_id,embed=embed,view=None)
        self.stop()