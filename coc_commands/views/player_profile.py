import discord
import pendulum

from typing import *

from numerize import numerize
from redbot.core import commands
from redbot.core.utils import AsyncIter

from coc_main.api_client import BotClashClient
from coc_main.cog_coc_client import ClashOfClansClient, aPlayer, aClanWar, aRaidWeekend
from coc_main.coc_objects.events.war_summary import aClanWarSummary
from coc_main.coc_objects.events.raid_summary import aSummaryRaidStats

from coc_main.utils.components import DefaultView, DiscordButton, DiscordSelectMenu, clash_embed, s_convert_seconds_to_str
from coc_main.utils.constants.ui_emojis import EmojisUI
from coc_main.utils.constants.coc_constants import EmojisClash, EmojisLeagues, EmojisTownHall, WarResult, EmojisEquipment

bot_client = BotClashClient()

class PlayerProfileMenu(DefaultView):
    def __init__(self,
        context:Union[commands.Context,discord.Interaction],
        accounts:List[aPlayer]):
        
        self.accounts = accounts
        self.current_page = "summary"
        self.current_account = self.accounts[0]

        self.current_warstats = None
        self.current_raidstats = None
        
        self.summary_button = DiscordButton(
            function=self._callback_summary,
            emoji=EmojisUI.HOME,
            style=discord.ButtonStyle.blurple
            )
        self.warlog_button = DiscordButton(
            function=self._callback_warlog,
            emoji=EmojisClash.CLANWAR,
            style=discord.ButtonStyle.gray
            )
        self.raidlog_button = DiscordButton(
            function=self._callback_raidlog,
            emoji=EmojisClash.CAPITALRAID,
            style=discord.ButtonStyle.gray
            )
        self.trooplevels_button = DiscordButton(
            function=self._callback_trooplevels,
            emoji=EmojisClash.LABORATORY,
            style=discord.ButtonStyle.gray
            )
        self.blacksmith_button = DiscordButton(
            function=self._callback_heroequipment,
            emoji=EmojisClash.BLACKSMITH,
            style=discord.ButtonStyle.gray
            )
        
        self.account_link_button = None
        self.account_dropdown = None
        
        super().__init__(context,timeout=300)

        self.add_item(self.summary_button)
        self.add_item(self.warlog_button)
        self.add_item(self.raidlog_button)
        self.add_item(self.trooplevels_button)
        self.add_item(self.blacksmith_button)
        self._build_dynamic_menu()
    
    @property
    def client(self) -> ClashOfClansClient:
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
        if len(self.accounts) == 0:
            embed = await clash_embed(
                context=self.ctx,
                message="I couldn't find any accounts to show. Check your input, maybe?",
                success=False
                )
            if isinstance(self.ctx,discord.Interaction):
                await self.ctx.edit_original_response(embed=embed,view=None)
                self.message = await self.ctx.original_response()
            else:
                self.message = await self.ctx.reply(embed=embed,view=None)
            return
        
        self.current_warstats = aClanWarSummary.for_player(
            player_tag=self.current_account.tag,
            war_log=await aClanWar.for_player(
                player_tag=self.current_account.tag,
                season=bot_client.current_season
                ))
        
        self.current_raidstats = aSummaryRaidStats.for_player(
            player_tag=self.current_account.tag,
            raid_log=await aRaidWeekend.for_player(
                player_tag=self.current_account.tag,
                season=bot_client.current_season
                ))
            
        self.is_active = True
        self.summary_button.disabled = True
        embed = await self._summary_embed()
        if isinstance(self.ctx,discord.Interaction):
            await self.ctx.edit_original_response(embed=embed,view=self)
            self.message = await self.ctx.original_response()
        else:
            self.message = await self.ctx.reply(embed=embed,view=self)
    
    ##################################################
    ### CALLBACKS
    ##################################################
    async def _callback_summary(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()

        self.summary_button.disabled = True
        self.warlog_button.disabled = False
        self.raidlog_button.disabled = False
        self.trooplevels_button.disabled = False
        self.blacksmith_button.disabled = False

        self.current_page = "summary"
        embed = await self._summary_embed()
        await interaction.edit_original_response(embed=embed,view=self)
    
    async def _callback_warlog(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()

        self.summary_button.disabled = False
        self.warlog_button.disabled = True
        self.raidlog_button.disabled = False
        self.trooplevels_button.disabled = False
        self.blacksmith_button.disabled = False

        self.current_page = "warlog"
        embed = await self._warlog_embed()
        await interaction.edit_original_response(embed=embed,view=self)

    async def _callback_raidlog(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()

        self.summary_button.disabled = False
        self.warlog_button.disabled = False
        self.raidlog_button.disabled = True
        self.trooplevels_button.disabled = False
        self.blacksmith_button.disabled = False

        self.current_page = "raidlog"
        embed = await self._raidlog_embed()
        await interaction.edit_original_response(embed=embed,view=self)

    async def _callback_trooplevels(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()

        self.summary_button.disabled = False
        self.warlog_button.disabled = False
        self.raidlog_button.disabled = False
        self.trooplevels_button.disabled = True
        self.blacksmith_button.disabled = False

        self.current_page = "trooplevels"
        embed = await self._laboratorylevels_embed()
        await interaction.edit_original_response(embed=embed,view=self)

    async def _callback_heroequipment(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()

        self.summary_button.disabled = False
        self.warlog_button.disabled = False
        self.raidlog_button.disabled = False
        self.trooplevels_button.disabled = False
        self.blacksmith_button.disabled = True

        self.current_page = "blacksmith"
        embed = await self._blacksmith_embed()
        await interaction.edit_original_response(embed=embed,view=self)
    
    async def _callback_select_account(self,interaction:discord.Interaction,menu:DiscordSelectMenu):
        await interaction.response.defer()
        self.current_account = [account for account in self.accounts if account.tag == menu.values[0]][0]

        self.current_warstats = aClanWarSummary.for_player(
            player_tag=self.current_account.tag,
            war_log=await aClanWar.for_player(
                player_tag=self.current_account.tag,
                season=bot_client.current_season
                ))
        
        self.current_raidstats = aSummaryRaidStats.for_player(
            player_tag=self.current_account.tag,
            raid_log=await aRaidWeekend.for_player(
                player_tag=self.current_account.tag,
                season=bot_client.current_season
                ))

        self._build_dynamic_menu()
            
        if self.current_page == "warlog":
            embed = await self._warlog_embed()
        elif self.current_page == "raidlog":
            embed = await self._raidlog_embed()
        elif self.current_page == "trooplevels":
            embed = await self._laboratorylevels_embed()
        elif self.current_page == "blacksmith":
            embed = await self._blacksmith_embed()
        else:
            embed = await self._summary_embed()
        
        await interaction.edit_original_response(embed=embed,view=self)
    
    ##################################################
    ### HELPERS
    ##################################################
    async def _summary_embed(self):
        player = self.current_account

        current_season = await player.get_current_season()

        discord_user = self.guild.get_member(player.discord_user)
        embed = await clash_embed(
            context=self.ctx,
            title=f"**{player}**",
            message=(f"{player.member_description}\n" if player.is_member else "")
                + f"{EmojisClash.EXP} {player.exp_level}\u3000{EmojisClash.CLAN} {player.clan_description}\n"
                + (f"{EmojisUI.TIMER} Last Seen: <t:{int(max([i.int_timestamp for i in current_season.last_seen]))}:R>\n" if len(current_season.last_seen) > 0 else "")
                + (f"{player.discord_user_str}\u3000{EmojisUI.ELO} {player.war_elo:,}\n" if player.discord_user else ""),
            thumbnail=getattr(discord_user,'display_avatar',None),
            )
        embed.add_field(
            name="**Home Village**",
            value=f"{player.town_hall.emoji} {player.town_hall.description}\u3000{EmojisLeagues.get(player.league.name)} {player.trophies} (best: {player.best_trophies})\n"
                + f"**Heroes**\n{player.hero_description}\n"
                + f"**Strength**\n"
                + f"{EmojisClash.BOOKFIGHTING} {player.troop_strength} / {player.max_troop_strength} *(rushed: {player.troop_rushed_pct}%)*\n"
                + (f"{EmojisClash.BOOKSPELLS} {player.spell_strength} / {player.max_spell_strength} *(rushed: {player.spell_rushed_pct}%)*\n" if player.town_hall.level >= 5 else "")
                + (f"{EmojisClash.BOOKHEROES} {player.hero_strength} / {player.max_hero_strength} *(rushed: {player.hero_rushed_pct}%)*\n" if player.town_hall.level >= 7 else "")
                + (f"**Currently Boosting**\n" + " ".join([troop.emoji for troop in player.super_troops]) + "\n" if len(player.super_troops) > 0 else "")
                + f"\u200b",
            inline=False
            )
        
        if player.is_member:
            td, th, tm, ts = s_convert_seconds_to_str(current_season.time_in_home_clan)
            embed.add_field(
                name="**Current Season Stats with The Guild**",
                value=(f"{player.home_clan.emoji} {td} days spent in {player.home_clan.name}\n\n" if player.home_clan else "")
                    + f"**Activity**\n"
                    + f"{EmojisClash.ATTACK} {current_season.attacks}\u3000{EmojisClash.DEFENSE} {current_season.defenses}\n"
                    + f"**Donations**\n"
                    + f"{EmojisClash.DONATIONSOUT} {current_season.donations_sent}\u3000{EmojisClash.DONATIONSRCVD} {current_season.donations_rcvd}\n"
                    + f"**Loot**\n"
                    + f"{EmojisClash.GOLD} {current_season.loot_gold}\u3000{EmojisClash.ELIXIR} {current_season.loot_elixir}\u3000{EmojisClash.DARKELIXIR} {current_season.loot_darkelixir}\n"
                    + f"**Clan Capital**\n"
                    + f"{EmojisClash.CAPITALGOLD} {current_season.capitalcontribution}\u3000{EmojisClash.CAPITALRAID} {self.current_raidstats.raids_participated}\u3000{EmojisClash.RAIDMEDALS} {self.current_raidstats.medals_earned:,}\n"
                    + f"**Clan War Performance**\n"
                    + f"{EmojisClash.CLANWAR} {self.current_warstats.wars_participated}\u3000{EmojisClash.STAR} {self.current_warstats.offense_stars}\u3000{EmojisClash.THREESTARS} {self.current_warstats.triples}\u3000{EmojisClash.UNUSEDATTACK} {self.current_warstats.unused_attacks}\n"
                    + f"**Clan Games**\n"
                    + f"{EmojisClash.CLANGAMES} {current_season.clangames.score:,} "
                    + (f"{EmojisUI.TIMER} {current_season.clangames.time_to_completion}\n" if current_season.clangames.ending_time else "\n")
                    + f"\u200b",
                inline=False
                )
        else:
            embed.add_field(
                name="**Season Activity**",
                value=f"**Attacks Won**\n{EmojisClash.ATTACK} {player.attack_wins}\n"
                    + f"**Defenses Won**\n{EmojisClash.DEFENSE} {player.defense_wins}\n"
                    + f"**Donations**\n{EmojisClash.DONATIONSOUT} {player.donations}\u3000{EmojisClash.DONATIONSRCVD} {player.received}\n",
                inline=False
                )
            embed.add_field(
                name="**Lifetime Achievements**",
                value=f"**Loot**\n"
                    + f"{EmojisClash.GOLD} {numerize.numerize(player.get_achievement('Gold Grab').value,1)}\u3000{EmojisClash.ELIXIR} {numerize.numerize(player.get_achievement('Elixir Escapade').value,1)}\u3000{EmojisClash.DARKELIXIR} {numerize.numerize(player.get_achievement('Heroic Heist').value,1)}\n"
                    + f"**Clan Capital**\n"
                    + f"{EmojisClash.CAPITALGOLD} {numerize.numerize(player.clan_capital_contributions,1)}\u3000<:CapitalRaids:1034032234572816384> {numerize.numerize(player.get_achievement('Aggressive Capitalism').value,1)}\n"
                    + f"**War Stats**\n"
                    + f"{EmojisClash.STAR} {player.war_stars:,}\u3000{EmojisClash.WARLEAGUES} {player.get_achievement('War League Legend').value:,}\n"
                    + f"**Clan Games**\n"
                    + f"{EmojisClash.CLANGAMES} {player.get_achievement('Games Champion').value:,}\n"
                    + f"\u200b",
                inline=False
                )
        return embed

    async def _warlog_embed(self):
        player = self.current_account

        embed = await clash_embed(
            context=self.ctx,
            title=f"**War Log: {player}**",
            message=f"**Stats for: {bot_client.current_season.description} Season**\n"
                + f"{EmojisClash.CLANWAR} `{self.current_warstats.wars_participated:^3}`\u3000"
                + f"{EmojisClash.THREESTARS} `{self.current_warstats.triples:^3}`\u3000"
                + f"{EmojisClash.UNUSEDATTACK} `{self.current_warstats.unused_attacks:^3}`\n"
                + f"{EmojisClash.ATTACK}\u3000{EmojisClash.STAR} `{self.current_warstats.offense_stars:<3}`\u3000{EmojisClash.DESTRUCTION} `{self.current_warstats.offense_destruction:>3}%`\n"
                + f"{EmojisClash.DEFENSE}\u3000{EmojisClash.STAR} `{self.current_warstats.defense_stars:<3}`\u3000{EmojisClash.DESTRUCTION} `{self.current_warstats.defense_destruction:>3}%`\n"
                + f"\u200b"
            )
        war_count = 0
        async for war in AsyncIter(self.current_warstats.war_log):
            if war_count >= 5:
                break

            war_member = war.get_member(player.tag)
            war_attacks = sorted(war_member.attacks,key=lambda x:(x.order))
            attack_str = "\n".join(
                [f"{EmojisClash.ATTACK}\u3000{EmojisTownHall.get(att.attacker.town_hall)} vs {EmojisTownHall.get(att.defender.town_hall)}\u3000{EmojisClash.STAR} `{att.stars:^3}`\u3000{EmojisClash.DESTRUCTION} `{att.destruction:>3}%`"
                for att in war_attacks]
                )
            embed.add_field(
                name=f"{war_member.clan.emoji} {war_member.clan.clean_name} vs {war_member.opponent.clean_name}",
                value=f"{WarResult.emoji(war_member.clan.result)}\u3000{EmojisClash.ATTACK} `{len(war_member.attacks):^3}`\u3000{EmojisClash.UNUSEDATTACK} `{war_member.unused_attacks:^3}`"
                    + (f"\u3000{EmojisUI.ELO} `{round(sum([att.elo_effect for att in war_member.attacks]),1):^3}`\n" if war_member.clan.is_alliance_clan else "\n")
                    + (f"*War Ends <t:{war.end_time.int_timestamp}:R>.*\n" if war.start_time < pendulum.now() < war.end_time else "")
                    + (f"*War Starts <t:{war.start_time.int_timestamp}:R>.*\n" if war.start_time > pendulum.now() else "")
                    + (f"{attack_str}\n" if len(war_attacks) > 0 else "")
                    + "\u200b",
                inline=False
                )
            war_count += 1
        return embed
    
    async def _raidlog_embed(self):
        player = self.current_account

        embed = await clash_embed(
            context=self.ctx,
            title=f"**Raid Log: {player}**",
            message=f"**Stats for: {bot_client.current_season.description} Season**\n"
                + f"{EmojisClash.CAPITALRAID} `{self.current_raidstats.raids_participated:^3}`\u3000"
                + f"{EmojisClash.ATTACK} {self.current_raidstats.raid_attacks:^3}\u3000"
                + f"{EmojisClash.UNUSEDATTACK} {self.current_raidstats.unused_attacks:^3}\n"
                + f"{EmojisClash.CAPITALGOLD} {self.current_raidstats.resources_looted:>6,}\u3000"
                + f"{EmojisClash.RAIDMEDALS} {self.current_raidstats.medals_earned:>5,}\n"
                + f"\u200b"
            )
        raid_count = 0
        async for raid in AsyncIter(self.current_raidstats.raid_log):
            r_clan = await self.client.fetch_clan(raid.clan_tag)
            if raid_count >= 5:
                break

            raid_member = raid.get_member(player.tag)
            raid_attacks = '\n'.join(
                [f"> `{att.district.name:<20}` {EmojisClash.STAR} `{att.stars:^3}`\u3000{EmojisClash.DESTRUCTION} `{att.destruction:>3}%`"
                 for att in raid_member.attacks]
                 )            
            embed.add_field(
                name=(f"{r_clan.emoji}" if raid.is_alliance_raid else "")
                    + f"**{r_clan.clean_name} {raid.start_time.format('DD MMM YYYY')}**",
                value=f"{EmojisClash.ATTACK} {raid_member.attack_count} / 6\u3000"
                    + f"{EmojisClash.CAPITALGOLD} {raid_member.capital_resources_looted:,}\u3000"
                    + f"{EmojisClash.RAIDMEDALS} {raid_member.medals_earned:,}\n"
                    + (f"{raid_attacks}\n" if len(raid_member.attacks) else "")
                    + f"\u200b",
                inline=False
                )
            raid_count += 1        
        return embed

    async def _laboratorylevels_embed(self):
        player = self.current_account

        embed = await clash_embed(
            context=self.ctx,
            title=f"**Laboratory Levels: {player}**",
            message=f"Hero & Troop Levels for: {EmojisTownHall.get(player.town_hall.level)} TH {player.town_hall.level}\n"
                + f"*`Italicized levels indicate rushed levels.`*"
            )
        
        if len(player.heroes) > 0:
            hero_list = []
            for i, hero in enumerate(player.heroes):
                hero_t = f"{hero.emoji}{'*' if hero.is_rushed else ''}`{str(hero.level) + ' / ' + str(hero.max_level):^7}`{'*' if hero.is_rushed else ''}"
                if i % 2 == 0:
                    hero_list.append(hero_t)
                else:
                    hero_list[-1] += "\u200b" + hero_t
            embed.add_field(name="Heroes",value="\n".join(hero_list)+"\n\u200b",inline=False)
        
        if len(player.pets) > 0:
            pet_list = []
            for i, pet in enumerate(player.pets):
                pet_t = f"{pet.emoji}{'*' if pet.is_rushed else ''}`{str(pet.level) + ' / ' + str(pet.max_level):^7}`{'*' if pet.is_rushed else ''}"
                if i % 2 == 0:
                    pet_list.append(pet_t)
                else:
                    pet_list[-1] += "\u200b" + pet_t
            embed.add_field(name="Hero Pets",value="\n".join(pet_list)+"\n\u200b",inline=False)
        
        if len(player.elixir_troops) > 0:
            elixir_troop_list = []
            for i, troop in enumerate(player.elixir_troops,start=1):
                troop_t = f"{troop.emoji}{'*' if troop.is_rushed else ''}`{str(troop.level) + ' / ' + str(troop.max_level):^7}`{'*' if troop.is_rushed else ''}"
                if i % 3 == 1:
                    elixir_troop_list.append(troop_t)
                else:
                    elixir_troop_list[-1] += troop_t
            embed.add_field(name="Elixir Troops",value="\n".join(elixir_troop_list)+"\n\u200b",inline=False)
        
        if len(player.darkelixir_troops) > 0:
            darkelixir_troop_list = []
            for i, troop in enumerate(player.darkelixir_troops,start=1):
                troop_t = f"{troop.emoji}{'*' if troop.is_rushed else ''}`{str(troop.level) + ' / ' + str(troop.max_level):^7}`{'*' if troop.is_rushed else ''}"
                if i % 3 == 1:
                    darkelixir_troop_list.append(troop_t)
                else:
                    darkelixir_troop_list[-1] += troop_t
            embed.add_field(name="Dark Elixir Troops",value="\n".join(darkelixir_troop_list)+"\n\u200b",inline=False)
        
        if len(player.siege_machines) > 0:
            siege_machine_list = []
            for i, siege_machine in enumerate(player.siege_machines,start=1):
                siege_machine_t = f"{siege_machine.emoji}{'*' if siege_machine.is_rushed else ''}`{str(siege_machine.level) + ' / ' + str(siege_machine.max_level):^7}`{'*' if siege_machine.is_rushed else ''}"
                if i % 3 == 1:
                    siege_machine_list.append(siege_machine_t)
                else:
                    siege_machine_list[-1] += siege_machine_t
            embed.add_field(name="Siege Machines",value="\n".join(siege_machine_list)+"\n\u200b",inline=False)
        
        if len(player.elixir_spells) > 0:
            elixir_spell_list = []
            for i, spell in enumerate(player.elixir_spells,start=1):
                spell_t = f"{spell.emoji}{'*' if spell.is_rushed else ''}`{str(spell.level) + ' / ' + str(spell.max_level):^7}`{'*' if spell.is_rushed else ''}"
                if i % 3 == 1:
                    elixir_spell_list.append(spell_t)
                else:
                    elixir_spell_list[-1] += spell_t
            embed.add_field(name="Elixir Spells",value="\n".join(elixir_spell_list)+"\n\u200b",inline=False)
        
        if len(player.darkelixir_spells) > 0:
            darkelixir_spell_list = []
            for i, spell in enumerate(player.darkelixir_spells,start=1):
                spell_t = f"{spell.emoji}{'*' if spell.is_rushed else ''}`{str(spell.level) + ' / ' + str(spell.max_level):^7}`{'*' if spell.is_rushed else ''}"
                if i % 3 == 1:
                    darkelixir_spell_list.append(spell_t)
                else:
                    darkelixir_spell_list[-1] += spell_t
            embed.add_field(name="Dark Elixir Spells",value="\n".join(darkelixir_spell_list)+"\n\u200b",inline=False)
        return embed

    async def _blacksmith_embed(self):
        player = self.current_account

        embed = await clash_embed(
            context=self.ctx,
            title=f"Hero Equipment: {player}",
            message=f"Max levels are provided as the maximum possible in-game, not by Townhall level."
            )
        
        if player.town_hall.level >= 8:
            eq_list = [f"{EmojisEquipment.get(e.name)} {e.level} / {e.max_level}" for e in player.equipment if e.hero == 'Barbarian King']
            embed.add_field(
                name=f"**Barbarian King**",
                value="\n".join(eq_list)+"\n\u200b",
                inline=True
                )
        
        if player.town_hall.level >= 9:
            eq_list = [f"{EmojisEquipment.get(e.name)} {e.level} / {e.max_level}" for e in player.equipment if e.hero == 'Archer Queen']
            embed.add_field(
                name=f"**Archer Queen**",
                value="\n".join(eq_list)+"\n\u200b",
                inline=True
                )
        
        if player.town_hall.level >= 11:
            eq_list = [f"{EmojisEquipment.get(e.name)} {e.level} / {e.max_level}" for e in player.equipment if e.hero == 'Grand Warden']
            embed.add_field(
                name=f"**Grand Warden**",
                value="\n".join(eq_list)+"\n\u200b",
                inline=True
                )
        
        if player.town_hall.level >= 13:
            eq_list = [f"{EmojisEquipment.get(e.name)} {e.level} / {e.max_level}" for e in player.equipment if e.hero == 'Royal Champion']
            embed.add_field(
                name=f"**Royal Champion**",
                value="\n".join(eq_list)+"\n\u200b",
                inline=True
                )
        return embed      

    def _build_dynamic_menu(self):
        if self.account_link_button:
            self.remove_item(self.account_link_button)
        self.account_link_button = discord.ui.Button(
            label="Open In-Game",
            style=discord.ButtonStyle.link,
            url=self.current_account.share_link
            )        
        self.add_item(self.account_link_button)

        if self.account_dropdown:
            self.remove_item(self.account_dropdown)
        if len(self.accounts) > 1:
            select_options = [discord.SelectOption(
                label=f"{account.name} | {account.tag}",
                value=account.tag,
                description=f"{account.clan_description}" + " | " + f"{account.alliance_rank}" + (f" ({account.home_clan.abbreviation})" if getattr(account.home_clan,'tag',None) else ""),
                emoji=account.town_hall.emoji,
                default=account.tag == self.current_account.tag)
                for account in self.accounts
                ]
            self.account_dropdown = DiscordSelectMenu(
                function=self._callback_select_account,
                options=select_options,
                placeholder="Select an account to view.",
                min_values=1,
                max_values=1
                )            
            self.add_item(self.account_dropdown)
