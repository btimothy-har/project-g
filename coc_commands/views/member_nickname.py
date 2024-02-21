import discord
import asyncio

from typing import *

from redbot.core import commands

from coc_main.api_client import BotClashClient
from coc_main.cog_coc_client import ClashOfClansClient

from coc_main.discord.member import aMember

from coc_main.utils.components import DefaultView, DiscordSelectMenu, clash_embed
from coc_main.utils.constants.ui_emojis import EmojisUI


bot_client = BotClashClient()

class MemberNicknameMenu(DefaultView):
    def __init__(self,
        context:Union[commands.Context,discord.Interaction],
        member:discord.Member,
        ephemeral:bool=False):

        self.ephemeral = ephemeral

        super().__init__(context,300)

        self.member = aMember(member.id,self.guild.id)
        self.for_self = self.user.id == self.member.user_id
    
    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    ####################################################################################################
    #####
    ##### OVERRIDE BUILT IN
    #####
    ####################################################################################################
    async def on_timeout(self):
        if self.for_self:
            embed = await clash_embed(
                context=self.ctx,
                message=f"Changing your nickname timed out. Please try again.",
                success=False
                )
        else:
            embed = await clash_embed(
                context=self.ctx,
                message=f"Changing {self.member.mention}'s nickname timed out. Please try again.",
                success=False
                )
        if isinstance(self.ctx,discord.Interaction):
            await self.ctx.edit_original_response(embed=embed,view=None)
        else:
            await self.message.edit(embed=embed,view=None,delete_after=60)
        self.stop_menu()
    
    ####################################################################################################
    #####
    ##### START
    #####
    ####################################################################################################  
    async def start(self):
        self.is_active = True
        await self.member.load()

        embed = await clash_embed(context=self.ctx,message=f"{EmojisUI.LOADING} Loading...")
        if isinstance(self.ctx,discord.Interaction):
            self.message = await self.ctx.followup.send(embed=embed,view=self,ephemeral=self.ephemeral,wait=True)
        else:
            self.message = await self.ctx.reply(embed=embed,view=self)

        if self.guild.id == 688449973553201335: #ARIX
            if len(self.member.member_accounts) > 1:
                await self._select_accounts()
            else:
                await self._change_nickname()
        else:
            if len(self.member.accounts) > 1:
                await self._select_accounts()
            else:
                await self._change_nickname()
    
    ##################################################
    ### STEP 1: SELECT ACCOUNT (IF MEMBER ACCOUNTS > 1)
    ##################################################
    async def _select_accounts(self):

        if self.guild.id == 688449973553201335: #ARIX
            player_accounts = [p async for p in bot_client.coc.get_players(self.member.member_tags)]

            dropdown_options = [discord.SelectOption(
                label=f"{account.name} | {account.tag}",
                value=account.tag,
                description=f"{account.clan_description}" + " | " + f"{account.alliance_rank}" + (f" ({account.home_clan.abbreviation})" if account.home_clan else ""),
                emoji=account.town_hall.emoji)
                for account in player_accounts[:25]
                ]
            dropdown_menu = DiscordSelectMenu(
                function=self._callback_account_select,
                options=dropdown_options,
                placeholder="Select an active member account.",
                min_values=1,
                max_values=1
                )
            self.add_item(dropdown_menu)

        else:
            player_accounts = [p async for p in bot_client.coc.get_players(self.member.account_tags)]

            dropdown_options = [discord.SelectOption(
                label=f"{account.name} | {account.tag}",
                value=account.tag,
                description=f"{account.clan_description}" + " | " + f"{account.alliance_rank}" + (f" ({account.home_clan.abbreviation})" if account.home_clan else ""),
                emoji=account.town_hall.emoji)
                for account in player_accounts[:25]
                ]
            dropdown_menu = DiscordSelectMenu(
                function=self._callback_account_select,
                options=dropdown_options,
                placeholder="Select one of your linked accounts.",
                min_values=1,
                max_values=1
                )
            self.add_item(dropdown_menu)

        if self.for_self:
            embed = await clash_embed(
                context=self.ctx,
                message=f"**Please select an account to use as your new nickname.**",
                thumbnail=self.member.display_avatar
                )
        else:
            embed = await clash_embed(
                context=self.ctx,
                message=f"**Please select an account to use as the new nickname for {self.member.mention}.**",
                thumbnail=self.member.display_avatar
                )
        for account in player_accounts[:25]:
            embed.add_field(
                name=f"**{account.name} ({account.tag})**",
                value=f"{account.short_description}",
                inline=False
                )
        if isinstance(self.ctx,discord.Interaction):
            await self.ctx.edit_original_response(embed=embed,view=self)
        else:
            await self.message.edit(embed=embed,view=self)
    
    async def _callback_account_select(self,interaction:discord.Interaction,menu:DiscordSelectMenu):
        await interaction.response.defer()
        self.clear_items()
        embed = await clash_embed(
            context=self.ctx,
            message=f"{EmojisUI.LOADING} Please wait..."
            )
        await interaction.edit_original_response(embed=embed,view=None)
        await self.member.set_default_account(menu.values[0])
        await self._change_nickname()

    ##################################################
    ### STEP 2: CHANGE NICKNAME
    ##################################################
    async def _change_nickname(self):
        new_nickname = await self.member.get_nickname()

        try:
            await self.member.discord_member.edit(nick=new_nickname)
        except discord.Forbidden:
            if self.for_self:
                result_text = f"I don't seem to have permissions to change your nickname."
            else:
                result_text = f"I don't seem to have permissions to change {self.member.mention}'s nickname."
            embed = await clash_embed(
                context=self.ctx,
                message=f"{EmojisUI.TASK_WARNING} {result_text}",
                success=False,
                thumbnail=self.member.display_avatar
                )
            self.stop_menu()
            if isinstance(self.ctx,discord.Interaction):
                await self.ctx.edit_original_response(embed=embed,view=None)
            else:
                await self.message.edit(embed=embed,view=None)
            return
        
        else:
            if self.for_self:
                result_text = f"Your nickname has been changed to **{new_nickname}**."
            else:
                result_text = f"{self.member.mention}'s nickname has been changed to **{new_nickname}**."

            embed = await clash_embed(
                context=self.ctx,
                message=f"{EmojisUI.TASK_CHECK} {result_text}",
                success=True,
                thumbnail=self.member.display_avatar
                )
            self.stop_menu()
            if isinstance(self.ctx,discord.Interaction):
                await self.ctx.edit_original_response(embed=embed,view=None)
            else:
                await self.message.edit(embed=embed,view=None)
            return