import discord
import asyncio

from typing import *

from redbot.core import commands
from redbot.core.utils import AsyncIter

from coc_client.api_client import BotClashClient

from coc_data.objects.players.player import aPlayer
from coc_data.objects.events.clan_war_leagues import WarLeaguePlayer, WarLeagueClan

from coc_data.utilities.components import *

from coc_data.constants.ui_emojis import *
from coc_data.constants.coc_emojis import *
from coc_data.constants.coc_constants import *

from coc_data.exceptions import *

from ..helpers.components import *

bot_client = BotClashClient()

class CWLRosterDisplayMenu(MenuPaginator):
    def __init__(self,
        context:Union[commands.Context,discord.Interaction],
        clan:WarLeagueClan):

        self.is_active = False
        self.waiting_for = False

        self.league_clan = clan
        self.reference_list = []

        super().__init__(context,[])
    
    # this exists because we are lazy
    @property
    def clan(self):
        return self.league_clan

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
        if self.league_clan.status in ['CWL Started']:
            roster_players = await asyncio.gather(*(p.get_full_player() for p in self.league_clan.master_roster))
            self.reference_list = sorted(roster_players,key=lambda x:(x.town_hall.level,x.hero_strength),reverse=True)
        else:
            if self.clan.roster_open:
                embed = await clash_embed(
                    context=self.ctx,
                    title=f"CWL Roster: {self.league_clan.name} ({self.league_clan.tag})",
                    message="This Clan's roster isn't available yet.",
                    thumbnail=self.league_clan.clan.badge,
                    success=False,
                    )
                if isinstance(self.ctx,discord.Interaction):
                    await self.ctx.edit_original_response(embed=embed,view=None)
                else:
                    await self.ctx.reply(embed=embed,view=None)
                return

            roster_players = await asyncio.gather(*(p.get_full_player() for p in self.league_clan.participants))
            self.reference_list = sorted(roster_players,key=lambda x:(x.town_hall.level,x.hero_strength),reverse=True)

            game_clan = await self.league_clan.get_full_clan()
            mem_in_clan = await asyncio.gather(*(bot_client.cog.fetch_player(p.tag) for p in game_clan.members))
            async for mem in AsyncIter(mem_in_clan):
                if mem.tag not in [p.tag for p in self.reference_list]:
                    self.reference_list.append(mem)
        self.is_active = True

        await self._set_roster_status_content()
        kwargs = self.get_content()
        if isinstance(self.ctx,discord.Interaction):
            await self.ctx.edit_original_response(**kwargs)
            self.message = await self.ctx.original_response()
        else:
            self.message = await self.ctx.reply(**kwargs)
    
    ##################################################
    ### CALLBACKS
    ##################################################
    async def _callback_roster_status(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        await self._set_roster_status_content()
        kwargs = self.get_content()
        await interaction.edit_original_response(**kwargs)

    async def _callback_roster_strength(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        await self._set_roster_strength_content()
        kwargs = self.get_content()
        await interaction.edit_original_response(**kwargs)
    
    ##################################################
    ### CONTENT HELPERS
    ##################################################
    def _build_menu_items(self):
        self.previous_page_button = DiscordButton(function=self.to_previous_page,style=discord.ButtonStyle.gray,emoji=EmojisUI.GREEN_PREVIOUS)
        self.next_page_button = DiscordButton(function=self.to_next_page,style=discord.ButtonStyle.gray,emoji=EmojisUI.GREEN_NEXT)
        self.roster_status_button = DiscordButton(function=self._callback_roster_status,label="Roster Status",emoji=EmojisClash.WARLEAGUES)
        self.roster_strength_button = DiscordButton(function=self._callback_roster_strength,label="Roster Strength",emoji=EmojisHeroes.BARBARIAN_KING)

    async def _set_roster_status_content(self):
        def evaluate_player_status(player):
            if self.league_clan.status in ['CWL Started']:
                if player.tag in [p.tag for p in self.league_clan.participants] and player.tag in [p.tag for p in self.league_clan.master_roster]:
                    return f"{EmojisUI.YES}"
                if player.tag not in [p.tag for p in self.league_clan.participants] and player.tag in [p.tag for p in self.league_clan.master_roster]:
                    return f"{EmojisUI.QUESTION}"
            else:
                if player.tag in [p.tag for p in self.league_clan.participants]:
                    return f"{EmojisUI.YES}"
            return f"{EmojisUI.SPACER}"

        embeds = []
        chunked_members = list(chunks(self.reference_list,25))
        iter_chunks = AsyncIter(chunked_members)

        async for i, members_chunk in iter_chunks.enumerate():
            startend = f"Showing members {i*25+1} to {(i*25+1)+len(members_chunk)-1}. (Total: {len(self.reference_list)})"

            header_text = f"**Season:** {self.league_clan.season.description}"
            header_text += f"\n**Status:** {self.league_clan.status}"
            header_text += f"\n**League:** {EmojisLeagues.get(self.league_clan.league)}{self.league_clan.league}"
            if self.league_clan.status in ["CWL Started"]:
                roster_players = await asyncio.gather(*(p.get_full_player() for p in self.league_clan.master_roster))
                header_text += f"\n**Participants:** {len([p for p in roster_players if p.clan.tag == self.league_clan.tag])} In Clan / {len([p for p in self.league_clan.master_roster])} in CWL"
            else:
                roster_players = await asyncio.gather(*(p.get_full_player() for p in self.league_clan.participants))
                header_text += f"\n**Rostered:** {len([p for p in self.league_clan.participants if p.clan.tag == self.league_clan.tag])} In Clan / {len([p for p in self.league_clan.participants])} Rostered"

            header_text += f"\n\n"
            header_text += (f"{EmojisUI.YES}: a Rostered CWL Player\n" if self.league_clan.status in ["Roster Finalized","Roster Pending"] else "")
            header_text += (f"{EmojisUI.YES}: a Rostered CWL Player in the in-game Roster\n" if self.league_clan.status in ["CWL Started"] else "")
            header_text += (f"{EmojisUI.QUESTION}: In the in-game CWL Roster but was **NOT** rostered\n" if self.league_clan.status in ["CWL Started"] else "")
            header_text += f"{EmojisUI.LOGOUT}: this player is not in the in-game Clan.\n\n"
            
            member_text = "\n".join([
                (f"{evaluate_player_status(player)}")
                + (f"{EmojisUI.LOGOUT}" if player.clan.tag != self.clan.tag else f"{EmojisUI.SPACER}")
                + f"{EmojisTownHall.get(player.town_hall)}"
                + f"`{re.sub('[_*/]','',player.clean_name)[:13]:<13}`\u3000" + f"`{'':^1}{player.tag:<11}`\u3000"
                + (f"`{'':^1}{getattr(self.ctx.guild.get_member(player.discord_user),'display_name','Not Found')[:12]:<12}`" if player.discord_user else f"`{'':<13}`")
                for player in members_chunk]
                )
            embed = await clash_embed(
                context=self.ctx,
                title=f"CWL Roster: {self.league_clan.name} ({self.league_clan.tag})",
                message=header_text+member_text+f"\n\n**{startend}**",
                thumbnail=self.league_clan.badge,
                )
            embeds.append(embed)

        self.paginate_options = embeds
        self.page_index = 0

        self._build_menu_items()
        self.clear_items()
        if len(self.paginate_options) > 1:
            self.add_item(self.previous_page_button)
        self.add_item(self.roster_status_button)
        self.add_item(self.roster_strength_button)
        if len(self.paginate_options) > 1:
            self.add_item(self.next_page_button)

        self.roster_status_button.disabled = True
        self.roster_strength_button.disabled = False
    
    async def _set_roster_strength_content(self):
        embeds = []
        chunked_members = list(chunks(self.reference_list,25))
        iter_chunks = AsyncIter(chunked_members)

        async for i, members_chunk in iter_chunks.enumerate():
            startend = f"Showing members {i*25+1} to {(i*25+1)+len(members_chunk)-1}. (Total: {len(self.reference_list)})"

            header_text = f"**Season:** {self.league_clan.season.description}"
            header_text += f"\n**Status:** {self.league_clan.status}"
            header_text += f"\n**League:** {EmojisLeagues.get(self.league_clan.league)}{self.league_clan.league}"
            if self.league_clan.status in ["CWL Started"]:
                roster_players = await asyncio.gather(*(p.get_full_player() for p in self.league_clan.master_roster))
                header_text += f"\n**Participants:** {len([p for p in roster_players if p.clan.tag == self.clan.tag])} In Clan / {len([p for p in self.clan.master_roster])} in CWL"
                header_text += f"\n*Only showing players in the in-game master roster.*"
            else:
                roster_players = await asyncio.gather(*(p.get_full_player() for p in self.clan.participants))
                header_text += f"\n**Rostered:** {len([p for p in self.clan.participants if p.clan.tag == self.clan.tag])} In Clan / {len([p for p in self.clan.participants])} Rostered"

            header_text += f"\n\n"
            header_text += f"{EmojisUI.YES}: This player is rostered to play in CWL."

            header_text += f"\n"            
            header_text += f"{EmojisUI.SPACER}{EmojisUI.SPACER}`{'':<1}{'BK':>2}{'':<2}{'AQ':>2}{'':<2}{'GW':>2}{'':<2}{'RC':>2}{'':<2}{'':<15}`\n"
            member_text = "\n".join([
                f"{EmojisTownHall.get(player.town_hall)}"
                + (f"{EmojisUI.YES}" if player in self.clan.participants else f"{EmojisUI.SPACER}")
                + f"`{'':<1}{getattr(player.get_hero('Barbarian King'),'level',''):>2}"
                + f"{'':<2}{getattr(player.get_hero('Archer Queen'),'level',''):>2}"
                + f"{'':<2}{getattr(player.get_hero('Grand Warden'),'level',''):>2}"
                + f"{'':<2}{getattr(player.get_hero('Royal Champion'),'level',''):>2}"
                + f"{'':<2}{re.sub('[_*/]','',player.clean_name)[:15]:<15}`"
                for player in members_chunk]
                )                
            embed = await clash_embed(
                context=self.ctx,
                title=f"CWL Roster: {self.clan.clean_name} ({self.clan.tag})",
                message=header_text+member_text+f"\n\n**{startend}**",
                thumbnail=self.clan.badge,
                )
            embeds.append(embed)
        self.paginate_options = embeds
        self.page_index = 0

        self._build_menu_items()
        self.clear_items()
        if len(self.paginate_options) > 1:
            self.add_item(self.previous_page_button)
        self.add_item(self.roster_status_button)
        self.add_item(self.roster_strength_button)
        if len(self.paginate_options) > 1:
            self.add_item(self.next_page_button)

        self.roster_status_button.disabled = False
        self.roster_strength_button.disabled = True