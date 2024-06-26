import discord

from typing import *
from redbot.core import commands
from redbot.core.utils import AsyncIter
from redbot.core.utils import chat_formatting as chat

from coc_main.coc_objects.players.player import aPlayer
from coc_main.discord.member import aMember

from coc_main.utils.components import DefaultView, DiscordButton, DiscordSelectMenu, MenuConfirmation, clash_embed
from coc_main.utils.constants.ui_emojis import EmojisUI

class RemoveMemberMenu(DefaultView):
    def __init__(self,
        context:Union[commands.Context,discord.Interaction],
        member:Optional[Union[discord.Member,int]]=None,
        account:Optional[aPlayer]=None):

        self.member = None
        self.remove_accounts = []

        self.stop_button = DiscordButton(
            function=self._callback_close,
            label="Cancel",
            emoji=EmojisUI.EXIT,
            style=discord.ButtonStyle.danger)
 
        super().__init__(context)

        if isinstance(member,discord.Member):
            self.member = aMember(member.id)
        elif isinstance(member,int):
            self.member = aMember(member)
        if account:
            self.remove_accounts.append(account)
    
    ####################################################################################################
    #####
    ##### START / STOP
    #####
    ####################################################################################################
    async def start(self):
        if isinstance(self.ctx,discord.Interaction) and (self.member == None and len(self.remove_accounts) == 0):
            no_input_embed = await clash_embed(
                context=self.ctx,
                message=f"You must provide one of the following: a Discord User, a Discord User ID, or a Clash Player Tag.",
                success=False
                )
            await self.ctx.followup.send(embed=no_input_embed,ephemeral=True)
            return self.stop_menu()
        
        self.is_active = True

        embed = await clash_embed(context=self.ctx,message=f"{EmojisUI.LOADING} Loading...")
        if isinstance(self.ctx,discord.Interaction):
            await self.ctx.edit_original_response(embed=embed,view=self)
            self.message = await self.ctx.original_response()
        else:
            self.message = await self.ctx.reply(embed=embed,view=self)

        if self.member:
            await self.member.load()
            #If Discord User provided, use select menu.
            await self._remove_accounts_by_select()
        else:
            await self._remove_accounts_confirmation()
    
    async def _callback_close(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        close_embed = await clash_embed(
            context=self.ctx,
            message=f"Remove member operation cancelled.",
            success=False
            )
        await interaction.edit_original_response(embed=close_embed,view=None)
        self.stop_menu()
    
    ####################################################################################################
    #####
    ##### SELECT MENU
    ##### *Used when Discord User is provided
    ####################################################################################################
    
    ##################################################
    ### IF DISCORD USER PROVIDED, USE SELECT MENU
    ##################################################
    async def _remove_accounts_by_select(self):
        member_accounts = [p async for p in self.coc_client.get_players(self.member.member_tags)]
        
        if len(member_accounts) == 0:
            embed = await clash_embed(
                context=self.ctx,
                message=f"I did not find any existing member accounts for {self.member.mention}. Please check your input.",
                thumbnail=self.member.display_avatar,
                success=False)
            self.stop_menu()
            return await self.message.edit(embed=embed,view=None)
        
        dropdown_options = [discord.SelectOption(
            label=f"{account.clean_name}" + " | " + f"{account.tag}",
            value=account.tag,
            description=f"{account.clan_description}" + " | " + f"{account.alliance_rank}" + (f" ({account.home_clan.abbreviation})" if account.home_clan else ""),
            emoji=account.town_hall.emoji)
            for account in member_accounts
            ]
        dropdown_menu = DiscordSelectMenu(
            function=self._callback_account_select,
            options=dropdown_options,
            placeholder="Select one or more account(s)...",
            min_values=1,
            max_values=len(dropdown_options)
            )
        self.add_item(dropdown_menu)
        self.add_item(self.stop_button)
        
        embed = await clash_embed(
            context=self.ctx,
            title=f"**Remove Member: {self.member.name}**",
            message=f"Please select one or more member accounts to remove.\n\u200b",
            thumbnail=self.member.display_avatar)
        
        for account in member_accounts:
            embed.add_field(
                name=f"{account}",
                value=f"{account.member_description}\n{account.long_description}\n\u200b",
                inline=False
                )        
        await self.message.edit(embed=embed,view=self)
    
    ##################################################
    ### CALLBACK FOR SELECT MENU
    ##################################################
    async def _callback_account_select(self,interaction:discord.Interaction,menu:DiscordSelectMenu):
        await interaction.response.defer()
        self.clear_items()
        embed = await clash_embed(
            context=self.ctx,
            message=f"{EmojisUI.LOADING} Please wait..."
            )
        await interaction.edit_original_response(embed=embed,view=self)

        self.remove_accounts.extend([p async for p in self.coc_client.get_players(menu.values)])  
        await self._remove_accounts_process()
    
    ####################################################################################################
    #####
    ##### CONFIRM REMOVE
    ##### 
    ####################################################################################################
    async def _remove_accounts_confirmation(self):
        if len(self.remove_accounts) == 0:
            embed = await clash_embed(
                context=self.ctx,
                message=f"There were no valid accounts found/selected to be removed. Please try again.",
                success=False)
            self.stop_menu()
            return await self.message.edit(embed=embed,view=None)

        embed = await clash_embed(
            context=self.ctx,
            title=f"**Remove Member**",
            message=f"Please confirm you would like to remove member status from the below accounts:\n\u200b")

        for account in self.remove_accounts:
            embed.add_field(
                name=f"{account}",
                value=f"{account.member_description}\n{account.long_description}\n\u200b",
                inline=False
                )
        confirmation_view = MenuConfirmation(self.ctx)
        await self.message.edit(embed=embed,view=confirmation_view)

        confirmation_timed_out = await confirmation_view.wait()
        if confirmation_timed_out:
            return await self.on_timeout()
        elif confirmation_view.confirmation:
            await self._remove_accounts_process()
        else:
            embed = await clash_embed(
                context=self.ctx,
                message=f"Remove member operation cancelled.",
                success=False
                )
            self.stop_menu()
            return await self.message.edit(embed=embed,view=None,delete_after=60)
    
    ##################################################
    ### REMOVE ACCOUNTS
    ##################################################
    async def _remove_accounts_process(self):
        report_output = ""
        accounts_removed_list = []
        discord_users = []

        rem_accounts = AsyncIter(self.remove_accounts)
        async for player in rem_accounts:
            await player.remove_member()
            accounts_removed_list.append(f"**{player.title}**")

            if player.discord_user not in discord_users:
                discord_users.append(player.discord_user)
        
        report_output += f"{EmojisUI.TASK_CHECK} Accounts Removed: {chat.humanize_list(accounts_removed_list)}.\n"
    
        u_iter = AsyncIter(discord_users)
        async for user_id in u_iter:
            
            roles_added_output = f""
            roles_removed_output = f""

            try:
                member = await aMember(user_id,self.guild.id)
                roles_added, roles_removed = await member.sync_clan_roles(self.ctx,force=True)
            except:
                report_output += f"\nCould not change {member.mention}'s Roles.\n"
            else:
                for role in roles_added:
                    roles_added_output += f"{role.mention}, "
                for role in roles_removed:
                    roles_removed_output += f"{role.mention}, "

                report_output += f"\nRoles Added for {member.mention}: {roles_added_output}"
                report_output += f"\nRoles Removed for {member.mention}: {roles_removed_output}"

            try:
                new_nickname = await member.get_nickname()
                await member.discord_member.edit(nick=new_nickname)
            except:
                report_output += f"\nCould not change {member.mention}'s Nickname.\n"
            else:
                report_output += f"\nChanged {member.mention}'s Nickname to {new_nickname}.\n"
        
        embed = await clash_embed(
            context=self.ctx,
            title=f"**Remove Member Task**",
            message=report_output)
        self.stop_menu()
        return await self.message.edit(embed=embed,view=None)