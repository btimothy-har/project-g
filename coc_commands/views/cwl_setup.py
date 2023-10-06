import discord

from typing import *
from redbot.core import commands
from redbot.core.utils import AsyncIter

from coc_client.api_client import BotClashClient

from coc_data.objects.clans.clan import aClan
from coc_data.objects.season.season import aClashSeason
from coc_data.objects.events.clan_war_leagues import WarLeagueClan, WarLeaguePlayer

from coc_data.utilities.components import *

from coc_data.constants.ui_emojis import *
from coc_data.constants.coc_emojis import *
from coc_data.constants.coc_constants import *

from coc_data.exceptions import *

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
    
    ##################################################
    ### START / STOP CALL
    ##################################################
    async def start(self):

        cwl_clans = bot_client.cog.get_cwl_clans()
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
        
        self.season.cwl_signup_status = True
        embed = await self.get_embed()
        await interaction.edit_original_response(embed=embed,view=self)
    
    async def _close_signups(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()        
        self.season.cwl_signup_status = False
        embed = await self.get_embed()
        await interaction.edit_original_response(embed=embed,view=self)
    
    async def _callback_clan_select(self,interaction:discord.Interaction,select:DiscordSelectMenu):
        await interaction.response.defer()

        for clan in WarLeagueClan.participating_by_season(self.season):
            if clan.tag not in select.values:
                clan.is_participating = False
        
        for clan_tag in select.values:
            clan = await bot_client.cog.fetch_clan(clan_tag)
            clan.war_league_season(self.season).is_participating = True
            
        embed = await self.get_embed()
        await self.build_clan_selector()
        await interaction.edit_original_response(embed=embed,view=self)
    
    async def get_embed(self):
        current_signups = WarLeaguePlayer.signups_by_season(self.season)

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
        participating_clans = WarLeagueClan.participating_by_season(self.season)
        async for cwl_clan in AsyncIter(participating_clans):
            embed.add_field(
                name=f"{EmojisLeagues.get(cwl_clan.war_league_name)} {cwl_clan.clan_str}",
                value=f"# in Roster: {len(cwl_clan.participants)} (Roster {'Open' if cwl_clan.roster_open else 'Finalized'})"
                    + (f"\nIn War: Round {len(cwl_clan.league_group.rounds)-1} / {cwl_clan.league_group.number_of_rounds}\nPreparation: Round {len(cwl_clan.league_group.rounds)} / {cwl_clan.league_group.number_of_rounds}" if cwl_clan.league_group else "\nCWL Not Started" if self.season.cwl_signup_lock else "")
                    + (f"\nMaster Roster: {len(cwl_clan.master_roster)}" if cwl_clan.league_group else "")
                    + "\n\u200b",
                inline=False
                )
        return embed

    async def build_clan_selector(self):
        if self.clan_selector:
            self.remove_item(self.clan_selector)
            self.clan_selector = None

        if not self.season.cwl_signup_lock:
            clans = bot_client.cog.get_cwl_clans()

            options = []
            async for c in AsyncIter(clans):
                clan = await c.get_full_clan()
                options.append(discord.SelectOption(
                    label=str(clan),
                    value=clan.tag,
                    emoji=EmojisLeagues.get(clan.war_league_name),
                    description=f"Level {clan.level} | {clan.war_league_name}",
                    default=clan.war_league_season(self.season).is_participating)
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