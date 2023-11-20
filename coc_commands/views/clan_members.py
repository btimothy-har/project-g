import asyncio
import discord
import re

from typing import *

from redbot.core import commands
from redbot.core.utils import AsyncIter

from coc_main.api_client import BotClashClient
from coc_main.cog_coc_client import ClashOfClansClient, aClan, aPlayer

from coc_main.utils.components import clash_embed, handle_command_error, MenuPaginator, DiscordButton, DiscordSelectMenu, DiscordChannelSelect, DefaultView

from coc_main.utils.constants.coc_emojis import EmojisTownHall, EmojisClash
from coc_main.utils.constants.ui_emojis import EmojisUI
from coc_main.exceptions import ClashAPIError
from coc_main.utils.utils import chunks

bot_client = BotClashClient()

class ClanMembersMenu(MenuPaginator):
    def __init__(self,
        context:Union[commands.Context,discord.Interaction],
        clan:aClan):

        self.is_active = False
        self.waiting_for = False

        self.clan = clan
        self.members_in_clan = []
        self.members_not_in_clan = []
        self.all_clan_members = []

        super().__init__(context,[])
    
    @property
    def coc_client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")

    ##################################################
    ### OVERRIDE BUILT IN METHODS
    ##################################################
    async def interaction_check(self, interaction:discord.Interaction):
        if not self.is_active:
            await interaction.response.send_message(
                content="This menu is not active.", ephemeral=True,view=None
                )
            return False
        if self.waiting_for and interaction.user.id == self.user.id:
            await interaction.response.send_message(
                content="Please respond first!", ephemeral=True,view=None
                )
            return False
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                content="This doesn't belong to you!", ephemeral=True,view=None
                )
            return False
        return True
    
    async def on_timeout(self):
        self.stop_menu()
        await self.message.edit(view=None)
        
    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        err = await handle_command_error(error,interaction,self.message)
        if err:
            return
        self.stop_menu()
    
    ##################################################
    ### START / STOP
    ##################################################
    def stop_menu(self):
        self.is_active = False
        self.waiting_for = False
        self.stop()

    async def start(self):
        registered_members = []
        if self.clan.is_alliance_clan and self.clan.alliance_member_count > 0:
            registered_members = await self.coc_client.fetch_many_players(*self.clan.alliance_members)

        self.members_in_clan = await self.coc_client.fetch_many_players(*[member.tag for member in self.clan.members])
        self.members_not_in_clan = [member for member in registered_members if member not in self.members_in_clan]
        self.all_clan_members = self.members_in_clan + self.members_not_in_clan
        self.is_active = True

        await self._set_discordlinks_content()
        kwargs = self.get_content()
        if isinstance(self.ctx,discord.Interaction):
            await self.ctx.edit_original_response(**kwargs)
            self.message = await self.ctx.original_response()
        else:
            self.message = await self.ctx.reply(**kwargs)
    
    ##################################################
    ### CALLBACKS
    ##################################################
    async def _callback_discord_links(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        await self._set_discordlinks_content()
        kwargs = self.get_content()
        await interaction.edit_original_response(**kwargs)

    async def _callback_member_ranks(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        await self._set_member_ranks_content()
        kwargs = self.get_content()
        await interaction.edit_original_response(**kwargs)
    
    async def _callback_war_status(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        await self._set_warstatus_content()
        kwargs = self.get_content()
        await interaction.edit_original_response(**kwargs)
    
    ##################################################
    ### CONTENT HELPERS
    ##################################################
    def _build_menu_items(self):
        self.previous_page_button = DiscordButton(function=self.to_previous_page,style=discord.ButtonStyle.gray,emoji=EmojisUI.GREEN_PREVIOUS)
        self.next_page_button = DiscordButton(function=self.to_next_page,style=discord.ButtonStyle.gray,emoji=EmojisUI.GREEN_NEXT)
        self.discord_links_button = DiscordButton(function=self._callback_discord_links,label="Discord Links",emoji=EmojisUI.DISCORD)
        self.member_ranks_button = DiscordButton(function=self._callback_member_ranks,label="Clan Ranks",emoji=EmojisClash.CLAN)
        self.war_status_button = DiscordButton(function=self._callback_war_status,label="War Status",emoji=EmojisClash.CLANWAR)

    async def _set_discordlinks_content(self):
        def get_embed_text(lst:list):
            text = "\n".join([
                (f"{EmojisUI.LOGOUT}" if getattr(member.home_clan,'tag',None) == getattr(self.clan,'tag',None) and getattr(member.clan,'tag',None) != getattr(self.clan,'tag',None) else (f"{EmojisUI.YES}" if getattr(member.home_clan,'tag',None) == getattr(self.clan,'tag',None) else f"{EmojisUI.SPACER}"))
                + f"{EmojisTownHall.get(member.town_hall.level)}"
                + f"`{re.sub('[_*/]','',member.name)[:15]:<15}`\u3000" + f"`{'':^1}{member.tag:<11}`\u3000"
                + (f"`{'':^1}{getattr(self.ctx.guild.get_member(member.discord_user),'display_name','User Not Found')[:14]:<14}`" if member.discord_user else f"`{' Not Linked':<15}`")            
                for member in lst])
            return text

        embeds = []
        chunked_members = list(chunks(self.all_clan_members,25))

        for i, members_chunk in enumerate(chunked_members):
            startend = f"Showing members {i*25+1} to {(i*25+1)+len(members_chunk)-1}. (Total: {len(self.all_clan_members)})"

            header_text = f"**Member Discord Links**\nIn Clan: {self.clan.member_count}\u3000"
            header_text += f"Registered: {self.clan.alliance_member_count}" if self.clan.is_alliance_clan else ""
            header_text += "\n\n"
            header_text += f"{EmojisUI.YES}: this member has been registered to the Clan.\n"
            header_text += f"{EmojisUI.LOGOUT}: a registered member who is not in the in-game Clan.\n\n"
                
            embed = await clash_embed(
                context=self.ctx,
                title=(f"{self.clan.title}" if i == 0 else ""),
                message=header_text + get_embed_text(members_chunk) + f"\n\n**{startend}**",
                thumbnail=self.clan.badge,
                )
            embeds.append(embed)
        self.paginate_options = embeds
        self.page_index = 0

        self._build_menu_items()
        self.clear_items()
        if len(self.paginate_options) > 1:
            self.add_item(self.previous_page_button)
        self.add_item(self.discord_links_button)
        self.add_item(self.member_ranks_button)
        self.add_item(self.war_status_button)
        if len(self.paginate_options) > 1:
            self.add_item(self.next_page_button)

        self.discord_links_button.disabled = True
        self.member_ranks_button.disabled = False
        self.war_status_button.disabled = False
    
    async def _set_member_ranks_content(self):
        def get_embed_text(lst:list):
            text = "\n".join([
                (f"{EmojisUI.LOGOUT}" if getattr(member.home_clan,'tag',None) == getattr(self.clan,'tag',None) and getattr(member.clan,'tag',None) != getattr(self.clan,'tag',None) else (f"{EmojisUI.YES}" if getattr(member.home_clan,'tag',None) == getattr(self.clan,'tag',None) else f"{EmojisUI.SPACER}"))
                + f"{EmojisTownHall.get(member.town_hall.level)}"
                + f"`{re.sub('[_*/]','',member.name)[:15]:<15}`\u3000" + f"`{'':>1}{str(member.role):<11}`\u3000"
                + (f"`{'':>1}{member.alliance_rank + '(' + member.home_clan.abbreviation + ')':<14}`" if member.is_member else f"`{'':^15}`")
                for member in lst])
            return text

        embeds = []
        chunked_members = list(chunks(self.all_clan_members,25))

        for i, members_chunk in enumerate(chunked_members):
            startend = f"Showing members {i*25+1} to {(i*25+1)+len(members_chunk)-1}. (Total: {len(self.all_clan_members)})"

            header_text = f"**Member Ranks**\nIn Clan: {self.clan.member_count}\u3000"
            header_text += f"Registered: {self.clan.alliance_member_count}\n\n" if self.clan.is_alliance_clan else "\n\n"
            header_text += f"{EmojisUI.YES}: this member has been registered to the Clan.\n"
            header_text += f"{EmojisUI.LOGOUT}: a registered member who is not in the in-game Clan.\n\n"
                
            embed = await clash_embed(
                context=self.ctx,
                title=(f"{self.clan.title}" if i == 0 else ""),
                message=header_text + get_embed_text(members_chunk) + f"\n\n**{startend}**",
                thumbnail=self.clan.badge,
                )
            embeds.append(embed)
        self.paginate_options = embeds
        self.page_index = 0

        self._build_menu_items()
        self.clear_items()
        if len(self.paginate_options) > 1:
            self.add_item(self.previous_page_button)
        self.add_item(self.discord_links_button)
        self.add_item(self.member_ranks_button)
        self.add_item(self.war_status_button)
        if len(self.paginate_options) > 1:
            self.add_item(self.next_page_button)

        self.discord_links_button.disabled = False
        self.member_ranks_button.disabled = True
        self.war_status_button.disabled = False
    
    async def _set_warstatus_content(self):
        def get_embed_text(lst:list):
            text = "\n".join([
                (f"{EmojisUI.LOGOUT}" if getattr(member.home_clan,'tag',None) == getattr(self.clan,'tag',None) and getattr(member.clan,'tag',None) != getattr(self.clan,'tag',None) else (f"{EmojisUI.YES}" if getattr(member.home_clan,'tag',None) == getattr(self.clan,'tag',None) else f"{EmojisUI.SPACER}"))
                + f"{EmojisTownHall.get(member.town_hall.level)}"
                + f"`{re.sub('[_*/]','',member.name)[:15]:<15}`\u3000"
                + f"`{member.war_opt_status:^5}`\u3000"
                + f"`{'':^1}"
                + f"{str(getattr(member.barbarian_king,'level','')):>2}"
                + f"{'  ' + str(getattr(member.archer_queen,'level','')):>4}"
                + f"{'  ' + str(getattr(member.grand_warden,'level','')):>4}"
                + f"{'  ' + str(getattr(member.royal_champion,'level','')):>4}"
                + f"{'':^1}`"
                for member in lst])
            return text
        
        war_status_num = {
            'IN': 1,
            'OUT': 0,
            }

        embeds = []
        #sort self.all_clan_members by war opt status and town hall level and hero levels        
        chunked_members = list(chunks(sorted(self.all_clan_members,key=lambda x: (war_status_num[x.war_opt_status],x.town_hall.level,x.hero_strength),reverse=True),25))
        iter_chunks = AsyncIter(chunked_members)

        async for i, members_chunk in iter_chunks.enumerate():
            startend = f"Showing members {i*25+1} to {(i*25+1)+len(members_chunk)-1}. (Total: {len(self.all_clan_members)})"

            header_text = f"**Member War Status**\nIn Clan: {self.clan.member_count}\u3000"
            header_text += f"Registered: {self.clan.alliance_member_count}\n\n" if self.clan.is_alliance_clan else "\n\n"
            header_text += f"Opted In: {len([member for member in self.members_in_clan if member.war_opted_in])} in Clan\u3000"
            header_text += f"{len([member for member in self.members_not_in_clan if member.war_opted_in])} Not in Clan\u3000"
            header_text += "\n\n"
            header_text += f"{EmojisUI.YES}: this member has been registered to the Clan.\n"
            header_text += f"{EmojisUI.LOGOUT}: a registered member who is not in the in-game Clan.\n\n"
                
            embed = await clash_embed(
                context=self.ctx,
                title=(f"{self.clan.title}" if i == 0 else ""),
                message=header_text + get_embed_text(members_chunk) + f"\n\n**{startend}**",
                thumbnail=self.clan.badge,
                )
            embeds.append(embed)
        self.paginate_options = embeds
        self.page_index = 0

        self._build_menu_items()
        self.clear_items()
        if len(self.paginate_options) > 1:
            self.add_item(self.previous_page_button)
        self.add_item(self.discord_links_button)
        self.add_item(self.member_ranks_button)
        self.add_item(self.war_status_button)
        if len(self.paginate_options) > 1:
            self.add_item(self.next_page_button)

        self.discord_links_button.disabled = False
        self.member_ranks_button.disabled = False
        self.war_status_button.disabled = True