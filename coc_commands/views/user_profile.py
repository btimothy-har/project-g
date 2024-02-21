import discord

from typing import *

from redbot.core import commands
from redbot.core.utils import AsyncIter

from coc_main.api_client import BotClashClient
from coc_main.cog_coc_client import ClashOfClansClient

from coc_main.discord.member import aMember
from coc_main.discord.add_delete_link import AddLinkMenu, DeleteLinkMenu

from coc_main.utils.components import DefaultView, DiscordButton, clash_embed
from coc_main.utils.constants.coc_constants import ClanRanks
from coc_main.utils.constants.ui_emojis import EmojisUI

bot_client = BotClashClient()

####################################################################################################
#####
##### VIEW MENU: USER PROFILE / LINKS
#####
####################################################################################################
class UserProfileMenu(DefaultView):
    def __init__(self,
        context:Union[commands.Context,discord.Interaction],
        member:Union[discord.User,discord.Member]):

        self.add_link_button = DiscordButton(
            function=self._add_link,
            label="Add",
            emoji=EmojisUI.ADD,
            style=discord.ButtonStyle.blurple
            )
        self.delete_link_button = DiscordButton(
            function=self._delete_link,
            label="Delete",
            emoji=EmojisUI.DELETE,
            style=discord.ButtonStyle.grey
            )
        super().__init__(context,timeout=300)

        self.member = aMember(member.id,self.guild.id)

        if self.user.id == self.member.user_id:
            self.add_item(self.add_link_button)
            self.add_item(self.delete_link_button)
    
    @classmethod
    def coc_client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")

    ##################################################
    ### OVERRIDE BUILT IN METHODS
    ##################################################
    async def on_timeout(self):
        await self.message.edit(view=None)
        self.stop_menu()
    
    ##################################################
    ### START / STOP
    ##################################################
    async def start(self):
        await self.member
        
        self.is_active = True
        embed = await UserProfileMenu.profile_embed(self.ctx,self.member)

        if isinstance(self.ctx,discord.Interaction):
            await self.ctx.edit_original_response(embeds=embed,view=self)
            self.message = await self.ctx.original_response()
        else:
            self.message = await self.ctx.reply(embeds=embed,view=self)
    
    ##################################################
    ### ADD LINK FUNCTIONS/CALLBACKS
    ##################################################
    async def _add_link(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer(ephemeral=True)
        add_link_view = AddLinkMenu(interaction,self.member)
        await add_link_view._start_add_link()

        await add_link_view.wait()
        await self.member.load()

        embed = await UserProfileMenu.profile_embed(self.ctx,self.member)
        await interaction.edit_original_response(embeds=embed,view=self)
    
    async def _delete_link(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer(ephemeral=True)
        delete_link_view = DeleteLinkMenu(interaction,self.member)
        await delete_link_view._start_delete_link()

        await delete_link_view.wait()
        await self.member.load()

        embed = await UserProfileMenu.profile_embed(self.ctx,self.member)
        await interaction.edit_original_response(embeds=embed,view=self)
    
    ##################################################
    ### HELPERS
    ##################################################
    @staticmethod
    async def profile_embed(ctx:Union[discord.Interaction,commands.Context],member:aMember):

        client = UserProfileMenu.coc_client()
        m_accounts = [p async for p in bot_client.coc.get_players(member.account_tags)]

        m_accounts.sort(
            key=lambda x:(ClanRanks.get_number(x.alliance_rank),x.town_hall_level,x.exp_level),
            reverse=True
            )
        
        global_member = await aMember(member.user_id)

        embed = await clash_embed(
            context=ctx,
            title=member.display_name,
            message=(f"{' '.join([c.emoji for c in global_member.home_clans])}\n\n" if len(global_member.home_clans) > 0 else "")
                + "\u200b",
            embed_color=next((r.color for r in sorted(member.discord_member.roles,key=lambda x:(x.position),reverse=True) if r.color.value), None),
            thumbnail=member.display_avatar
            )

        async for account in AsyncIter(m_accounts[:10]):
            embed.add_field(
                name=(f"{account.home_clan.emoji} " if account.is_member else "") + f"{account.town_hall.emote} **{account.name}**",
                value=f"{account.hero_description}\n[Player Link: {account.tag}]({account.share_link})\n\u200b",
                inline=False
                )
        # if len(member.accounts) > 10:
        #     embed_2 = await clash_embed(
        #         context=ctx,
        #         embed_color=next((r.color for r in sorted(member.discord_member.roles,key=lambda x:(x.position),reverse=True) if r.color.value), None),
        #         thumbnail=member.display_avatar,
        #         show_author=False,
        #         )
        #     async for account in AsyncIter(m_accounts[10:20]):
        #         embed_2.add_field(
        #             name=(f"{account.home_clan.emoji} " if account.is_member else "") + f"{account.town_hall.emote} **{account.name}**",
        #             value=f"{account.hero_description}\n[Player Link: {account.tag}]({account.share_link})\n\u200b",
        #             inline=False
        #             )
        #     return [embed,embed_2]
        return [embed]