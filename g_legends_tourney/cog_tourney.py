import coc
import random
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
from coc_main.coc_objects.players.player import BasicPlayer, aPlayer
from coc_main.coc_objects.players.player_stat import aPlayerActivity
from coc_main.discord.add_delete_link import AddLinkMenu
from coc_main.utils.components import clash_embed, DefaultView, DiscordButton, DiscordSelectMenu, DiscordModal
from coc_main.utils.constants.ui_emojis import EmojisUI
from coc_main.utils.constants.coc_emojis import EmojisTownHall, EmojisLeagues
from coc_main.exceptions import ClashAPIError, InvalidTag

bot_client = client()

default_global = {
    "global_scope": 0,
    }

tournament_clans = ['#2LVJ98RR0']

class LegendsTourney(commands.Cog):
    """1LxGuild Legends League Tournament March 2024"""

    __author__ = bot_client.author
    __version__ = bot_client.version

    def __init__(self,bot:Red):
        self.bot: Red = bot
        _id = "1LxGuildLegendsLeagueTourneyMarch2024"
        self.event_id = hashlib.sha256(_id.encode()).hexdigest()

        default_global = {
            "info_channel": 1206586918066978826 if bot.user.id == 828838353977868368 else 1207540522181468200,
            "info_message": 0,
            "lb_channel": 1206596691151552553 if bot.user.id == 828838353977868368 else 1207540552120406016,
            "lb_messages": [],
            "participant_role": 1207526837429993532
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
    @property
    def participant_role(self) -> Optional[discord.Role]:
        if self.guild:
            return self.guild.get_role(self._participant_role)
        return None

    async def cog_load(self):
        self._info_channel = await self.config.info_channel()
        self._lb_channel = await self.config.lb_channel()
        self._participant_role = await self.config.participant_role()
        self._tourney_season = '3-2024'

        asyncio.create_task(self.load_info_embed())

        self.tourney_update_loop.start()
    
    async def cog_unload(self):
        self.tourney_update_loop.cancel()
    
    async def load_info_embed(self):
        await self.bot.wait_until_ready()

        info_message_id = await self.config.info_message()
        try:
            message = await self.info_channel.fetch_message(info_message_id)
        except:
            message = None

        tourn_season = await aClashSeason(self._tourney_season)

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
                + f"\n- {EmojisTownHall.TH16} **TH16:** All Players who finish above 5,700 trophies will be eligible for a lucky draw. 10 lucky winners will be selected for a Gold Pass!"
                + f"\n- {EmojisTownHall.TH13} {EmojisTownHall.TH14} {EmojisTownHall.TH15} **TH13 - TH15:** The top 5 finishing players in each Town Hall level will receive a Gold Pass."
                + f"\n\n*Gold Passes are distributed via The Guild's inventory system. Details will be provided after the tournament.*",
            show_author=False)
        embeds.append(embed)

        embed_2 = await clash_embed(
            context=self.bot,
            title="**Rules & Regulations**",
            message=f"1. The Tournament will be held during the in-game March 2024 Legend League Season."
                + f"\n2. This Tournament is open to the Clash of Clans Community."
                + f"\n3. Players may register with only **one** account of {EmojisTownHall.TH13} TH13 or higher."
                + f"\n4. Withdrawing from the Tournament is allowed any time before <t:{tourn_season.trophy_season_start.add(days=3).int_timestamp}:f>."
                + f"\n5. You must join and stay in The Guild's Discord Server throughout the Tournament to participate."
                + f"\n6. For TH16 participants, your account must be a member in any of the designated Tournament Clans for at least 70% of the time during the Tournament Period. You may check your current time spent with the `Cancel/Check` button below."
                + f"\n7. For purposes of determining time spent, the Tournament Period shall: (1) start from 3 days after the start of the in-game Legend League Season or when a participant registers, whichever is later; (2) end at the current moment or the last day of the in-game Legend League Season, whichever is earlier."
                + f"\n8. TH13 - TH15 participants do not need to meet the time spent requirement."
                + f"\n9. The Townhall Level used for determining prizes shall be your Townhall Level at the end of the Legends Season."
                + f"\n### Designated Clans"
                + f"\n- [1LegioN #2LVJ98RR0](https://link.clashofclans.com/en?action=OpenClanProfile&tag=%232LVJ98RR0)",
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
        
        registration_timestamp = tournament_db.get('timestamp',0) if tournament_db else 0
        player.registration_timestamp = pendulum.from_timestamp(registration_timestamp) if registration_timestamp else None
        
        return player
    
    async def fetch_all_participants(self) -> List[aPlayer]:
        db_query = {'event_id':self.event_id,'is_participant':True}
        tournament_db = bot_client.coc_db.db__event_participant.find(db_query)

        participants = []
        async for participant in tournament_db:
            player = await self.fetch_participant(participant['tag'])
            participants.append(player)
        
        if self.guild:
            left_participants = [p for p in participants if not self.guild.get_member(p.discord_user)]
            await asyncio.gather(*[self.withdraw_participant(p.discord_user) for p in left_participants])
        
        return participants
    
    async def fetch_participant_for_user(self,user_id:int) -> Optional[aPlayer]:
        db_query = {'event_id':self.event_id,'discord_user':user_id,'is_participant':True}
        tournament_db = await bot_client.coc_db.db__event_participant.find_one(db_query)

        if not tournament_db:
            return None
        return await self.fetch_participant(tournament_db['tag'])
    
    async def register_participant(self,player:aPlayer,user_id:int) -> aPlayer:
        db_query = {'event_id':self.event_id,'tag':player.tag}
        await bot_client.coc_db.db__event_participant.update_one(
            db_query,
            {'$set':{
                'tag': player.tag,
                'event_id': self.event_id,
                'is_participant': True,
                'discord_user': user_id,
                'timestamp': pendulum.now().int_timestamp
                }},
            upsert=True
            )
        if player.discord_user <= 0:
            await BasicPlayer.set_discord_link(player.tag,user_id)
        
        user = self.guild.get_member(user_id)
        await user.add_roles(self.participant_role)
        return await self.fetch_participant(player.tag)
    
    async def withdraw_participant(self,user_id:int) -> Optional[aPlayer]:
        db_query = {'event_id':self.event_id,'discord_user':user_id}
        await bot_client.coc_db.db__event_participant.update_many(
            db_query,
            {'$set':{'is_participant': False}},
            )
        user = self.guild.get_member(user_id)
        try:
            await user.remove_roles(self.participant_role)
        except:
            pass
        return await self.fetch_participant_for_user(user_id)

    async def leaderboard_current_season_embed(self):
        participants = await self.fetch_all_participants()
        elig_participants = [p for p in participants if getattr(getattr(p,'legend_statistics',None),'current_season',None)]
        elig_participants.sort(key=lambda x: (x.town_hall.level,x.legend_statistics.current_season.trophies),reverse=True)

        #chunk the list into 30s
        chunks = [elig_participants[i:i + 30] for i in range(0, len(elig_participants), 30)]
        c_iter = AsyncIter(chunks)

        embeds = []
        async for i,chunk in c_iter.enumerate(start=1):
            player_text = "\n".join([
                f"{p.town_hall.emoji} `{p.clean_name[:15]:<15} {p.legend_statistics.current_season.trophies:<6,}` <@{p.discord_user}>" for p in chunk if p.legend_statistics.current_season.trophies >= 5000])
            if i == 1:
                season = await aClashSeason(self._tourney_season)
                days_difference = pendulum.now().diff(season.trophy_season_start).in_days() + 1
                season_length = season.trophy_season_end.diff(season.trophy_season_start).in_days()

                embed = await clash_embed(
                    context=self.bot,
                    title=f"1LxAG Legends League Tournament",
                    message=f"### {EmojisLeagues.LEGEND_LEAGUE} Day {days_difference} of {season_length}"
                        + f"\nLast Refreshed: <t:{int(pendulum.now().int_timestamp)}:R>"
                        + f"\nTotal Participants: {len(elig_participants):,}\n\n"
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

    async def leaderboard_previous_season_embed(self):
        participants = await self.fetch_all_participants()
        elig_participants = [p for p in participants if getattr(getattr(p,'legend_statistics',None),'previous_season',None)]
        elig_participants.sort(key=lambda x: (x.town_hall.level,x.legend_statistics.previous_season.trophies),reverse=True)

        #chunk the list into 30s
        chunks = [elig_participants[i:i + 30] for i in range(0, len(elig_participants), 30)]
        c_iter = AsyncIter(chunks)

        embeds = []
        async for i,chunk in c_iter.enumerate(start=1):
            player_text = "\n".join([
                f"{p.town_hall.emoji} `{p.clean_name[:15]:<15} {p.legend_statistics.previous_season.trophies:<6,}` <@{p.discord_user}>" for p in chunk])
            if i == 1:
                embed = await clash_embed(
                    context=self.bot,
                    title=f"1LxAG Legends League Tournament",
                    message=f"Last Refreshed: <t:{int(pendulum.now().int_timestamp)}:R>"
                        + f"\nTotal Participants: {len(elig_participants):,}\n\n"
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

    async def leaderboard_future_season_embed(self):
        participants = await self.fetch_all_participants()
        elig_participants = participants
        elig_participants.sort(key=lambda x: (x.town_hall.level,x.trophies),reverse=True)

        #chunk the list into 30s
        chunks = [elig_participants[i:i + 30] for i in range(0, len(elig_participants), 30)]
        c_iter = AsyncIter(chunks)

        embeds = []
        async for i,chunk in c_iter.enumerate(start=1):
            player_text = "\n".join([
                f"\u200E{p.town_hall.emoji} `{p.clean_name[:15]:<20}` <@{p.discord_user}>\u200F" for p in chunk])
            if i == 1:
                season = await aClashSeason(self._tourney_season)
                days_difference = pendulum.now().diff(season.trophy_season_start,abs=False).in_days()

                embed = await clash_embed(
                    context=self.bot,
                    title=f"1LxAG Legends League Tournament",
                    message=f"### {EmojisLeagues.LEGEND_LEAGUE} {days_difference} Days to go!"
                        + f"\nLast Refreshed: <t:{int(pendulum.now().int_timestamp)}:R>"
                        + f"\nTotal Participants: {len(elig_participants):,}\n\n"
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
    
    @tasks.loop(minutes=5.0)
    async def tourney_update_loop(self):
        if self._update_lock.locked():
            return
        
        await self.bot.wait_until_ready()
        
        async with self._update_lock:

            league_season = await bot_client.coc.get_seasons(29000022)

            # league_season[0] is in YYYY-MM format, change to MM-YYYY
            last_season = await aClashSeason(pendulum.from_format(league_season[-1], 'YYYY-MM').format('M-YYYY'))
            
            # is current season
            if self._tourney_season == last_season.next_season().id:
                embeds = await self.leaderboard_current_season_embed()            
            # update for previous season
            elif self._tourney_season == last_season.id:
                embeds = await self.leaderboard_previous_season_embed()            
            else:
                embeds = await self.leaderboard_future_season_embed()
            
            new_msg = []
            messages = await self.config.lb_messages()
            if len(messages) == 0:                    
                e_iter = AsyncIter(embeds)
                async for i,embed in e_iter.enumerate(start=1):
                    message = await self.lb_channel.send(embed=embed)
                    new_msg.append(message.id)
            else:
                e_iter = AsyncIter(embeds)
                async for i,embed in e_iter.enumerate(start=1):
                    try:
                        message = await self.lb_channel.fetch_message(messages[i-1])
                    except discord.NotFound:
                        message = await self.lb_channel.send(embed=embed)
                        new_msg.append(message.id)
                    except IndexError:
                        message = await self.lb_channel.send(embed=embed)
                        new_msg.append(message.id)
                    else:
                        await message.edit(embed=embed)
                        new_msg.append(message.id)
                
                extra_msgs = [m for m in messages if m not in new_msg]
                m_iter = AsyncIter(extra_msgs)
                async for m_id in m_iter:
                    try:
                        message = await self.lb_channel.fetch_message(m_id)
                    except discord.NotFound:
                        pass
                    else:
                        await message.delete()
            await self.config.lb_messages.set(new_msg)
    
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
        self.reload_items()
        await interaction.followup.edit_message(interaction.message.id,view=self)

        await CancelRegistrationMenu.respond(interaction)

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
            await self.tournament_cog.register_participant(self.add_link_account,self.member.id)
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
    @classmethod
    async def respond(cls,interaction:discord.Interaction):
        
        menu = cls(interaction,interaction.user)
        chk_registration = await menu.tournament_cog.fetch_participant_for_user(interaction.user.id)

        tourn_season = await aClashSeason(menu.tournament_cog._tourney_season)

        if chk_registration:
            if pendulum.now() > tourn_season.trophy_season_start:
                check_window_start = chk_registration.registration_timestamp if chk_registration.registration_timestamp > tourn_season.trophy_season_start.add(days=3) else tourn_season.trophy_season_start.add(days=3)                
                check_window_end = tourn_season.trophy_season_end if pendulum.now() > tourn_season.trophy_season_end else pendulum.now()

                time_spent = 0

                snapshots = await aPlayerActivity.get_by_player_datetime(chk_registration.tag,check_window_start,check_window_end)
                a_iter = AsyncIter([a for a in snapshots if not a._legacy_conversion])
                ts = None
                async for a in a_iter:
                    if not ts:
                        if a.clan_tag in tournament_clans:
                            ts = a._timestamp
                    if ts:
                        if a.clan_tag in tournament_clans:
                            time_spent += max(0,a._timestamp - ts)
                        ts = a._timestamp
                
                tourn_period = tourn_season.trophy_season_end.diff(check_window_start).in_hours()
                time_spent_hours = (time_spent//3600)
                time_spent_str = f"You have spent **{int(min((time_spent_hours/tourn_period)*100,100))}%** of the Tournament Period in the designated clans.\n\n"
                
            else:
                time_spent_str = ""

            if pendulum.now() < tourn_season.trophy_season_start.add(days=3):
                embed = await clash_embed(
                    context=interaction,
                    message=f"You are currently registered with the account **{chk_registration.town_hall.emoji} {chk_registration.tag} {chk_registration.clean_name}**.\n\n"
                        + time_spent_str
                        + f"If you would like to cancel your registration, click on the button below.",
                    )
                menu.message = await interaction.followup.send(embed=embed,view=menu,ephemeral=True,wait=True)
            else:
                embed = await clash_embed(
                    context=interaction,
                    message=f"You are currently registered with the account **{chk_registration.town_hall.emoji} {chk_registration.tag} {chk_registration.clean_name}**.\n\n"
                        + time_spent_str,
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
        self.message = None
        
        super().__init__(context,timeout=120)
        self.add_item(self.button_cancel_registration)
        self.add_item(self.button_exit)
        self.is_active = True

    @property
    def tournament_cog(self) -> LegendsTourney:
        return bot_client.bot.get_cog("LegendsTourney")
    
    async def on_timeout(self):
        if self.message:
            await self.message.edit(view=None)
    
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