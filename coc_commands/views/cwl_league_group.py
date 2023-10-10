import discord
import asyncio
import re

from typing import *

from redbot.core import commands
from redbot.core.utils import AsyncIter

from coc_main.api_client import BotClashClient
from coc_main.cog_coc_client import ClashOfClansClient, aClanWar
from coc_main.coc_objects.events.clan_war_leagues import WarLeagueClan
from coc_main.coc_objects.events.war_summary import aClanWarSummary
from coc_main.coc_objects.events.helpers import clan_war_embed

from coc_main.utils.components import clash_embed, DefaultView, DiscordButton, DiscordSelectMenu
from coc_main.utils.constants.coc_emojis import EmojisClash, EmojisLeagues, EmojisTownHall
from coc_main.utils.constants.coc_constants import WarState, WarResult
from coc_main.utils.constants.ui_emojis import EmojisUI

bot_client = BotClashClient()

class CWLClanGroupMenu(DefaultView):
    def __init__(self,
        context:Union[commands.Context,discord.Interaction],
        clan:WarLeagueClan):

        self.league_group = clan.league_group
        self.clan = None
        self.war = None
        self.clan_nav = None
        super().__init__(context,timeout=300)
    
    @property
    def bot_client(self) -> BotClashClient:
        return bot_client

    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    ##################################################
    ### START / STOP
    ##################################################
    async def start(self):
        self.is_active = True

        league_group_button = self._button_league_group()
        league_group_button.disabled = True

        self.add_item(league_group_button)
        self.add_item(self._button_league_table())
        self.add_item(self._dropdown_clan_select())

        embed = await self._content_embed_league_group()
        if isinstance(self.ctx,discord.Interaction):
            await self.ctx.edit_original_response(embed=embed,view=self)
            self.message = await self.ctx.original_response()
        else:
            self.message = await self.ctx.reply(embed=embed,view=self)
    
    ##################################################
    ### CALLBACKS
    ##################################################
    async def _callback_league_group(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()

        self.clan = None
        self.war = None

        self.clear_items()
        league_group_button = self._button_league_group()
        league_group_button.disabled = True

        self.add_item(league_group_button)
        self.add_item(self._button_league_table())
        self.add_item(self._dropdown_clan_select())

        embed = await self._content_embed_league_group()
        await interaction.edit_original_response(embed=embed,view=self)

    async def _callback_league_table(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()

        self.clan = None
        self.war = None
        
        self.clear_items()
        self.add_item(self._button_league_group())
        
        league_table_button = self._button_league_table()
        league_table_button.disabled = True
        self.add_item(league_table_button)
        self.add_item(self._dropdown_clan_select())

        embed = await self._content_embed_league_table()
        await interaction.edit_original_response(embed=embed,view=self)

    async def _callback_select_clan(self,interaction:discord.Interaction,select:Optional[DiscordSelectMenu]=None):
        if not interaction.response.is_done():
            await interaction.response.defer()

        if select:
            self.clan = self.league_group.get_clan(select.values[0])
        self.war = None

        self.clear_items()
        self.add_item(self._button_league_group())
        roster_button = self._button_clan_roster()
        self.add_item(roster_button)
        stats_button = self._button_clan_stats()
        self.add_item(stats_button)
        self.add_item(self._dropdown_clan_select())
        self.add_item(self._dropdown_war_select(self.clan.league_wars))

        if not self.clan_nav:
            embed = await self._content_clan_roster()
            self.clan_nav = 'roster'
            roster_button.disabled = True
            stats_button.disabled = False
        else:
            if self.clan_nav == 'roster':
                embed = await self._content_clan_roster()
                roster_button.disabled = True
                stats_button.disabled = False
            elif self.clan_nav == 'stats':
                embed = await self._content_clan_stats()
                roster_button.disabled = False
                stats_button.disabled = True

        await interaction.edit_original_response(embed=embed,view=self)
    
    async def _callback_clan_stats(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        self.clan_nav = 'stats'
        self.war = None
        await self._callback_select_clan(interaction)
    
    async def _callback_clan_roster(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        self.clan_nav = 'roster'
        self.war = None
        await self._callback_select_clan(interaction)
    
    async def _callback_select_war(self,interaction:discord.Interaction,select:DiscordSelectMenu):
        await interaction.response.defer()
        self.clan_nav = None
        self.war = aClanWar(select.values[0])

        self.clear_items()
        self.add_item(self._button_league_group())
        self.add_item(self._button_clan_roster())
        self.add_item(self._button_clan_stats())
        self.add_item(self._dropdown_clan_select())
        self.add_item(self._dropdown_war_select(self.clan.league_wars))

        #embed = await self.war.war_embed_overview(ctx=self.ctx)
        embed = await clan_war_embed(self.ctx,self.war)
        await interaction.edit_original_response(embed=embed,view=self)

    ##################################################
    ### BUTTON BUILDERS
    ##################################################
    def _button_league_group(self):
        return DiscordButton(
            function=self._callback_league_group,
            emoji=EmojisClash.WARLEAGUES,
            label="League Group",
            style=discord.ButtonStyle.blurple
            )
    def _button_league_table(self):
        return DiscordButton(
            function=self._callback_league_table,
            emoji=EmojisClash.WARLEAGUETROPHY,
            label="League Table",
            style=discord.ButtonStyle.secondary
            )
    def _dropdown_clan_select(self):
        clan_select = [discord.SelectOption(
            label=f"{clan.clean_name} ({clan.tag})",
            value=f"{clan.tag}",
            default=True if clan.tag == getattr(self.clan,'tag',None) else False)
            for clan in self.league_group.clans
            ]
        return DiscordSelectMenu(
            function=self._callback_select_clan,
            options=clan_select,
            placeholder="Select a Clan to view.",
            min_values=1,
            max_values=1,
            )
    def _button_clan_roster(self):
        return DiscordButton(
            function=self._callback_clan_roster,
            label=f"Roster: {self.clan.clean_name}",
            style=discord.ButtonStyle.secondary
            )
    def _button_clan_stats(self):
        return DiscordButton(
            function=self._callback_clan_stats,
            label=f"Stats: {self.clan.clean_name}",
            style=discord.ButtonStyle.secondary
            )
    def _dropdown_war_select(self,wars:list[aClanWar]):
        war_select = [discord.SelectOption(
            label=f"{war.clan_1.clean_name} vs {war.clan_2.clean_name} (Round {self.league_group.get_round_from_war(war)})",
            value=war.war_id,
            default=True if war.war_id == getattr(self.war,'war_id',None) else False)
            for war in wars
            ]
        return DiscordSelectMenu(
            function=self._callback_select_war,
            options=war_select,
            placeholder="Select a War to view.",
            min_values=1,
            max_values=1,
            )
    
    ##################################################
    ### CONTENT BUILDERS
    ##################################################    
    async def _content_embed_league_group(self):
        emoji_id = re.search(r'\d+',EmojisLeagues.get(self.league_group.league)).group()
        league_emoji = self.bot_client.bot.get_emoji(int(emoji_id))

        content_body = (f"**League:** {EmojisLeagues.get(self.league_group.league)} {self.league_group.league}"
            + f"\n**Rounds:** {self.league_group.number_of_rounds}"
            + f"\n**State:** {WarState.readable_text(self.league_group.state)} (Round {self.league_group.current_round})"
            + "\n\u200b"
            )
        embed = await clash_embed(
            context=self.ctx,
            title=f"CWL Group: {self.league_group.season.description}",
            message=content_body,
            thumbnail=league_emoji.url
            )
        
        for lc in self.league_group.clans:            
            embed.add_field(
                name=f"\u200E__**{lc.clean_name} ({lc.tag})**__",
                value=f"**Level**: {lc.level}"
                    + f"\n**Players In CWL:** {len(lc.master_roster)}\u3000**Average TH:** {lc.master_average_th}"
                    + "\n"
                    + '\u3000'.join(f"{EmojisTownHall.get(th)} {ct}" for th,ct in lc.master_lineup.items())
                    + "\n\u200b",
                inline=False
                )               
        return embed
    
    async def _content_embed_league_table(self):
        emoji_id = re.search(r'\d+',EmojisLeagues.get(self.league_group.league)).group()
        league_emoji = self.bot_client.bot.get_emoji(int(emoji_id))
        league_clans = sorted(self.league_group.clans,key=lambda x: (x.total_score,x.total_destruction),reverse=True)

        league_table = f"```{'':^3}{'STARS':>5}{'':^2}{'DESTR %':>7}{'':^20}\n"        
        league_table += '\n'.join([
            f"\u200E{i:<3}{lc.total_score:>5}{'':^2}{str(lc.total_destruction)+'%':>7}{'':<3}{lc.clean_name[:17]:<17}"
            for i,lc in enumerate(league_clans,start=1)
            ])
        league_table += "```"

        embed = await clash_embed(
            context=self.ctx,
            title=f"CWL Table: {self.league_group.season.description}",
            message=f"**League:** {EmojisLeagues.get(self.league_group.league)} {self.league_group.league}"
                + f"\n**Rounds:** {self.league_group.number_of_rounds}"
                + f"\n**State:** {WarState.readable_text(self.league_group.state)} (Round {self.league_group.current_round})"
                + f"\n\n{league_table}\n\u200b",
            thumbnail=league_emoji.url)
        
        for i,rd in enumerate(self.league_group.rounds,start=1):
            wars = [aClanWar(war) for war in rd]

            war_str = ""
            for war in wars:
                war_str += f"\u200E`{war.clan_1.clean_name[:10]:>10}\u200E {war.clan_1.stars:>3} {str(round(war.clan_1.destruction))+'%':>4}`{WarResult.WINEMOJI if war.clan_1.result == WarResult.WON else WarResult.LOSEEMOJI if war.clan_1.result == WarResult.LOST else EmojisUI.SPACER}"
                war_str += f"**vs**"
                war_str += f"{WarResult.WINEMOJI if war.clan_2.result == WarResult.WON else WarResult.LOSEEMOJI if war.clan_2.result == WarResult.LOST else EmojisUI.SPACER}`{str(round(war.clan_2.destruction))+'%':<4} {war.clan_2.stars:<3} {war.clan_2.clean_name[:10]:<10}`\n"

            embed.add_field(
                name=f"__**Round {i}**__",
                value=war_str + "\u200b",
                inline=False
                )
        return embed
    
    async def _content_clan_roster(self):
        get_players = await asyncio.gather(*(self.client.fetch_player(p.tag) for p in self.clan.master_roster),return_exceptions=True)
        roster_players = [p for p in get_players if not isinstance(p,Exception)]
        roster_players.sort(key=lambda x:(x.town_hall.level,x.hero_strength,x.troop_strength,x.spell_strength,x.name),reverse=True)
 
        embed = await clash_embed(
            context=self.ctx,
            title=f"CWL Roster: {self.clan.clean_name} ({self.clan.tag})",
            message=f"**League:** {EmojisLeagues.get(self.league_group.league)} {self.league_group.league}"
                + f"\n**Players in CWL:** {len(self.clan.master_roster)}"
                + f"\n**Average TH:** {self.clan.master_average_th}"
                + "\n"
                + '\u3000'.join(f"{EmojisTownHall.get(th)} {ct}" for th,ct in self.clan.master_lineup.items())
                + "\n\n"
                + f"{EmojisUI.SPACER}`{'':^2}{'BK':>3}{'':^2}{'AQ':>3}{'':^2}{'GW':>3}{'':^2}{'RC':>3}{'':^2}{'':^15}`\n"
                + '\n'.join([
                    f"{EmojisTownHall.get(player.town_hall.level)}"
                    + f"`"
                    + (f"{'':^2}" + (f"{str(getattr(player.get_hero('Barbarian King'),'level','')):>3}" if player.get_hero('Barbarian King') else f"{'':<3}"))
                    + (f"{'':^2}" + (f"{str(getattr(player.get_hero('Archer Queen'),'level','')):>3}" if player.get_hero('Archer Queen') else f"{'':<3}"))
                    + (f"{'':^2}" + (f"{str(getattr(player.get_hero('Grand Warden'),'level','')):>3}" if player.get_hero('Grand Warden') else f"{'':<3}"))
                    + (f"{'':^2}" + (f"{str(getattr(player.get_hero('Royal Champion'),'level','')):>3}" if player.get_hero('Royal Champion') else f"{'':<3}"))
                    + f"\u200E{'':<2}{re.sub('[_*/]','',player.clean_name)[:15]:<15}`"
                    for player in roster_players
                    ]),
            thumbnail=self.clan.badge)
        return embed
    
    async def _content_clan_stats(self):
        war_stats = aClanWarSummary.for_clan(self.clan.tag,self.clan.league_wars)

        embed = await clash_embed(
            context=self.ctx,
            title=f"CWL Stats: {self.clan.clean_name} ({self.clan.tag})",
            message=f"**League:** {EmojisLeagues.get(self.league_group.league)} {self.league_group.league}"
                + f"\n**Players in CWL:** {len(self.clan.master_roster)}"
                + "\n\n"
                + f"{EmojisClash.ATTACK} `{war_stats.attack_count:>3}`\u3000"
                + f"{EmojisClash.UNUSEDATTACK} `{war_stats.unused_attacks:>3}`\u3000"
                + f"{EmojisClash.THREESTARS} `{war_stats.triples:>3} ({str(round((war_stats.triples/war_stats.attack_count)*100))+'%'})`\n"
                + f"{EmojisClash.STAR} `{self.clan.total_score:>4}`\u3000"
                + f"{EmojisClash.DESTRUCTION} `{str(self.clan.total_destruction)+'%':>7}`"
                + f"\n*Only hit rates with 4 or more attacks are shown below.*\u200b",
            thumbnail=self.clan.badge)
        
        roster_townhalls = sorted(list(self.clan.master_lineup.keys()),reverse=True)
        
        async for th_level in AsyncIter(roster_townhalls):
            hitrates = await war_stats.hit_rate_for_th(int(th_level))

            async for hr in AsyncIter(sorted(list(hitrates.keys()),reverse=True)):
                if hitrates[hr]['total'] >= 4:
                    h = hitrates[hr]
                    embed.add_field(
                        name=f"TH{h['attacker']} vs TH{h['defender']}",
                        value=f"{EmojisClash.ATTACK} `{h['total']:^3}`\u3000"
                            + f"{EmojisClash.STAR} `{h['stars']:^3}`\u3000"
                            + f"{EmojisClash.DESTRUCTION} `{h['destruction']:^5}%`"
                            + f"\nHit Rate: {h['triples']/h['total']*100:.0f}% ({h['triples']} {EmojisClash.THREESTARS} / {h['total']} {EmojisClash.ATTACK})"
                            + f"\nAverage: {EmojisClash.STAR} {h['stars']/h['total']:.2f}\u3000{EmojisClash.DESTRUCTION} {h['destruction']/h['total']:.2f}%"
                            + "\n\u200b",
                        inline=False
                        )
        return embed