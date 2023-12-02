import discord

from typing import *
from redbot.core import commands
from redbot.core.utils import AsyncIter

from coc_main.api_client import BotClashClient, aClashSeason
from coc_main.cog_coc_client import ClashOfClansClient, aPlayer
from coc_main.coc_objects.events.clan_war_leagues import WarLeaguePlayer, WarLeagueClan

from coc_main.utils.components import clash_embed, DefaultView, DiscordButton, DiscordSelectMenu
from coc_main.utils.constants.ui_emojis import EmojisUI
from coc_main.utils.constants.coc_emojis import EmojisTownHall, EmojisLeagues
from coc_main.utils.constants.coc_constants import CWLLeagueGroups

bot_client = BotClashClient()

class CWLSeasonSetup(DefaultView):
    def __init__(self,
        context:Union[commands.Context,discord.Interaction],
        season:aClashSeason):

        self.season = season
        
        self._open_signups_button = DiscordButton(
            function=self._open_signups,
            label="Open Signups",
            style=discord.ButtonStyle.blurple
            )
        self._open_signups_button.disabled = self.season.cwl_signup_lock
        
        self._close_signups_button = DiscordButton(
            function=self._close_signups,
            label="Close Signups",
            style=discord.ButtonStyle.secondary
            )
        self._close_signups_button.disabled = self.season.cwl_signup_lock

        self.clan_selector = None

        self.close_button = DiscordButton(
            function=self._close,
            label="",
            emoji=EmojisUI.EXIT,
            style=discord.ButtonStyle.red,
            row=0
            )
        super().__init__(context=context,timeout=300)

        self.add_item(self._open_signups_button)
        self.add_item(self._close_signups_button)
        self.add_item(self.close_button)
    
    @property
    def bot_client(self) -> BotClashClient:
        return bot_client

    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    ##################################################
    ### START / STOP CALL
    ##################################################
    async def start(self):

        cwl_clans = await self.client.get_war_league_clans()
        if len(cwl_clans) == 0:
            embed = await clash_embed(
                context=self.ctx,
                message=f"**No clans registered for CWL.** Add some maybe?")
            if isinstance(self.ctx,discord.Interaction):
                await self.ctx.edit_original_response(embed=embed, view=None)
            else:
                await self.ctx.reply(embed=embed)
            return self.stop_menu()
        
        embed = await self.get_embed()

        await self.build_clan_selector()
        self.is_active = True

        if isinstance(self.ctx,discord.Interaction):
            await self.ctx.edit_original_response(embed=embed, view=self)
            self.message = await self.ctx.original_response()
        else:
            self.message = await self.ctx.reply(embed=embed, view=self)
    
    ##################################################
    ### BUTTON CALLBACKS
    ##################################################
    async def _close(self,interaction:discord.Interaction,button:DiscordButton):
        self.stop_menu()
        embed = await clash_embed(
            context=self.ctx,
            message=f"**CWL Setup Menu closed.**")
        await interaction.response.edit_message(embed=embed,view=None)
    
    async def _open_signups(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        
        await self.season.open_cwl_signups()
        embed = await self.get_embed()
        await interaction.edit_original_response(embed=embed,view=self)
    
    async def _close_signups(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()        
        await self.season.close_cwl_signups()
        embed = await self.get_embed()
        await interaction.edit_original_response(embed=embed,view=self)
    
    async def _callback_clan_select(self,interaction:discord.Interaction,select:DiscordSelectMenu):
        await interaction.response.defer()

        currently_participating = await WarLeagueClan.participating_by_season(self.season)

        async for clan in AsyncIter(currently_participating):
            if clan.tag not in select.values:
                await clan.disable_for_war_league()
        
        async for clan_tag in AsyncIter(select.values):
            league_clan = await WarLeagueClan(clan_tag,self.season)
            await league_clan.enable_for_war_league()
            
        embed = await self.get_embed()
        await self.build_clan_selector()
        await interaction.edit_original_response(embed=embed,view=self)
    
    async def get_embed(self):
        current_signups = await WarLeaguePlayer.signups_by_season(self.season)

        all_th = sorted(list(set([p.town_hall for p in current_signups])),reverse=True)

        embed = await clash_embed(
            context=self.ctx,
            title=f"CWL Season Setup: {self.season.description}",
            message=("```**Season Locked**```" if self.season.cwl_signup_lock else "")
                + f"**CWL Starts**: <t:{self.season.cwl_start.int_timestamp}:F>"
                + f"\n**CWL Ends**: <t:{self.season.cwl_end.int_timestamp}:F>"
                + "\n\u200b",
            )        
        embed.add_field(
            name=f"**Player Registration**: `{'OPEN' if self.season.cwl_signup_status else 'CLOSED'}`",
            value=f"**Total:** `{len(current_signups):>3}`"
                + f"\n**Rostered:** `{len([p for p in current_signups if p.roster_clan]):>3}`"
                + f"\u3000**Unrostered:** `{len([p for p in current_signups if not p.roster_clan]):>3}`"
                + '\n'
                + '\u3000'.join([f"{EmojisTownHall.get(th)} `{len([p for p in current_signups if p.town_hall == th]):^3}`" for th in all_th[:5]])
                + ('\n' if len(all_th) > 5 else "")
                + ('\u3000'.join([f"{EmojisTownHall.get(th)} `{len([p for p in current_signups if p.town_hall == th]):^3}`" for th in all_th[5:10]]) if len(all_th) > 5 else "")
                + ('\n' if len(all_th) > 10 else "")
                + ('\u3000'.join([f"{EmojisTownHall.get(th)} `{len([p for p in current_signups if p.town_hall == th]):^3}`" for th in all_th[10:]]) if len(all_th) > 10 else "")
                + '\n> '
                + '\n> '.join([
                    f"{CWLLeagueGroups.get_description(i)}: `{len([p for p in current_signups if p.league_group == i]):>3}`"
                    for i in [1,2,9,99]
                    ])
                + "\n\u200b",
            inline=False
            )
        participating_clans = await WarLeagueClan.participating_by_season(self.season)
        async for cwl_clan in AsyncIter(participating_clans):
            league_group = await cwl_clan.get_league_group()
            embed.add_field(
                name=f"{EmojisLeagues.get(cwl_clan.war_league_name)} {cwl_clan.name} ({cwl_clan.tag})",
                value=f"# in Roster: {len(cwl_clan.participants)} (Roster {'Open' if cwl_clan.roster_open else 'Finalized'})"
                    + (f"\nIn War: Round {len(league_group.rounds)-1} / {league_group.number_of_rounds}\nPreparation: Round {len(league_group.rounds)} / {league_group.number_of_rounds}" if league_group else "\nCWL Not Started" if self.season.cwl_signup_lock else "")
                    + (f"\nMaster Roster: {len(cwl_clan.master_roster_tags)}" if league_group else "")
                    + "\n\u200b",
                inline=False
                )
        return embed

    async def build_clan_selector(self):
        if self.clan_selector:
            self.remove_item(self.clan_selector)
            self.clan_selector = None

        if not self.season.cwl_signup_lock:
            clans = await self.client.get_war_league_clans()

            options = []
            async for c in AsyncIter(clans):
                league = await WarLeagueClan(c.tag,self.season)
                options.append(discord.SelectOption(
                    label=str(c),
                    value=c.tag,
                    emoji=EmojisLeagues.get(c.war_league_name),
                    description=f"Level {c.level} | {c.war_league_name}",
                    default=league.is_participating)
                    )
            
            self.clan_selector = DiscordSelectMenu(
                function=self._callback_clan_select,
                options=options,
                placeholder="Select one or more clan(s) for CWL...",
                min_values=1,
                max_values=len(options)
                )        
            self.clan_selector.disabled = self.season.cwl_signup_lock
            self.add_item(self.clan_selector)