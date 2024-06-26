import coc
import discord
import asyncio
import pendulum

from typing import *

from redbot.core import commands
from redbot.core.utils import AsyncIter, bounded_gather

from coc_main.coc_objects.season.season import aClashSeason
from coc_main.coc_objects.events.war_clans import bWarLeagueClan
from coc_main.coc_objects.events.war_players import bWarLeaguePlayer
from coc_main.coc_objects.events.war_summary import aClanWarSummary

from coc_main.discord.member import aMember

from coc_main.utils.components import clash_embed, DefaultView, DiscordButton, DiscordSelectMenu
from coc_main.utils.constants.coc_emojis import EmojisClash, EmojisLeagues, EmojisTownHall
from coc_main.utils.constants.coc_constants import WarResult, CWLLeagueGroups, MultiplayerLeagues
from coc_main.utils.constants.ui_emojis import EmojisUI

class NewRegistration():
    def __init__(self,account:bWarLeaguePlayer,league:int):
        self.account = account
        self.league = league

class CWLPlayerMenu(DefaultView):
    def __init__(self,
        context:Union[commands.Context,discord.Interaction],
        season:aClashSeason,
        member:aMember):

        self.season = season
        self.member = member
        self.accounts = []
        self.roster_clans = []

        self._ph_save_button = None        
        self.show_account_stats = None

        self.user_registration = {}
        self.current_signups = []
        self.live_cwl_accounts = []
        
        super().__init__(context=context,timeout=300)
    
    def get_live_account(self,tag:str) -> bWarLeaguePlayer:
        return next((p for p in self.live_cwl_accounts if p.tag == tag),None)
    
    def get_league_clan(self,tag:str) -> Optional[bWarLeagueClan]:
        return next((c for c in self.roster_clans if c.tag == tag),None)

    ##################################################
    ### OVERRIDE BUILT IN METHODS
    ##################################################
    async def on_timeout(self):
        timeout_embed = await clash_embed(
            context=self.ctx,
            message="Player Clan War League menu timed out.",
            success=False
            )
        if self.message:
            await self.message.edit(embed=timeout_embed,view=None)
        self.stop_menu()
    
    async def _close(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        close_embed = await clash_embed(
            context=self.ctx,
            message="Player Clan War League menu closed. Goodbye!",
            )
        await interaction.edit_original_response(embed=close_embed,view=None)
        self.stop_menu()
    
    ####################################################################################################
    #####
    ##### PRE-CWL: SIGNUPS
    #####
    ####################################################################################################

    ##################################################
    ### START SIGNUP
    ##################################################
    async def start_signup(self):
        guild = self.bot.get_guild(1132581106571550831) if self.bot.user.id == 1031240380487831664 else self.bot.get_guild(680798075685699691)
        member = guild.get_member(self.member.user_id)
        if member is None:
            embed = await clash_embed(
                context=self.ctx,
                message=f"You must join The Assassins Guild server to register for CWL. Please join the server at https://discord.gg/assassinsguild and try again.",
                success=False
                )
            if isinstance(self.ctx,discord.Interaction):
                await self.ctx.edit_original_response(embed=embed, view=self)
                self.message = await self.ctx.original_response()
            else:
                try:
                    self.message = await self.ctx.send(embed=embed, view=self)
                except discord.HTTPException:
                    self.message = await self.ctx.send(embed=embed, view=self)
            return            

        self.accounts = [p async for p in self.coc_client.get_players([p.tag for p in self.member.accounts])]
        self.accounts.sort(key=lambda x:(x.town_hall.level,x.name),reverse=True)

        self.roster_clans = await self.coc_client.get_league_clans(self.season,participating=True)

        self.is_active = True
        
        self.current_signups = await self.coc_client.get_league_players(
            season=self.season,
            discord_user=self.member.user_id,
            registered=True
            )
        
        self.signup_main_menu()
        embeds = await self.signup_embed()

        if isinstance(self.ctx,discord.Interaction):
            await self.ctx.edit_original_response(embeds=embeds, view=self)
            self.message = await self.ctx.original_response()
        else:
            try:
                self.message = await self.ctx.send(embeds=embeds, view=self)
            except discord.HTTPException:
                self.message = await self.ctx.send(embeds=embeds, view=self)
    
    ##################################################
    ### ADD SIGNUP
    ### Opens the start signup menu
    ##################################################
    async def _add_signups(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer(ephemeral=True)
        
        self.add_signup_menu()
        self._ph_save_button.reference = 'add'

        self.current_signups = await self.coc_client.get_league_players(
            season=self.season,
            discord_user=self.member.user_id,
            registered=True
            )
        embeds = await self.signup_embed()        
        signup_embed = await self.signup_instruction_embed()
        
        await interaction.edit_original_response(embeds=embeds,view=self)
        await interaction.followup.send(embed=signup_embed,ephemeral=True)
    
    ##################################################
    ### REMOVE SIGNUP
    ### Opens the remove signup menu
    ##################################################
    async def _remove_signups(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer(ephemeral=True)

        self.current_signups = await self.coc_client.get_league_players(
            season=self.season,
            discord_user=self.member.user_id,
            registered=True
            )
        
        self.remove_signup_menu()
        self._ph_save_button.reference = 'remove'
        embeds = await self.signup_embed()
        remove_embed = await self.unregister_instruction_embed()

        await interaction.edit_original_response(embeds=embeds,view=self)
        await interaction.followup.send(embed=remove_embed,ephemeral=True)
    
    ##################################################
    ### SAVE REGISTRATION
    ### Saves all pending registrations during this session
    ##################################################
    async def _save_signups(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()

        for item in self.children:
            item.disabled = True
        
        await interaction.edit_original_response(view=self)

        iter_signups = AsyncIter(list(self.user_registration.values()))
        tasks = []
        async for player in iter_signups:
            if player.league:
                tasks.append(player.account.register(self.member.user_id,player.league))
            else:
                tasks.append(player.account.unregister())

        await bounded_gather(*tasks,return_exceptions=True,limit=3)

        self.user_registration = {}

        self.current_signups = await self.coc_client.get_league_players(
            season=self.season,
            discord_user=self.member.user_id,
            registered=True
            )
        
        if button.reference == 'add':
            self.add_signup_menu()
        elif button.reference == 'remove':
            self.remove_signup_menu()
        
        for item in self.children:
            item.disabled = False

        self._ph_save_button.label = "Saved!"
        self._ph_save_button.disabled = True
        embeds = await self.signup_embed()
        await interaction.edit_original_response(embeds=embeds,view=self)
    
    ##################################################
    ### RESET SIGNUP
    ### Triggers a reset of the signup menu
    ##################################################
    async def _reset_signups(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()

        self.user_registration = {}
        self.current_signups = await self.coc_client.get_league_players(
            season=self.season,
            discord_user=self.member.user_id,
            registered=True
            )
        
        self.signup_main_menu()
        embed = await self.signup_embed()
        await interaction.edit_original_response(embeds=embed,view=self)
    
    ##################################################
    ### ADD REGISTRATION
    ### Facilitates the signups of accounts to a League Group
    ##################################################
    async def _callback_group_signup(self,interaction:discord.Interaction,select:DiscordSelectMenu):
        await interaction.response.defer()
        
        if len(select.values) > 0:
            for player_tag in select.values:
                league_player = await self.coc_client.get_league_player(player_tag,self.season)
                self.user_registration[player_tag] = NewRegistration(
                    league_player,
                    select.reference
                    )

        self.current_signups = await self.coc_client.get_league_players(
            season=self.season,
            discord_user=self.member.user_id,
            registered=True
            )

        self.add_signup_menu()
        self._ph_save_button.reference = 'add'
        embed = await self.signup_embed()
        await interaction.edit_original_response(embeds=embed,view=self)

    ##################################################
    ### REMOVE REGISTRATION
    ### Facilitates the removal of accounts from a League Group
    ##################################################
    async def _callback_group_unregister(self,interaction:discord.Interaction,select:DiscordSelectMenu):
        await interaction.response.defer()
        select.disabled = True

        if len(select.values) > 0:
            for player_tag in select.values:
                league_player = await self.coc_client.get_league_player(player_tag,self.season)
                self.user_registration[player_tag] = NewRegistration(
                    league_player,
                    None
                    )
        
        self.current_signups = await self.coc_client.get_league_players(
            season=self.season,
            discord_user=self.member.user_id,
            registered=True
            )
        
        if len(self.current_signups) == 0:
            self.signup_main_menu()
            embeds = await self.signup_embed()
            await interaction.edit_original_response(embeds=embeds,view=self)
        else:
            self.remove_signup_menu()
            self._ph_save_button.reference = 'remove'
            embeds = await self.signup_embed()
            select.disabled = False
            await interaction.edit_original_response(embeds=embeds,view=self)
    
    ####################################################################################################
    ##### PRE-CWL MENUS
    ####################################################################################################

    ##################################################
    ### BUTTONS
    ##################################################
    def _save_signup_button(self):
        return DiscordButton(
            function=self._save_signups,
            label="Save",
            emoji=EmojisUI.YES,
            style=discord.ButtonStyle.secondary,
            row=0
            )
    def _help_button(self):
        return DiscordButton(
            function=self._display_help,
            label="Help",
            emoji=EmojisUI.HELP,
            style=discord.ButtonStyle.green,
            row=0
            )
    def _close_button(self):
        return DiscordButton(
            function=self._close,
            emoji=EmojisUI.EXIT,
            style=discord.ButtonStyle.red,
            row=0
            )

    ##################################################
    ### MAIN MENU
    ##################################################
    def signup_main_menu(self):
        self.clear_items()
        
        self.add_item(self._help_button())
        self.add_item(self._close_button())

        remove_signups = len(self.current_signups) > 0

        _add_signups_button = DiscordButton(
            function=self._add_signups,
            label="Register for CWL",
            emoji=EmojisUI.ADD,
            style=discord.ButtonStyle.secondary,
            row=1
            )
        _remove_signups_button = DiscordButton(
            function=self._remove_signups,
            label="Cancel CWL Registration",
            emoji=EmojisUI.DELETE,
            style=discord.ButtonStyle.secondary,
            row=1
            )
        if not self.season.cwl_signup_status:
            _add_signups_button.disabled = True
            _add_signups_button.label = "CWL Closed"
        
        self.add_item(_add_signups_button)

        if self.season.cwl_signup_status:
            if not remove_signups:
                _remove_signups_button.disabled = True
            self.add_item(_remove_signups_button)
        
    ##################################################
    ### ADD REGISTRATION MENU
    ##################################################
    def add_signup_menu(self):
        self.clear_items()

        back_button = DiscordButton(
            function=self._reset_signups,
            label="Back",
            emoji=EmojisUI.GREEN_FIRST,
            style=discord.ButtonStyle.secondary,
            row=0
            )
        self.add_item(back_button)

        self._ph_save_button = self._save_signup_button()
        self.add_item(self._ph_save_button)
        self.add_item(self._close_button())

        group_1_accounts = [discord.SelectOption(
            label=str(account),
            value=account.tag,
            emoji=EmojisTownHall.get(account.town_hall.level),
            description=account.clan_description,
            default=False)
            for i,account in enumerate(self.accounts,start=1) if account.town_hall.level >= 15 and i <=25]
        
        group_2_accounts = [discord.SelectOption(
            label=str(account),
            value=account.tag,
            emoji=EmojisTownHall.get(account.town_hall.level),
            description=account.clan_description,
            default=False)
            for i,account in enumerate(self.accounts,start=1) if account.town_hall.level >= 13 and i <=25]
        
        group_3_accounts = [discord.SelectOption(
            label=str(account),
            value=account.tag,
            emoji=EmojisTownHall.get(account.town_hall.level),
            description=account.clan_description,
            default=False)
            for i,account in enumerate(self.accounts,start=1) if account.town_hall.level >= 10 and i <=25]

        group_4_accounts = [discord.SelectOption(
            label=str(account),
            value=account.tag,
            emoji=EmojisTownHall.get(account.town_hall.level),
            description=account.clan_description,
            default=False)
            for i,account in enumerate(self.accounts,start=1) if account.town_hall.level >= 4 and i <=25]
        
        if len(group_1_accounts) > 0:
            group_1_selector = DiscordSelectMenu(
                function=self._callback_group_signup,
                options=group_1_accounts,
                placeholder=f"Group A: Up to Champion I (TH15+)",
                min_values=0,
                max_values=len(group_1_accounts),
                row=1,
                reference=1
                )
            self.add_item(group_1_selector)
        
        if len(group_2_accounts) > 0:
            group_2_selector = DiscordSelectMenu(
                function=self._callback_group_signup,
                options=group_2_accounts,
                placeholder=f"Group B: Up to Master I (TH13+)",
                min_values=0,
                max_values=len(group_2_accounts),
                row=2,
                reference=2
                )
            self.add_item(group_2_selector)
        
        if len(group_3_accounts) > 0:
            group_3_selector = DiscordSelectMenu(
                function=self._callback_group_signup,
                options=group_3_accounts,
                placeholder=f"Group C: Up to Crystal I (TH10+)",
                min_values=0,
                max_values=len(group_3_accounts),
                row=3,
                reference=9
                )
            self.add_item(group_3_selector)
        
        if len(group_4_accounts) > 0:
            group_4_selector = DiscordSelectMenu(
                function=self._callback_group_signup,
                options=group_4_accounts,
                placeholder=f"Group D: Lazy CWL (TH6+)",
                min_values=0,
                max_values=len(group_4_accounts),
                row=4,
                reference=99
                )
            self.add_item(group_4_selector)
    
    ##################################################
    ### REMOVE REGISTRATION MENU
    ##################################################
    def remove_signup_menu(self):
        self.clear_items()
        back_button = DiscordButton(
            function=self._reset_signups,
            label="Back",
            emoji=EmojisUI.GREEN_FIRST,
            style=discord.ButtonStyle.secondary,
            row=0
            )
        self.add_item(back_button)
        self._ph_save_button = self._save_signup_button()
        self.add_item(self._ph_save_button)
        self.add_item(self._close_button())

        registered_accounts = [discord.SelectOption(
            label=f"{cwl_player.name} ({cwl_player.tag})",
            value=cwl_player.tag,
            emoji=EmojisTownHall.get(cwl_player.town_hall),
            description=CWLLeagueGroups.get_description_no_emoji(cwl_player.league_group),
            default=False)
            for cwl_player in self.current_signups
            if getattr(self.get_league_clan(cwl_player.roster_clan_tag),'roster_open',True)
            ]
        if len(registered_accounts) > 0:
            unregister_selector = DiscordSelectMenu(
                function=self._callback_group_unregister,
                options=registered_accounts,
                placeholder=f"Select Accounts to Unregister.",
                min_values=0,
                max_values=len(registered_accounts),
                row=1,
                reference=1
                )
            self.add_item(unregister_selector)
    
    ####################################################################################################
    ##### PRE-CWL CONTENT 
    ####################################################################################################
    
    ##################################################
    ### PRIMARY EMBED
    ##################################################
    async def signup_embed(self):
        embed_1_ct = 0
        embed_2_ct = 0
        embed = await clash_embed(
            context=self.ctx,
            title=f"Your CWL Registration: {self.season.description}",
            message=f"**CWL Starts**: <t:{self.season.cwl_start.int_timestamp}:f>"
                + f"\n**CWL Ends**: <t:{self.season.cwl_end.int_timestamp}:f>"
                + f"\n\nIf you don't see your account in the list below, ensure it is linked through `/profile` (or `$profile`)."
                + f"\n\n*For non-registered accounts, only {EmojisTownHall.TH10} TH10+ are shown.\nAccounts {EmojisTownHall.TH6} TH6 and up can be registered for Lazy CWL via the drop-down menu.*"
                + "\n\u200b",
                )
        embed_2 = await clash_embed(
            context=self.ctx,
            message=f"*Accounts 11-20 are shown below.\nIf you have more than 20 accounts, these may not be reflected.*",
            show_author=False
            )        
        
        a_iter = AsyncIter(self.current_signups)
        async for cwl_account in a_iter:
            try:
                player = await self.coc_client.get_player(cwl_account.tag)
            except coc.NotFound:
                continue
            roster_clan = self.get_league_clan(cwl_account.roster_clan_tag)

            if cwl_account.tag not in self.user_registration:
                if embed_1_ct < 10:
                    embed.add_field(
                        name=f"{EmojisUI.ELO} {cwl_account.war_elo:,}\u3000**{player.title}**",
                        value=(f"{CWLLeagueGroups.get_description(cwl_account.league_group)}" if cwl_account.league_group > 0 else "")
                            + (f"\n**{EmojisLeagues.get(roster_clan.league)} [{roster_clan.clean_name} {roster_clan.tag}]({roster_clan.share_link})**" if roster_clan and not roster_clan.roster_open else "")
                            + (f"\n{EmojisUI.TASK_WARNING} **Please move to your CWL Clan before CWL starts.**" if roster_clan and not roster_clan.roster_open and roster_clan.tag != getattr(player.clan,'tag',None) else "")
                            + f"\n{player.hero_description}"
                            + "\n\u200b",
                        inline=False
                        )
                    embed_1_ct += 1

                elif embed_2_ct < 10:
                    embed_2.add_field(
                        name=f"{EmojisUI.ELO} {cwl_account.war_elo:,}\u3000**{player.title}**",
                        value=(f"{CWLLeagueGroups.get_description(cwl_account.league_group)}" if cwl_account.league_group > 0 else "")
                            + (f"\n**{EmojisLeagues.get(roster_clan.league)} [{roster_clan.clean_name} {roster_clan.tag}]({roster_clan.share_link})**" if roster_clan and not roster_clan.roster_open else "")
                            + (f"\n{EmojisUI.TASK_WARNING} **Please move to your CWL Clan before CWL starts.**" if roster_clan and not roster_clan.roster_open and roster_clan.tag != getattr(player.clan,'tag',None) else "")
                            + f"\n{player.hero_description}"
                            + "\n\u200b",
                        inline=False
                        )
                    embed_2_ct += 1
                else:
                    break

        a_iter = AsyncIter(self.accounts)
        async for account in a_iter:
            if account.tag not in self.user_registration and account.tag not in [p.tag for p in self.current_signups] and account.town_hall_level >= 10:

                cwl_player = await self.coc_client.get_league_player(account.tag,self.season)

                if embed_1_ct < 10:
                    embed.add_field(
                        name=f"{EmojisUI.ELO} {account.war_elo:,}\u3000**{account.title}**",
                        value=f"Not Registered"
                            + (f"(Previously registered by <@{cwl_player.discord_user}>)" if cwl_player.discord_user and cwl_player.is_registered else "")
                            + f"\n{account.hero_description}"
                            + "\n\u200b",
                        inline=False
                        )
                    embed_1_ct += 1

                elif embed_2_ct < 10:
                    embed_2.add_field(
                        name=f"{EmojisUI.ELO} {account.war_elo:,}\u3000**{account.title}**",
                        value=f"Not Registered"
                            + (f"(Previously registered by <@{cwl_player.discord_user}>)" if cwl_player.discord_user and cwl_player.is_registered else "")
                            + f"\n{account.hero_description}"
                            + "\n\u200b",
                        inline=False
                        )
                    embed_2_ct += 1
                else:
                    break
        
        change_embed = await clash_embed(
            context=self.ctx,
            title=f"**Unsaved Changes**",
            message=f"Click the {EmojisUI.YES} **SAVE** button to save your changes below.\n"
                + f"Pressing {EmojisUI.GREEN_FIRST} **BACK** will discard the below changes.\n\u200b",
            show_author=False
            )
        r_iter = AsyncIter(list(self.user_registration.values()))
        async for m_account in r_iter:
            try:
                player = await self.coc_client.get_player(m_account.account.tag)
            except coc.NotFound:
                continue
            change_embed.add_field(
                name=f"**{player.title}**",
                value=f"{CWLLeagueGroups.get_description(m_account.league) if m_account.league else 'Registration Removed'}"
                    + f"\n{player.hero_description}"
                    + "\n\u200b",
                inline=False
                )
        
        r_embed = []
        r_embed.append(embed)
        if embed_2_ct > 0:
            r_embed.append(embed_2)
        if len(self.user_registration) > 0:
            r_embed.append(change_embed)
        return r_embed

    ##################################################
    ### INSTRUCTION EMBEDS
    ##################################################
    async def signup_instruction_embed(self):
        embed = await clash_embed(
            context=self.ctx,
            message="**Use the dropdowns above to register accounts to the respective League Groups.**"
                + f"\n\nFor more information on League Groups, use `/cwl info`."
                + "\nRemember to **`SAVE`** your registration when you are done.\nGoing **`BACK`** will discard any changes."
                + "\n\nIf an account is already registered:"
                + "\n> **Re-registering** it below will update the current registration."
                + "\n> **Doing nothing** will not change the current registration."
                + "\n\n**If you have more than 25 accounts, please contact a Leader.**",
            show_author=False
            )
        return embed

    async def unregister_instruction_embed(self):
        embed = await clash_embed(
            context=self.ctx,
            message="**Select an account from the dropdown above to unregister from CWL.**"
                + "\nRemember to **`SAVE`** your registration when you are done.\nGoing **`BACK`** will discard any changes."
                + "\n\nAccounts that have already been finalized into a CWL Roster **cannot** be unregistered.",
            show_author=False
            )
        return embed

    ##################################################
    ### HELP EMBEDS
    ##################################################
    async def _display_help(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer(ephemeral=True)

        embed = await clash_embed(
            context=self.ctx,
            title="CWL Registration Help",
            message=f"- You may modify your registration options at any time through this menu."
                + f"\n- Changes to your registration **cannot** be made once registration is closed."
                + f"\n- Once a CWL Roster has been finalized, you cannot withdraw your registration."
                + f"\n\nUse `/cwl info` for more details on CWL."
                + f"\n\u200b"
            )
        embed.add_field(
            name="**About League Groups**",
            value="When registering for CWL, you are required to register individual accounts to a **League Group**."
                + "\n\nLeague Groups provide a gauge to assist with rostering. The League Group you sign up for represents the **highest** league you are willing to play in. "
                + "**It is not a guarantee that you will play in that League.** Rosters are subject to availability and Alliance needs."
                + "\n\nThere are currently 4 League Groups available:"
                + f"\n> **League Group A**: {EmojisLeagues.CHAMPION_LEAGUE_I} Champion I ({EmojisTownHall.TH15} TH15+)"
                + f"\n> **League Group B**: {EmojisLeagues.MASTER_LEAGUE_II} Master League I ({EmojisTownHall.TH13} TH13+)"
                + f"\n> **League Group C**: {EmojisLeagues.CRYSTAL_LEAGUE_II} Crystal League I ({EmojisTownHall.TH10} TH10+)"
                + f"\n> **League Group D**: {EmojisLeagues.UNRANKED} Lazy CWL (TH6+; heroes down wars)"
                + "\n\n**Note**: If you do not have any accounts eligible for a specific League Group, you will not be able to register for that group."
                + "\n\u200b",
            inline=False
            )
        embed.add_field(
            name="**Example: How League Groups Work**",
            value="If you sign up for League Group B (Master League I):\n"
                + "\n> You will **not** be rostered in a Champion League III clan."
                + "\n> You **can** be rostered for a Crystal League III clan."
                + "\n\u200b",
            inline=False
            )
        embed.add_field(
            name="**Account Linking**",
            value="To link or unlink accounts, use the `/profile` command."
                + "\n\nNote: Your Discord User is captured at the time of registration. Unlinking your accounts will **not** change your CWL registration."
                + "\n- If you wish to cancel your registration, use the `Unregister` button."
                + "\n- If you wish to transfer your registration to another player, the other player should link the account to their profile, and re-register for CWL."
                + "\n\u200b",
            inline=False
            )
        await interaction.followup.send(embed=embed,ephemeral=True)
    
    ####################################################################################################
    #####
    ##### DURING CWL: STATS
    #####
    ####################################################################################################

    ##################################################
    ### START LIVE CWL
    ##################################################
    async def show_live_cwl(self):
        self.live_cwl_accounts = [a for a in await self.coc_client.get_league_players(self.season,registered=True,discord_user=self.member.user_id)]

        if len(self.live_cwl_accounts) == 0:
            embed = await clash_embed(
                context=self.ctx,
                message="Oops! You don't seem to be participating in CWL this season. Please contact a Leader if you believe this is in error.",
                success=False
                )
            if isinstance(self.ctx,discord.Interaction):
                await self.ctx.edit_original_response(embed=embed, view=None)
                self.message = await self.ctx.original_response()
            else:
                try:
                    self.message = await self.ctx.send(embed=embed,view=None)
                except discord.HTTPException:
                    self.message = await self.ctx.send(embed=embed,view=None)
            return self.stop_menu()        

        for account in self.live_cwl_accounts:
            account.league_clan = await self.coc_client.get_league_clan(account.league_clan_tag,season=self.season) if account.league_clan_tag else None
            account.roster_clan = await self.coc_client.get_league_clan(account.roster_clan_tag,season=self.season) if account.roster_clan_tag else None
        
        #sort cwl accounts by clan league, then clan name
        self.live_cwl_accounts.sort(
            key=lambda x:(MultiplayerLeagues.get_index(getattr(x.league_clan,'league','')),
                        MultiplayerLeagues.get_index(getattr(x.roster_clan,'league','')),
                        getattr(x.league_clan,'name',''),
                        getattr(x.roster_clan,'name','')),
            reverse=True
            )
        
        self.is_active = True
        self.stats_menu()
        embed = await self.player_cwl_stats_by_account()
        
        if isinstance(self.ctx,discord.Interaction):
            await self.ctx.edit_original_response(embeds=embed, view=self)
            self.message = await self.ctx.original_response()
        else:
            try:
                self.message = await self.ctx.send(embeds=embed, view=self)
            except discord.HTTPException:
                self.message = await self.ctx.send(embeds=embed, view=self)
    
    ##################################################
    ### LIVE CWL CALLBACKS
    ##################################################
    async def _callback_live_cwl_home(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        self.show_account_stats = None
        embed = await self.player_cwl_stats_by_account()        
        self.stats_menu(current_page=0)
        await interaction.edit_original_response(embeds=embed,view=self)
    
    async def _callback_live_cwl_hitrate(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        self.show_account_stats = None
        embed = await self.player_cwl_stats_overall()
        self.stats_menu(current_page=1)
        await interaction.edit_original_response(embeds=embed,view=self)
    
    async def _callback_view_account_stats(self,interaction:discord.Interaction,select:DiscordSelectMenu):
        await interaction.response.defer()

        self.show_account_stats = self.get_live_account(select.values[0])
        embed = await self.player_cwl_stats_warlog()
        
        self.stats_menu(current_page=9)
        await interaction.edit_original_response(embeds=embed,view=self)
    
    ##################################################
    ### MENU HELPERS
    ##################################################
    def stats_menu(self,current_page=None):
        self.clear_items()
        #stats_toggle

        home_button = DiscordButton(
            function=self._callback_live_cwl_home,
            label="My CWL",
            emoji=EmojisClash.WARLEAGUES,
            style=discord.ButtonStyle.blurple,
            row=0
            )
        if current_page == 0 or current_page == None:
            home_button.disabled = True
        self.add_item(home_button)

        hitrate_button = DiscordButton(
            function=self._callback_live_cwl_hitrate,
            label="My Stats",
            emoji=EmojisClash.THREESTARS,
            style=discord.ButtonStyle.secondary,
            row=0
            )
        if current_page == 1:
            hitrate_button.disabled = True
        self.add_item(hitrate_button)
        self.add_item(self._close_button())
        
        #dropdown stats per account
        cwl_accounts = [discord.SelectOption(
            label=f"{cwl_player.name} ({cwl_player.tag})",
            value=cwl_player.tag,
            emoji=EmojisTownHall.get(cwl_player.town_hall),
            description=f"CWL Roster: {cwl_player.league_clan.name} ({cwl_player.league_clan.tag})" if cwl_player.league_clan else f"CWL Roster: {cwl_player.roster_clan.name} ({cwl_player.roster_clan.tag})" if cwl_player.roster_clan else "Not in CWL Roster",
            default=cwl_player.tag == getattr(self.show_account_stats,'tag',None))
            for cwl_player in self.live_cwl_accounts
            ]
        if len(cwl_accounts) > 0:
            stats_selector = DiscordSelectMenu(
                function=self._callback_view_account_stats,
                options=cwl_accounts,
                placeholder=f"Select an Account to view war log.",
                min_values=1,
                max_values=1,
                row=1
                )
            self.add_item(stats_selector)
    
    ##################################################
    ### CONTENT HELPERS
    ##################################################
    async def player_cwl_stats_by_account(self):
        embed = await clash_embed(
            context=self.ctx,
            title=f"Your CWL: {self.season.description}",
            message=f"**CWL Starts**: <t:{self.season.cwl_start.int_timestamp}:f>"
                + f"\n**CWL Ends**: <t:{self.season.cwl_end.int_timestamp}:f>"
                + f"\n\n*Overall stats are not live and may be delayed.*"
                + "\n\u200b",
                )
        embed_2 = await clash_embed(
                context=self.ctx,
                message=f"*Accounts 11-20 are shown below.\nIf you have more than 20 accounts, these may not be reflected.*",
                show_author=False)
        
        ct = 0
        a_iter = AsyncIter(self.live_cwl_accounts)
        async for cwl_player in a_iter:
            try:
                player = await self.coc_client.get_player(cwl_player.tag)
            except coc.NotFound:
                continue

            ct += 1
            e = embed
            if ct > 10:
                e = embed_2
            
            if cwl_player.league_clan:
                e.add_field(
                    name=f"{EmojisUI.ELO} {cwl_player.war_elo:,}\u3000**{cwl_player.title}**",
                    value=f"**{EmojisLeagues.get(cwl_player.league_clan.league)} [{cwl_player.league_clan.name} {cwl_player.league_clan.tag}]({cwl_player.league_clan.share_link})**"
                        + (f"\n{EmojisUI.TASK_WARNING} **You are not in your CWL Clan.**" if cwl_player.league_clan.tag != getattr(player.clan,'tag',None) else ""),
                    inline=False
                    )                
            
                league_group = await self.coc_client.get_league_group(cwl_player.league_clan.tag,self.season)
                league_wars = [w async for w in league_group.get_wars_for_clan(cwl_player.league_clan_tag)]
                
                try:
                    current_war = [w for w in league_wars if w.state in 'inWar'][-1]
                except IndexError:
                    try:
                        current_war = [w for w in league_wars if w.state in 'preparation'][-1]
                    except IndexError:
                        try:
                            current_war = [w for w in league_wars if w.state in 'warEnded'][-1]
                        except IndexError:
                            current_war = [w for w in league_wars][-1]

                e.add_field(
                    name=f"**Current War (Round: {league_group.current_round})**",
                    value=(f"**War Ends In**: <t:{current_war.end_time.int_timestamp}:R>" if current_war.state == 'inWar' else f"**War Starts In**: <t:{current_war.start_time.int_timestamp}:R>" if current_war.state == 'preparation' else "War Ended" if current_war.state == 'warEnded' else "")
                        + ("Not In War" if not current_war.get_member(cwl_player.tag) else "")
                        + (f"\n{EmojisClash.ATTACK} `{str(len(current_war.get_member(cwl_player.tag).attacks)) + ' / ' + str(current_war.attacks_per_member):^5}`" if current_war.get_member(cwl_player.tag) else "")
                        + (f"\n{EmojisClash.STAR} `{current_war.get_member(cwl_player.tag).total_stars:^5}`" if current_war.get_member(cwl_player.tag) else "")
                        + (f"\u3000{EmojisClash.DESTRUCTION} `{str(current_war.get_member(cwl_player.tag).total_destruction)+'%':^5}` " if current_war.get_member(cwl_player.tag) else "")
                        + "\n\u200b",
                    inline=True
                    )
                
                war_stats = aClanWarSummary.for_player(
                    cwl_player.tag,
                    [w for w in league_wars if w.state not in ['preparation'] and w.get_member(cwl_player.tag)]
                    )
                e.add_field(
                    name=f"**Overall Stats**",
                    value=f"{EmojisClash.ATTACK} `{str(war_stats.attack_count) + ' / ' + str(war_stats.attack_count + war_stats.unused_attacks):^5}`"
                        + f"\n{EmojisClash.THREESTARS} `{war_stats.triples:^5}`"
                        + f"\n{EmojisClash.STAR} `{war_stats.offense_stars:^5}`"
                        + f"\n{EmojisClash.DESTRUCTION} `{str(war_stats.offense_destruction)+'%':^5}`"
                        + f"\n{EmojisUI.ELO} `{war_stats.elo_change:^5,.1f}`"
                        + "\n\u200b",
                    inline=True
                    )
            
            elif cwl_player.roster_clan:
                e.add_field(
                    name=f"{EmojisUI.ELO} {cwl_player.war_elo:,}\u3000**{cwl_player.title}**",
                    value=f"**{EmojisLeagues.get(cwl_player.roster_clan.league)} [{cwl_player.roster_clan.name} {cwl_player.roster_clan.tag}]({cwl_player.roster_clan.share_link})**"
                        + (f"\n{EmojisUI.TASK_WARNING} **You are not in your CWL Clan.**" if cwl_player.roster_clan.tag != getattr(player.clan,'tag',None) else "")
                        + (f"\n*CWL Not Started*\n\u200b"),
                    inline=False
                    )    
        if ct > 10:
            return [embed,embed_2]
        return [embed]
    
    async def player_cwl_stats_overall(self):
        def _get_overall_stats():
            overall_stats = [aClanWarSummary.for_player(a.tag,a.league_clan.league_wars) for a in self.live_cwl_accounts if a.league_clan]
            return overall_stats

        overall_stats = await self.run_in_thread(_get_overall_stats)

        total_wars = sum([x.wars_participated for x in overall_stats])
        total_attacks = sum([x.attack_count for x in overall_stats])
        unused_attacks = sum([x.unused_attacks for x in overall_stats])
        total_triples = sum([x.triples for x in overall_stats])
        total_stars = sum([x.offense_stars for x in overall_stats])
        total_destruction = sum([x.offense_destruction for x in overall_stats])

        embed = await clash_embed(
            context=self.ctx,
            title=f"Your CWL: {self.season.description}",
            message=f"**CWL Starts**: <t:{self.season.cwl_start.int_timestamp}:f>"
                + f"\n**CWL Ends**: <t:{self.season.cwl_end.int_timestamp}:f>"
                + f"\n\n*Overall stats are not live and may be delayed.*"
                + "\n"
                + f"{EmojisClash.WARLEAGUES} `{total_wars:^3}`\u3000"
                + f"{EmojisClash.THREESTARS} `{total_triples:^3}`\u3000"
                + f"{EmojisClash.UNUSEDATTACK} `{unused_attacks:^3}`\n"
                + f"{EmojisClash.STAR} `{total_stars:<3}`\u3000{EmojisClash.DESTRUCTION} `{total_destruction:>5}%`"
                + "\n\u200b",
                )
        
        overall_hit_rate = {}
        async for th in AsyncIter(list(set([p.town_hall for p in self.live_cwl_accounts]))):
            overall_hr = [s.hit_rate_for_th(th) for s in overall_stats]
            
            async for hit_rate in AsyncIter(overall_hr):
                async for def_th in AsyncIter(list(hit_rate.values())):
                    th = f"{def_th['attacker']}v{def_th['defender']}"
                    if th not in overall_hit_rate:
                        overall_hit_rate[th] = {
                            'attacker':def_th['attacker'],
                            'defender':def_th['defender'],
                            'total':0,
                            'stars':0,
                            'destruction':0,
                            'triples':0
                            }
                    overall_hit_rate[th]['total'] += def_th['total']
                    overall_hit_rate[th]['stars'] += def_th['stars']
                    overall_hit_rate[th]['destruction'] += def_th['destruction']
                    overall_hit_rate[th]['triples'] += def_th['triples']
        
        for hr in list(overall_hit_rate.values()):
            embed.add_field(
                name=f"{EmojisTownHall.get(int(hr['attacker']))} TH{hr['attacker']} vs {EmojisTownHall.get(int(hr['defender']))} TH{hr['defender']}",
                value=f"{EmojisClash.ATTACK} `{hr['total']:^3}`\u3000"
                    + f"{EmojisClash.STAR} `{hr['stars']:^3}`\u3000"
                    + f"{EmojisClash.DESTRUCTION} `{hr['destruction']:^5}%`"
                    + f"\nHit Rate: {hr['triples']/hr['total']*100:.0f}% ({hr['triples']} {EmojisClash.THREESTARS} / {hr['total']} {EmojisClash.ATTACK})"
                    + f"\nAverage: {EmojisClash.STAR} {hr['stars']/hr['total']:.2f}\u3000{EmojisClash.DESTRUCTION} {hr['destruction']/hr['total']:.2f}%",
                inline=False
                )
        return [embed]

    async def player_cwl_stats_warlog(self):
        if not self.show_account_stats.league_clan:
            embed = await clash_embed(
                context=self.ctx,
                message=f"CWL has not yet started for **{self.show_account_stats.name}**.",
                success=False
                )
            return [embed]
        
        league_group = await self.coc_client.get_league_group(self.league_clan.tag,self.season)
        league_wars = [w async for w in league_group.get_wars_for_player(self.show_account_stats.tag)]
        
        war_stats = aClanWarSummary.for_player(self.show_account_stats.tag,league_wars)

        embed = await clash_embed(
            context=self.ctx,
            title=f"CWL Warlog: {self.show_account_stats.title}",
            message=f"**Stats for: CWL {self.season.season_description} ({EmojisLeagues.get(self.show_account_stats.league_clan.league)} {self.show_account_stats.league_clan.name})**"
                + f"\n*Overall stats are not live and may be delayed.*"
                + f"\n\n{EmojisClash.WARLEAGUES} `{war_stats.wars_participated:^3}`\u3000"
                + f"{EmojisClash.THREESTARS} `{war_stats.triples:^3}`\u3000"
                + f"{EmojisClash.UNUSEDATTACK} `{war_stats.unused_attacks:^3}`\n"
                + f"{EmojisClash.ATTACK}\u3000{EmojisClash.STAR} `{war_stats.offense_stars:<3}`\u3000{EmojisClash.DESTRUCTION} `{war_stats.offense_destruction:>3}%`\n"
                + f"{EmojisClash.DEFENSE}\u3000{EmojisClash.STAR} `{war_stats.defense_stars:<3}`\u3000{EmojisClash.DESTRUCTION} `{war_stats.defense_destruction:>3}%`\n"
                + "\u200b",
                )
        if war_stats.wars_participated > 0:
            war_log = sorted(war_stats.war_log,key=lambda x:(x.end_time),reverse=True)
            iter = AsyncIter(war_log)
            async for war in iter:
                war_member = war.get_member(self.show_account_stats.tag)
                if war_member:
                    war_attacks = sorted(war_member.attacks,key=lambda x:(x.order))
                    war_defenses = sorted(war_member.defenses,key=lambda x:(x.order))
                    attack_str = "\n".join(
                        [f"{EmojisClash.ATTACK}\u3000{EmojisTownHall.get(att.attacker.town_hall)} vs {EmojisTownHall.get(att.defender.town_hall)}\u3000{EmojisClash.STAR} `{att.stars:^3}`\u3000{EmojisClash.DESTRUCTION} `{att.destruction:>3}%`"
                        for att in war_attacks]
                        )
                    defense_str = "\n".join(
                        [f"{EmojisClash.DEFENSE}\u3000{EmojisTownHall.get(defe.attacker.town_hall)} vs {EmojisTownHall.get(defe.defender.town_hall)}\u3000{EmojisClash.STAR} `{defe.stars:^3}`\u3000{EmojisClash.DESTRUCTION} `{defe.destruction:>3}%`"
                        for defe in war_defenses]
                        )
                    embed.add_field(
                        name=f"R{league_group.get_round_from_war(war)}: {war_member.clan.name} vs {war.get_opponent(war_member.clan.tag).name}",
                        value=f"{WarResult.emoji(war_member.clan.result)}\u3000{EmojisClash.ATTACK} `{len(war_member.attacks):^3}`\u3000{EmojisClash.UNUSEDATTACK} `{war_member.unused_attacks:^3}`\u3000{EmojisClash.DEFENSE} `{len(war_member.defenses):^3}`\n"
                            + (f"*War Ends <t:{war.end_time.int_timestamp}:R>.*\n" if war.start_time < pendulum.now() < war.end_time else "")
                            + (f"*War Starts <t:{war.start_time.int_timestamp}:R>.*\n" if war.start_time > pendulum.now() else "")
                            + (f"{attack_str}\n" if len(war_attacks) > 0 else "")
                            + (f"{defense_str}\n" if len(war_defenses) > 0 else "")
                            + "\u200b",
                        inline=False
                        )
        return [embed]