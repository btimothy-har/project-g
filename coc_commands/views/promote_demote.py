import discord
import asyncio

from typing import *

from redbot.core import commands

from coc_main.api_client import BotClashClient
from coc_main.cog_coc_client import ClashOfClansClient
from coc_main.coc_objects.clans.player_clan import aPlayerClan

from coc_main.discord.member import aMember

from coc_main.utils.components import MultipleChoiceSelectionMenu, MenuConfirmation, clash_embed
from coc_main.utils.constants.coc_constants import ClanRanks
from coc_main.utils.constants.ui_emojis import EmojisUI

bot_client = BotClashClient()

###################################################################################################
#####
##### RANK HANDLER FOR PROMOTE / DEMOTE
##### **We don't have to sub-class this to ui.View as we don't have any child views here.**
#####
####################################################################################################
class MemberRankMenu():
    def __init__(self,
        context:commands.Context,
        member:discord.Member):

        self.rank_action = 0
        self.eligible_clans = []

        self.ctx = context
        if isinstance(context,commands.Context):
            self.bot = self.ctx.bot
            self.user = self.ctx.author
            self.channel = self.ctx.channel
            self.guild = self.ctx.guild
        elif isinstance(context,discord.Interaction):
            self.bot = self.ctx.client
            self.user = self.ctx.user
            self.channel = self.ctx.channel
            self.guild = self.ctx.guild
        self.message = None
        
        self.executor = aMember(self.user.id)
        self.member = aMember(member.id)
    
    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    ####################################################################################################
    #####
    ##### STARTING POINT: PROMOTE
    #####
    ####################################################################################################
    async def promote(self):
        await asyncio.gather(*[self.executor.load(),self.member.load()])

        self.rank_action = 1
        if len(self.member.home_clans) == 0:
            embed = await clash_embed(
                context=self.ctx,
                message=f"{self.member.mention} is not a member of any clans.",
                success=False
                )
            if isinstance(self.ctx,discord.Interaction):
                self.message = await self.ctx.original_response()
                await self.message.edit(embed=embed,view=None,delete_after=60)
            else:
                await self.ctx.reply(embed=embed,view=None,delete_after=60)
            return

        self.eligible_clans = [clan for clan in self.member.home_clans if self._predicate_is_eligible_clan(clan)]

        if len(self.eligible_clans) == 0:
            embed = await clash_embed(
                context=self.ctx,
                message=f"You don't seem to have permission to promote {self.member.mention} in any of their clans."
                    + f"\n\n> - Only Leaders or Co-Leaders of a Clan can promote elders/members."
                    + f"\n> - Leaders and Co-Leaders cannot be promoted further. Only the current Leader of a Clan can assign a new Leader.",
                success=False
                )
            if isinstance(self.ctx,discord.Interaction):
                self.message = await self.ctx.original_response()
                await self.message.edit(embed=embed,view=None,delete_after=60)
            else:
                await self.ctx.reply(embed=embed,view=None,delete_after=60)
            return

        embed = await clash_embed(context=self.ctx,message=f"{EmojisUI.LOADING} Loading...")
        if isinstance(self.ctx,discord.Interaction):
            await self.ctx.edit_original_response(embed=embed)
            self.message = await self.ctx.original_response()
        else:
            self.message = await self.ctx.reply(embed=embed)
        
        if len(self.eligible_clans) > 1:
            await self._select_clan_from_multiple()
        else:
            await self._confirm_single_clan()
    
    ####################################################################################################
    #####
    ##### STARTING POINT: DEMOTE
    #####
    ####################################################################################################
    async def demote(self):
        await asyncio.gather(*[self.executor.load(),self.member.load()])

        self.rank_action = -1
        if len(self.member.home_clans) == 0:
            embed = await clash_embed(
                context=self.ctx,
                message=f"{self.member.mention} is not a member of any clans.",
                success=False
                )
            if isinstance(self.ctx,discord.Interaction):
                self.message = await self.ctx.original_response()
                await self.message.edit(embed=embed,view=None,delete_after=60)
            else:
                await self.ctx.reply(embed=embed,view=None,delete_after=60)
            return

        self.eligible_clans = [clan for clan in self.member.home_clans if self._predicate_is_eligible_clan(clan)]

        if len(self.eligible_clans) == 0:
            embed = await clash_embed(
                context=self.ctx,
                message=f"You don't seem to have permission to demote {self.member.mention} in any of their clans."
                    + f"\n\n> - Only Leaders can demote Co-Leaders."
                    + f"\n> - Members cannot be demoted."
                    + f"\n> - Only the current Leader of a Clan can assign a new Leader.",
                success=False
                )
            if isinstance(self.ctx,discord.Interaction):
                self.message = await self.ctx.original_response()
                await self.message.edit(embed=embed,view=None,delete_after=60)
            else:
                await self.ctx.reply(embed=embed,view=None,delete_after=60)
            return

        embed = await clash_embed(context=self.ctx,message=f"{EmojisUI.LOADING} Loading...")
        if isinstance(self.ctx,discord.Interaction):
            await self.ctx.edit_original_response(embed=embed)
            self.message = await self.ctx.original_response()
        else:
            self.message = await self.ctx.reply(embed=embed)
        
        if len(self.eligible_clans) > 1:
            await self._select_clan_from_multiple()
        else:
            await self._confirm_single_clan()

    ####################################################################################################
    #####
    ##### SELECT CLAN IF MEMBER IS IN MULTIPLE CLANS
    #####
    ####################################################################################################
    async def _select_clan_from_multiple(self):
        embed = await clash_embed(
            context=self.ctx,
            message=f"**Select a Clan to __{self.rank_action_text}__ {self.member.mention} in.**\n\u200b",
            thumbnail=self.member.display_avatar
            )
        select_clan_view = MultipleChoiceSelectionMenu(context=self.ctx,timeout=120)
        for clan in self.eligible_clans:            
            select_clan_view.add_list_item(reference=clan.tag,label=clan.name,emoji=clan.emoji)
            embed.add_field(
                name=f"{clan.title}",
                value=f"Current Rank: {self.get_current_rank(clan)}"
                    + "\n> " + '\n> '.join([f"{a.title}" for a in self.member.member_accounts if a.home_clan.tag == clan.tag])
                    + "\n\u200b",
                inline=False
                )
        
        await self.message.edit(embed=embed,view=select_clan_view)
        select_timed_out = await select_clan_view.wait()
        if select_clan_view.return_value:
            await self._apply_rank_changes(select_clan_view.return_value)
        else:
            embed = await clash_embed(
                context=self.ctx,
                message=f"Did not receive a Clan selection. Task cancelled.",
                success=False,
                )
            return await self.message.edit(embed=embed,view=None,delete_after=60)
    
    ####################################################################################################
    #####
    ##### CONFIRMATION FOR SINGLE CLAN
    #####
    ####################################################################################################    
    async def _confirm_single_clan(self):
        target_clan = self.eligible_clans[0]
        embed = await clash_embed(
            context=self.ctx,
            message=f"**Please confirm you want to __{self.rank_action_text}__ {self.member.mention} in {target_clan.title}.**"
                + f"\n\nCurrent Rank: {self.get_current_rank(target_clan)}"
                + "\n> " + '\n> '.join([f"{a.title}" for a in self.member.member_accounts if a.home_clan.tag == target_clan.tag]),
            thumbnail=self.member.display_avatar,
            )
        confirmation_view = MenuConfirmation(self.ctx)
        await self.message.edit(embed=embed,view=confirmation_view)
        confirmation_timed_out = await confirmation_view.wait()

        if confirmation_view.confirmation:
            await self._apply_rank_changes(target_clan.tag)
        elif confirmation_timed_out:
            embed = await clash_embed(
                context=self.ctx,
                message=f"Did not receive confirmation. Task cancelled.",
                success=False,
                )
            return await self.message.edit(embed=embed,view=None,delete_after=60)
        else:
            embed = await clash_embed(
                context=self.ctx,
                message=f"Task cancelled.",
                success=False,
                )
            return await self.message.edit(embed=embed,view=None,delete_after=60)

    ####################################################################################################
    #####
    ##### COMPLETE RANK CHANGE
    #####
    ####################################################################################################
    async def _apply_rank_changes(self,target_clan:str):
        report_output = ""

        clan = await self.client.fetch_clan(target_clan)
        current_rank_int = ClanRanks.get_number(self.get_current_rank(clan))
        new_rank = ClanRanks.get_rank(current_rank_int + self.rank_action)

        if new_rank:
            if new_rank == "Member":
                await clan.remove_coleader(self.member.user_id)
                await clan.remove_elder(self.member.user_id)
            
            if new_rank == "Elder":
                await clan.new_elder(self.member.user_id)
            
            if new_rank == "Co-Leader":
                await clan.new_coleader(self.member.user_id)

            report_output += f"{EmojisUI.TASK_CHECK} {self.member.mention} is now a **{new_rank}** in {clan.title}.\n"

            self.member = await aMember(self.member.user_id,self.member.guild_id)
            roles_added, roles_removed = await self.member.sync_clan_roles(self.ctx,force=True)
            
            for role in roles_added:
                report_output += f"{EmojisUI.TASK_CHECK} Added {role.mention}.\n"
            for role in roles_removed:
                report_output += f"{EmojisUI.TASK_CHECK} Removed {role.mention}.\n"
            
            embed = await clash_embed(
                context=self.ctx,
                message=report_output,
                thumbnail=self.member.display_avatar
                )
            return await self.message.edit(embed=embed,view=None)
        
        else:
            embed = await clash_embed(
                context=self.ctx,
                message=f"Could not {self.rank_action_text} {self.member.mention} in {clan.title}.",
                success=False,
                )
            return await self.message.edit(embed=embed,view=None)

    ##################################################
    ### HELPERS
    ##################################################
    def _predicate_is_eligible_clan(self,clan:aPlayerClan):
        if self.member.user_id == clan.leader:
            return False
        elif self.member.user_id in clan.coleaders:
            if self.rank_action == 1:
                return False
            elif self.executor.user_id == clan.leader:
                return True
            elif self.executor.user_id in self.bot.owner_ids:
                return True
            else:
                return False
        elif self.member.user_id in clan.elders:
            if self.executor.user_id == clan.leader:
                return True
            elif self.executor.user_id in clan.coleaders:
                return True
            elif self.executor.user_id in self.bot.owner_ids:
                return True
            else:
                return False
        else:
            if self.rank_action == -1:
                return False
            elif self.executor.user_id == clan.leader:
                return True
            elif self.executor.user_id in clan.coleaders:
                return True
            elif self.executor.user_id in self.bot.owner_ids:
                return True
            else:
                return False
    
    def get_current_rank(self,clan:aPlayerClan):
        if self.member.user_id in clan.coleaders:
            current_rank = "Co-Leader"
        elif self.member.user_id in clan.elders:
            current_rank = "Elder"
        else:
            current_rank = "Member"
        return current_rank
    
    @property
    def rank_action_text(self):
        if self.rank_action == 1:
            return "promote"
        if self.rank_action == -1:
            return "demote"