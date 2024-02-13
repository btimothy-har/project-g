import coc
import discord
import asyncio
import hashlib
import pendulum

from typing import *

from discord.ext import tasks

from redbot.core import Config, commands, app_commands
from redbot.core.commands import Context
from redbot.core.utils import AsyncIter
from redbot.core.bot import Red

from coc_main.api_client import BotClashClient as client
from coc_main.cog_coc_client import ClashOfClansClient
from coc_main.coc_objects.season.season import aClashSeason
from coc_main.coc_objects.players.player import aPlayer
from coc_main.discord.add_delete_link import AddLinkMenu
from coc_main.utils.components import clash_embed, DefaultView, DiscordButton, DiscordSelectMenu, DiscordModal
from coc_main.utils.constants.ui_emojis import EmojisUI
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

        self.tourney_update_loop.start()
    
    async def cog_unload(self):
        self.tourney_update_loop.cancel()
    
    async def load_info_embed(self):
        info_message_id = await self.config.info_message()
        try:
            message = await self.info_channel.fetch_message(info_message_id)
        except:
            message = None

        embeds = []
        embed = await clash_embed(
            context=self.bot,
            title="*1LegioN & The Assassins Guild proudly presents...*",
            message=f"## {EmojisLeagues.LEGEND_LEAGUE} Legends League Tournament: March 2024 {EmojisLeagues.LEGEND_LEAGUE}"
                + f"\n\n### __Cash Prizes__"
                + f"\n🥇 **1st**: USD 50"
                + f"\n🥈 **2nd**: USD 35"
                + f"\n🥉 **3rd**: USD 25"
                + f"\n**4th - 5th**: USD 20"
                + f"\n**6th - 10th**: USD 15"
                + f"\n**11th - 15th**: USD 10"
                + f"\n\n*Cash Prizes will be distributed via PayPal. You __must__ have a PayPal account to receive your prizes. Winners will be contacted after the tournament.*"
                + f"\n### __Gold Pass Prizes__"
                + f"\n{EmojisTownHall.TH16} **TH16 Players**"
                + f"\nAll Players who finish above 5,700 trophies will be eligible for a lucky draw. 10 lucky winners will be selected for a Gold Pass!"
                + f"\n\n{EmojisTownHall.TH13} {EmojisTownHall.TH14} {EmojisTownHall.TH15} **TH13 - TH15 Players**"
                + f"\nThe top 5 finishing players in each Town Hall level will receive a Gold Pass."
                + f"\n\n*Gold Passes are distributed via The Guild's inventory system. Details will be provided after the tournament.*",
            show_author=False)
        embeds.append(embed)

        embed_2 = await clash_embed(
            context=self.bot,
            title="**Rules & Regulations**",
            message=f"1. The Tournament will be held during the in-game March 2024 Legend League Season."
                + f"\n2. This Tournament is open to the Clash of Clans Community."
                + f"\n3. Players may register with only **one** account of {EmojisTownHall.TH13} TH13 or higher."
                + f"\n4. Withdrawing from the Tournament is allowed any time before <t:1709096400:f>."
                + f"\n5. You must stay and join in The Guild's Discord Server to participate in the Tournament."
                + f"\n6. Your account must be a member of one the designated clans for the Tournament at least 70% of the time during the Tournament period."
                + f"\n7. The Townhall Level used for determining prizes shall be your Townhall Level at the end of the Legends Season."
                + f"\n### Designated Clans"
                + f"\n- [Assassins #92G9J8CG](https://link.clashofclans.com/en?action=OpenClanProfile&tag=%2392G9J8CG)",
            show_author=False)
        embeds.append(embed_2)
        
        view = TournamentApplicationMenu()

        if not message:            
            message = await self.info_channel.send(embeds=embeds,view=view)
            await self.config.info_message.set(message.id)
        
        if message:
            await message.edit(embeds=embeds,view=view)
        
    async def fetch_participant(self,tag:str) -> aPlayer:
        player = await self.client.fetch_player(tag)

        db_query = {'event_id':self.event_id,'tag':player.tag}
        tournament_db = await bot_client.coc_db.db__event_participant.find_one(db_query)
        
        player.is_participant = tournament_db.get('is_participant',False) if tournament_db else False
        player.discord_user = tournament_db.get('discord_user',0) if tournament_db else 0
        
        return player
    
    async def fetch_all_participants(self) -> List[aPlayer]:
        db_query = {'event_id':self.event_id,'is_participant':True}
        tournament_db = bot_client.coc_db.db__event_participant.find(db_query)

        participants = []
        async for participant in tournament_db:
            player = await self.fetch_participant(participant['tag'])
            participants.append(player)
        return participants
    
    async def fetch_participant_for_user(self,user_id:int) -> Optional[aPlayer]:
        db_query = {'event_id':self.event_id,'discord_user':user_id,'is_participant':True}
        tournament_db = await bot_client.coc_db.db__event_participant.find_one(db_query)

        if not tournament_db:
            return None
        return await self.fetch_participant(tournament_db['tag'])
    
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
    
    async def withdraw_participant(self,user_id:int) -> Optional[aPlayer]:
        db_query = {'event_id':self.event_id,'discord_user':user_id}
        await bot_client.coc_db.db__event_participant.update_many(
            db_query,
            {'$set':{'is_participant': False}},
            )
        return await self.fetch_participant_for_user(user_id)

    async def leaderboard_current_season_embed(self):
        participants = await self.fetch_all_participants()
        elig_participants = [p for p in participants if getattr(getattr(p,'legend_statistics',None),'current_season',None)]
        elig_participants.sort(key=lambda x: x.legend_statistics.current_season.trophies,reverse=True)

        #chunk the list into 30s
        chunks = [elig_participants[i:i + 30] for i in range(0, len(elig_participants), 30)]
        c_iter = AsyncIter(chunks)

        embeds = []
        async for i,chunk in c_iter.enumerate(start=1):
            player_text = "\n".join([
                f"{p.town_hall.emoji} `{p.clean_name:<30} {p.legend_statistics.current_season.trophies:,}`" for p in chunk])
            if i == 1:
                embed = await clash_embed(
                    context=self.bot,
                    title=f"1LxAG Legends League Tournament",
                    message=f"Last Refreshed: <t:{int(pendulum.now().int_timestamp)}:R>\n"
                        + player_text,
                    show_author=False
                    )
            else:
                embed = await clash_embed(
                    context=self.bot,
                    message=player_text,
                    show_author=False
                    )
            embeds.append(embed)
        return embeds
    
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
                embeds = await self.leaderboard_current_season_embed()                
                messages = await self.config.lb_messages()
                if len(messages) == 0:
                    new_msg = []
                    e_iter = AsyncIter(embeds)
                    async for i,embed in e_iter.enumerate(start=1):
                        message = await self.lb_channel.send(embed=embed)
                        new_msg.append(message.id)
                    await self.config.lb_messages.set(new_msg)
                else:
                    e_iter = AsyncIter(embeds)
                    async for i,embed in e_iter.enumerate(start=1):
                        try:
                            message = await self.lb_channel.fetch_message(messages[i-1])
                        except discord.NotFound:
                            message = await self.lb_channel.send(embed=embed)
                            messages[i-1] = message.id
                        except IndexError:
                            message = await self.lb_channel.send(embed=embed)
                            messages.append(message.id)
                        else:
                            await message.edit(embed=embed)
                    await self.config.lb_messages.set(messages)
            
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
    def tournament_cog(self) -> LegendsTourney:
        return bot_client.bot.get_cog("LegendsTourney")
    
    @property
    def button_registration(self) -> DiscordButton:
        return DiscordButton(
            function=self._callback_registration,
            label="Register",
            emoji=EmojisLeagues.LEGEND_LEAGUE,
            style=discord.ButtonStyle.blurple
            )
    
    @property
    def button_cancel(self) -> DiscordButton:
        return DiscordButton(
            function=self._callback_check,
            label="Cancel/Check",
            emoji=EmojisUI.REFRESH,
            style=discord.ButtonStyle.grey
            )

    async def on_timeout(self):
        pass

    def reload_items(self):
        self.clear_items()
        self.add_item(self.button_registration)
        self.add_item(self.button_cancel)
    
    async def _callback_registration(self,interaction:discord.Interaction,button:discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        self.reload_items()
        await interaction.followup.edit_message(interaction.message.id,view=self)
        
        add_link_view = RegistrationMenu(interaction,interaction.user)
        await add_link_view._start_add_link()
    
    async def _callback_check(self,interaction:discord.Interaction,button:discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        chk_registration = await self.tournament_cog.fetch_participant_for_user(interaction.user.id)

        if chk_registration:
            if pendulum.now().int_timestamp < 1709096400:
                embed = await clash_embed(
                    context=interaction,
                    message=f"You are currently registered for the Tournament with the account **{chk_registration.town_hall.emoji} {chk_registration.tag} {chk_registration.clean_name}**."
                        + f"\n\nIf you would like to cancel your registration, click on the button below.",
                    )
                cancel_view = CancelRegistrationMenu(interaction,interaction.user)
                await interaction.followup.send(embed=embed,view=cancel_view,ephemeral=True)
            else:
                embed = await clash_embed(
                    context=interaction,
                    message=f"You are currently registered for the Tournament with the account **{chk_registration.town_hall.emoji} {chk_registration.tag} {chk_registration.clean_name}**.",
                    )
                await interaction.followup.send(embed=embed,ephemeral=True)
        else:
            embed = await clash_embed(
                context=interaction,
                message=f"You are currently **NOT** registered for the Tournament."
                    + f"\n\nIf you would like to register, click on the Register button above.",
                )
            await interaction.followup.send(embed=embed,ephemeral=True)        
        return

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
    
    ##################################################
    #####
    ##### STANDARD APPLICATION FUNCTIONS
    #####
    ##################################################
    async def _start_add_link(self):
        self.is_active = True

        chk_participant = await self.tournament_cog.fetch_participant_for_user(self.member.id)
        if chk_participant:
            embed = await clash_embed(
                context=self.ctx,
                message=f"You are already registered for the Tournament with the account **{chk_participant.town_hall.emoji} {chk_participant.tag} {chk_participant.clean_name}**."
                    + f"\n\nPlease cancel your registration before registering with another account.",
                success=False
                )
            return await self.ctx.followup.send(embed=embed,ephemeral=True)

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
                message=f"The account **{self.add_link_account.town_hall.emoji} {self.add_link_account.tag} {self.add_link_account.name}** is already registered as a participant.",
                success=False
                )
            await interaction.followup.edit_message(self.m_id,embed=embed,view=None)
            return self.stop_menu()

        if self.add_link_account.town_hall.level < 13:
            verify = False
            embed = await clash_embed(
                context=self.ctx,
                message=f"The account **{self.add_link_account.town_hall.emoji} {self.add_link_account.tag} {self.add_link_account.name}** is not eligible for the Tournament. Only TH13 and above are allowed to participate.",
                success=False
                )
            await interaction.followup.edit_message(self.m_id,embed=embed,view=None)
            return self.stop_menu()

        if verify:
            await self.tournament_cog.register_participant(tag,self.member.id)
            embed = await clash_embed(
                context=self.ctx,
                message=f"The account **{self.add_link_account.town_hall.emoji} {self.add_link_account.tag} {self.add_link_account.name}** is now registered for the 1LxGuild Legends League Tournament! All the best!",
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

##################################################
#####
##### USER CANCEL REGISTRATION MENU
#####
##################################################
class CancelRegistrationMenu(DefaultView):
    def __init__(self,context:discord.Interaction,member:discord.Member):

        self.button_cancel_registration = DiscordButton(
            function=self._callback_cancel_registration,
            label="Cancel Registration",
            emoji=EmojisUI.NO,
            style=discord.ButtonStyle.red
            )
        self.button_exit = DiscordButton(
            function=self._callback_exit,
            label="Exit",
            emoji=EmojisUI.EXIT,
            style=discord.ButtonStyle.grey
            )
        
        super().__init__(context,timeout=120)
        self.add_item(self.button_cancel_registration)
        self.add_item(self.button_exit)
        self.is_active = True

    @property
    def tournament_cog(self) -> LegendsTourney:
        return bot_client.bot.get_cog("LegendsTourney")
    
    ##################################################
    #####
    ##### STANDARD APPLICATION FUNCTIONS
    #####
    ##################################################
    async def _callback_cancel_registration(self,interaction:discord.Interaction,button:discord.ui.Button):

        await interaction.response.defer(ephemeral=True)
        self.is_active = False
        await self.tournament_cog.withdraw_participant(interaction.user.id)
        embed = await clash_embed(
            context=self.ctx,
            message=f"Your registration for the Tournament has been cancelled.",
            success=True
            )
        await interaction.followup.edit_message(interaction.message.id,embed=embed,view=None)
    
    async def _callback_exit(self,interaction:discord.Interaction,button:discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        self.is_active = False
        embed = await clash_embed(
            context=self.ctx,
            message=f"Registration closed.",
            success=True
            )
        await interaction.followup.edit_message(interaction.message.id,embed=embed,view=None)
        self.stop()