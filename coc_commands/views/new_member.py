import discord
import asyncio

from typing import *

from redbot.core import commands
from redbot.core.utils import AsyncIter

from coc_main.api_client import BotClashClient, CacheNotReady, NoClansRegistered
from coc_main.cog_coc_client import ClashOfClansClient, aPlayer, aClan

from coc_main.discord.member import aMember
from coc_main.discord.guild import aGuild, ClanGuildLink

from coc_main.utils.components import DiscordButton, DefaultView, MultipleChoiceSelectionMenu, DiscordSelectMenu, clash_embed
from coc_main.utils.constants.ui_emojis import EmojisUI

bot_client = BotClashClient()

class NewMember():
    def __init__(self,account:aPlayer,home_clan:Optional[aClan]=None):
        self.account = account
        self.home_clan = home_clan

class NewMemberMenu(DefaultView):
    def __init__(self,
        context:Union[commands.Context,discord.Interaction],
        member:discord.Member,
        silent_mode:bool=False):

        self.member = aMember(member.id,member.guild.id)
        self.silent_mode = silent_mode

        self.accounts = []
        self.menu_summary = []
        self.added_count = 0

        self.stop_button = DiscordButton(
            function=self._callback_close_button,
            label="Cancel",
            emoji=EmojisUI.EXIT,
            style=discord.ButtonStyle.danger)
 
        super().__init__(context)
    
    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    ####################################################################################################
    #####
    ##### OVERRIDE BUILT IN METHODS
    #####
    ####################################################################################################
    async def on_timeout(self):
        embed = await clash_embed(
            context=self.ctx,
            message=f"Adding {self.member.mention} timed out. Please try again.",
            success=False
            )
        await self.message.edit(embed=embed,view=None)
        self.stop_menu()
    
    ####################################################################################################
    #####
    ##### START / STOP
    #####
    ####################################################################################################
    async def start(self):
        self.is_active = True
        main_embed = await self.new_member_embed()

        if isinstance(self.ctx,discord.Interaction):
            await self.ctx.edit_original_response(embed=main_embed,view=self)
            self.message = await self.ctx.original_response()
        else:
            self.message = await self.ctx.reply(embed=main_embed,view=self)
        
        await self.member.refresh_clash_link(force=True)

        try:
            if len(self.member.account_tags) == 0:
                await self._manual_tag_entry()
            else:
                await self._get_accounts_select()
        except CacheNotReady:
            await self._manual_tag_entry()
    
    async def _callback_close_button(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        close_embed = await clash_embed(
            context=self.ctx,
            message=f"Cancelled adding {self.member.mention}.",
            success=False
            )
        await interaction.edit_original_response(embed=close_embed,view=None)
        self.stop_menu()

    ####################################################################################################
    #####
    ##### STEP 1: GET USER ACCOUNTS
    #####
    ####################################################################################################
    async def _get_accounts_select(self):
        main_embed = await self.new_member_embed()

        player_accounts = await self.client.fetch_many_players(*[p.tag for p in self.member.accounts])
        player_accounts.sort(key=lambda x:(x.town_hall.level,x.hero_strength,x.exp_level,x.clean_name),reverse=True)

        self.clear_items()
        
        if len(player_accounts) > 0:
            dropdown_list = [discord.SelectOption(
                label=f"{account.name} | {account.tag}",
                value=f"{account.tag}",
                description=f"{account.clan_description}" + " | " + f"{account.alliance_rank}" + (f" ({account.home_clan.abbreviation})" if account.home_clan else ""),
                emoji=f"{account.town_hall.emoji}")
                for account in player_accounts[:25]
                ]
            account_select_menu = DiscordSelectMenu(
                function=self._callback_menu_tags,
                options=dropdown_list,
                placeholder="Select one or more account(s)...",
                min_values=1,
                max_values=len(dropdown_list),
                )
            self.add_item(account_select_menu)

        enter_tags_button = DiscordButton(
            function=self._callback_manual_tag_entry,
            label="Enter Tags Manually")
        
        self.add_item(enter_tags_button)
        self.add_item(self.stop_button)
            
        ask_embed = await clash_embed(
            context=self.ctx,
            message=f"Select one or more account(s) from the dropdown below."
                + f"\n\n*If the account you wish to add is not listed, click on the 'Enter Tags Manually' button.*",
            show_author=False,
            )
        await self.message.edit(embeds=[main_embed,ask_embed],view=self)        
    
    ##################################################
    ### CALLBACK: SELECT TAGS FROM LIST
    ##################################################
    async def _callback_menu_tags(self,interaction:discord.Interaction,menu:DiscordSelectMenu):
        await interaction.response.defer()
        self.clear_items()

        embed = await clash_embed(
            context=self.ctx,
            title=f"**Member Add: {self.member.name}**",
            message=f"{EmojisUI.LOADING} Please wait...",
            thumbnail=self.member.display_avatar)
        await interaction.edit_original_response(embed=embed,view=self)
        await self._collate_player_accounts(menu.values)
    
    ##################################################
    ### CALLBACK: MANUAL ENTRY BUTTON
    ##################################################
    async def _callback_manual_tag_entry(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        await self._manual_tag_entry(interaction)
    
    ##################################################
    ### MANUAL ENTRY TASK
    ##################################################
    async def _manual_tag_entry(self,interaction:Optional[discord.Interaction]=None):
        def response_check(m):
            return m.author.id == self.user.id and m.channel.id == self.channel.id
        
        main_embed = await self.new_member_embed()
        ask_embed = await clash_embed(
            context=self.ctx,
            message=f"**Please send the Clash Player Tags for {self.member.mention}.**"
                + f"\n\nSeparate multiple tags with a space in between. To stop/cancel, send `cancel`.",
            show_author=False,
            )
        self.clear_items()

        if interaction:
            await interaction.edit_original_response(embeds=[main_embed,ask_embed],view=self)
        else:
            self.message = await self.message.edit(embeds=[main_embed,ask_embed],view=self)
        
        try:
            self.waiting_for = True
            tags_abbreviation = await self.bot.wait_for("message",timeout=180,check=response_check)
        except asyncio.TimeoutError:
            return await self.on_timeout()
        else:
            self.waiting_for = False
            await tags_abbreviation.delete()
            if tags_abbreviation.content.lower() == "cancel":
                embed = await clash_embed(
                    context=self.ctx,
                    message=f"Adding {self.member.mention} was cancelled.",
                    success=False
                    )
                if interaction:
                    await interaction.edit_original_response(embed=embed,view=self)
                else:
                    await self.message.edit(embed=embed,view=self)
                return self.stop_menu()

            embed = await clash_embed(
                context=self.ctx,
                message=f"{EmojisUI.LOADING} Please wait...",
                )
            if interaction:
                await interaction.edit_original_response(embed=embed,view=self)
            else:
                await self.message.edit(embed=embed,view=self)
            await self._collate_player_accounts(tags_abbreviation.content.split())

    ##################################################
    ### COLLATE ACCOUNTS
    ##################################################    
    async def _collate_player_accounts(self,tags:List[str]):
        self.accounts = await self.client.fetch_many_players(*tags)
        self.accounts.sort(key=lambda x:(x.town_hall.level,x.hero_strength,x.exp_level,x.clean_name),reverse=True)
        await self._get_home_clans()
    
    ####################################################################################################
    #####
    ##### STEP 2: ASSIGN HOME CLAN FOR EACH ACCOUNT
    #####
    ####################################################################################################
    async def _get_home_clans(self):
        self.clear_items()

        if len(self.accounts) == 0:
            embed = await clash_embed(
                context=self.ctx,
                message=f"There were no valid accounts found/selected for **{self.member.mention}**. Please try again.",
                thumbnail=self.member.display_avatar,
                success=False)
            await self.message.edit(embed=embed,view=None,delete_after=60)
            return self.stop_menu()
    
        async for account in AsyncIter(self.accounts):
            await self._select_home_clan(account)    
        await self._finish_add()

    async def _select_home_clan(self,account:aPlayer):        
        linked_clans = await ClanGuildLink.get_for_guild(self.guild.id)
        guild_clans = await asyncio.gather(*(self.client.fetch_clan(c.tag) for c in linked_clans))

        alliance_clans = sorted([c for c in guild_clans if c.is_alliance_clan],key=lambda x:(x.level,x.max_recruitment_level,x.capital_hall),reverse=True)
        if len(alliance_clans) == 0:
            raise NoClansRegistered()

        player_notes = ""
        if account.discord_user and account.discord_user != self.member.user_id:
            player_notes += f"\n- This account is currently linked to <@{account.discord_user}>."                    
        if account.is_member:
            player_notes += f"\n- This account is already a **{account.alliance_rank} in {account.home_clan.title}**."

        main_embed = await self.new_member_embed()
        homeclan_embed = await clash_embed(
            context=self.ctx,
            title=f"**Select a Home Clan for {account}.**",
            message=player_notes,
            show_author=False,
            )
        home_clan_select_view = MultipleChoiceSelectionMenu(context=self.ctx,timeout=120,timeout_function=self.on_timeout)
        for clan in alliance_clans:
            home_clan_select_view.add_list_item(reference=clan.tag,label=clan.clean_name[:80],emoji=clan.emoji)            
            homeclan_embed.add_field(
                name=f"{clan.title}",
                value=f"Members: {clan.alliance_member_count}\u3000Recruiting: {clan.recruitment_level_emojis}",
                inline=False
                )
        await self.message.edit(embeds=[main_embed,homeclan_embed],view=home_clan_select_view)

        select_timed_out = await home_clan_select_view.wait()
        if select_timed_out or not home_clan_select_view.return_value:
            self.menu_summary.append(NewMember(account))
            return
        
        else:
            home_clan = [clan for clan in alliance_clans if clan.tag == home_clan_select_view.return_value][0]
            await account.new_member(self.member.user_id,home_clan)
            self.menu_summary.append(NewMember(account,home_clan))
            self.added_count += 1        
    
    ##################################################
    ### STEP 3: WRAP UP
    ##################################################
    async def _finish_add(self):
        self.stop_menu()

        if self.added_count == 0:
            embed = await clash_embed(
                context=self.ctx,
                message=f"No accounts were added for **{self.member.mention}**.",
                thumbnail=self.member.display_avatar
                )
            return await self.message.edit(embed=embed,view=None)
        
        report_output = ""
        for action in self.menu_summary:
            if action.home_clan:
                report_output += f"{EmojisUI.TASK_CHECK} **{action.account.title}** added to {action.home_clan.title}.\n"
            else:
                report_output += f"{EmojisUI.TASK_WARNING} **{action.account.title}** not added.\n"
        
        if self.member.discord_member:
            report_output += "\n\u200b"
            roles_added, roles_removed = await self.member.sync_clan_roles(self.ctx)

            for role in roles_added:
                report_output += f"{EmojisUI.TASK_CHECK} Added {role.mention}.\n"
            for role in roles_removed:
                report_output += f"{EmojisUI.TASK_CHECK} Removed {role.mention}.\n"
            
            try:
                new_nickname = await self.member.get_nickname()
                await self.member.discord_member.edit(nick=new_nickname)
            except discord.Forbidden:
                report_output += f"{EmojisUI.TASK_WARNING} Could not change nickname. Please edit the user's nickname manually.\n"
            else:
                report_output += f"{EmojisUI.TASK_CHECK} Changed nickname to: {new_nickname}.\n"
            
            if not self.silent_mode and self.guild.id == 688449973553201335:
                sent_welcome = await self.send_welcome_dm()
                if sent_welcome:
                    await self.channel.send(f"**Welcome to AriX, {self.member.mention}**!"
                        + "\n\nI've sent you some information and instructions in your DMs. Please review them ASAP.")
                    report_output += f"{EmojisUI.TASK_CHECK} Welcome DM sent.\n"
                else:
                    report_output += f"{EmojisUI.TASK_WARNING} Could not send Welcome DM, please check the user's DM settings.\n"
        
        embed = await clash_embed(
            context=self.ctx,
            title=f"**Successfully Added {self.member.name}**",
            message=report_output,
            thumbnail=self.member.display_avatar
            )
        return await self.message.edit(embed=embed,view=None)
    
    ##################################################
    ### HELPER FUNCTIONS
    ##################################################
    async def new_member_embed(self):
        embed = await clash_embed(
            context=self.ctx,
            title=f"**Member Add: {self.member.name}**",
            message=f"Account Created: <t:{self.member.created_at.int_timestamp}:R>\n"
                + f"Joined {self.guild.name}: <t:{self.member.joined_at.int_timestamp}:R>"
                + f"\n\u200b",
            thumbnail=self.member.display_avatar)
        
        self.accounts.sort(key=lambda x:(x.town_hall.level,x.exp_level), reverse=True)        
        for account in self.accounts:
            status_message = ""
            account_action = self.get_summary_action(account.tag)
            if account_action:
                if account_action.home_clan:
                    status_message = f"{EmojisUI.TASK_CHECK} Added to {account_action.home_clan.title}."
                else:
                    status_message = f"{EmojisUI.TASK_WARNING} Not added."
            else:
                status_message = f"{account.member_description if account.is_member else ''}"

            embed.add_field(
                name=f"{account}",
                value=f"{status_message}\n{account.long_description}\n\u200b",
                inline=False
                )        
        return embed

    def get_summary_action(self,tag:str):
        for action in self.menu_summary:
            if action.account.tag == tag:
                return action
        return None

    async def send_welcome_dm(self): 
        intro_embed = await clash_embed(
            context=self.ctx,
            title="Congratulations! You're an AriX Member!",
            message=f"We're really happy to have you with us. We *strongly encourage* you to review the information below, so you can understand everything that goes on in AriX."
                + f"\n\nThe **AriX Alliance** is made up of 5 active clans:"
                + f"\n- <:logoao9:1037988555592577054> ArmyOf9YearOlds (AO9)"
                + f"\n- <:logopr:1037988553390559252> Phoenix Reborn (PR)"
                + f"\n- <:logopa:1037988554778890270> Project AriX (PA)"
                + f"\n- <:logoas:1037988552052572171> Assassins (AS)"
                + f"\n\nWe also have 3 event-only clans:"
                + f"\n- <:logodop:1037988559090614293> DawnOfPhoenix (DOP)"
                + f"\n- <:logoao2:1037988557685530654> ArmyOf2YearOlds (AO2)"
                + f"\n- <:logodon:1037988556502740992> Don (DON)"
                + f"\n\u200b",
            show_author=False)

        intro_embed.add_field(
            name="**Getting Started in AriX**",
            value="We strongly encourage you to check out the following channels to get yourself set up in the community. If you have any questions, our Leaders will be around to assist."
                + f"\n\n> - Read <#973472492222046258> for info regarding the AriX Alliance Server"
                + f" \n> - Read <#970239273456500736> for info about our Hierarchy"
                + f"\n> - Read <#960096690394767380> for info about our War Rules"
                + f"\n> - Read <#998620795116986499> for info regarding our Raid Rules"
                + f"\n> - Customize your AriX Profile and Experience by clicking on **Channels & Roles** at the top of the channel list"
                + f"\n\u200b")
        try:
            await self.member.discord_member.send(embed=intro_embed)
            return True
        except:
            return False