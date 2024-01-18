import asyncio
import discord
import pendulum

from typing import *
from redbot.core import commands,bank

from coc_main.api_client import BotClashClient as client

from coc_main.utils.components import DefaultView, DiscordButton, DiscordSelectMenu, clash_embed
from coc_main.utils.constants.coc_constants import WarResult, WarState
from coc_main.utils.constants.coc_emojis import EmojisClash, EmojisTownHall
from coc_main.utils.constants.ui_emojis import EmojisUI

from coc_main.coc_objects.clans.clan import aClan
from coc_main.coc_objects.events.helpers import clan_war_embed
from coc_main.coc_objects.events.clan_war import aClanWar
from coc_main.coc_objects.events.war_summary import aClanWarSummary

bot_client = client()

class ClanWarLog(DefaultView):
    def __init__(self,
        context:discord.Interaction,
        clan:aClan):
        
        self.clan = clan
        self.war_selector = None
        self.war_summary = None
        self.war_index = -1


        super().__init__(context,timeout=600)
    
    @property
    def home_button(self):
        return DiscordButton(
            function=self._callback_home,
            style=discord.ButtonStyle.blurple,
            emoji=EmojisUI.HOME,
            label="Overview",
            row=1
            )
    @property
    def close_button(self):
        return DiscordButton(
            function=self._callback_close,
            style=discord.ButtonStyle.red,
            emoji=EmojisUI.EXIT,
            row=1
            )
    
    # def view_clan_button(self,war:aClanWar):
    #     return DiscordButton(
    #         function=self._callback_,
    #         style=discord.ButtonStyle.red,
    #         emoji=EmojisUI.EXIT,
    #         row=1
    #         )
    # def view_opponent_button(self,war:aClanWar):
    #     return DiscordButton(
    #         function=self._callback_close,
    #         style=discord.ButtonStyle.red,
    #         emoji=EmojisUI.EXIT,
    #         row=1
    #         )
    
    ##################################################
    ### OVERRIDE BUILT IN METHODS
    ##################################################
    async def on_timeout(self):
        self.stop_menu()
    
    ####################################################################################################
    #####
    ##### VIEW HELPERS
    #####
    ####################################################################################################    
    async def overview_embed(self):
        min_prep_start = min([w.start_time.int_timestamp for w in self.war_summary.war_log])
        war_wins = len([w for w in self.war_summary.war_log if w.get_clan(self.clan.tag).result in [WarResult.WINNING,WarResult.WON]])
        war_losses = len([w for w in self.war_summary.war_log if w.get_clan(self.clan.tag).result in [WarResult.LOSING,WarResult.LOST]])
        war_ties = len([w for w in self.war_summary.war_log if w.get_clan(self.clan.tag).result in [WarResult.TIED]])

        avg_townhall = round(sum([w.get_clan(self.clan.tag).average_townhall for w in self.war_summary.war_log])/len(self.war_summary.war_log),1)
        total_attacks = sum([w.attacks_per_member * w.team_size for w in self.war_summary.war_log])

        embed = await clash_embed(
            context=self.ctx,
            title=f"**{self.clan.title}**",
            message=f"**{len(self.war_summary.war_log)} Clan War(s) recorded since <t:{min_prep_start-86400}:R>.**",
            thumbnail=self.clan.badge,
            )
        embed.add_field(
            name="**__War Performance__**",
            value=f"Wins: {war_wins} ({war_wins/len(self.war_summary.war_log)*100:.0f}%)"
                + f"\nLosses: {war_losses} ({war_losses/len(self.war_summary.war_log)*100:.0f}%)"
                + f"\nTies: {war_ties} ({war_ties/len(self.war_summary.war_log)*100:.0f}%)",
            inline=False
            )
        embed.add_field(
            name="**__War Stats__**",
            value=f"Average TH: {avg_townhall}"
                + f"\n{EmojisClash.THREESTARS} Triples: {self.war_summary.triples:,} / {total_attacks:,} ({self.war_summary.triples/total_attacks*100:.0f}%)"
                + f"\n{EmojisClash.UNUSEDATTACK} Unused Hits: {self.war_summary.unused_attacks:,} / {total_attacks:,} ({self.war_summary.unused_attacks/total_attacks*100:.0f}%)",
            inline=False
            )
        return embed
    
    ##################################################
    ### START / STOP 
    ##################################################
    async def start(self):
        self.is_active = True
        get_all_wars = await aClanWar.for_clan(self.clan.tag)
        
        self.war_summary = await bot_client.run_in_thread(aClanWarSummary.for_clan,self.clan.tag,get_all_wars)
        self.war_selector = [
            discord.SelectOption(
                label=f"{w.clan_1.name} vs {w.clan_2.name}",
                value=i-1,
                description=(f"War Ended {w.end_time.format('MMM DD, YYYY')}" if w.state == WarState.WAR_ENDED else f"War Ends {w.end_time.format('MMM DD, YYYY')}"),
                emoji=w.get_clan(self.clan.tag).emoji)
            for i,w in enumerate(self.war_summary.war_log,1)
            ]
        
        embed = await self.overview_embed()
        self._build_war_select_menu()
        
        if isinstance(self.ctx,discord.Interaction):
            await self.ctx.edit_original_response(embed=embed,view=self)
            self.message = await self.ctx.original_response()
        else:
            self.message = await self.ctx.reply(embed=embed,view=self)
    
    async def _callback_home(self,interaction:discord.Interaction,button:discord.Button):
        self.war_index = -1
        embed = await self.overview_embed()
        self._build_war_select_menu()
        await interaction.response.edit_message(embed=embed,view=self)
    
    async def _callback_close(self,interaction:discord.Interaction,button:discord.Button):
        self.clear_items()
        await interaction.response.edit_message(view=self)
        self.stop_menu()
    
    async def _callback_select_war(self,interaction:discord.Interaction,select:DiscordSelectMenu):
        await interaction.response.defer()
        if select.values[0] == "overview":
            embed = await self.overview_embed()
            await interaction.edit_original_response(embed=embed,view=self)
            return
        
        self.war_index = int(select.values[0])
        select_war = self.war_summary.war_log[self.war_index]
        self._build_war_select_menu()
        embed = await clan_war_embed(context=interaction,clan_war=select_war)

        await interaction.edit_original_response(embed=embed,view=self)
 
    def _build_war_select_menu(self):
        self.clear_items()

        if len(self.war_selector) > 25:
            minus_diff = None
            plus_diff = 25
            if 12 < self.war_index < len(self.war_selector) - 25:
                minus_diff = self.war_index - 12
                plus_diff = self.war_index + 13
            elif self.war_index >= len(self.war_selector) - 25:
                minus_diff = len(self.war_selector) - 25
                plus_diff = None
            options = self.war_selector[minus_diff:plus_diff]
        else:
            options = self.war_selector[:25]
        
        for option in options:
            if option.value == self.war_index:
                option.default = True
            else:
                option.default = False
            
        select_menu = DiscordSelectMenu(
            function=self._callback_select_war,
            options=options,
            placeholder="Select a War to view.",
            min_values=1,
            max_values=1,
            row=1
            )
        self.add_item(self.home_button)
        self.add_item(self.close_button)
        self.add_item(select_menu)