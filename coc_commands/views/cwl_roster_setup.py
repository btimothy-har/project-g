import discord
import asyncio
import random
import re

from typing import *

from redbot.core import commands
from redbot.core.utils import AsyncIter

from coc_main.api_client import BotClashClient, aClashSeason
from coc_main.cog_coc_client import ClashOfClansClient, aPlayer
from coc_main.coc_objects.events.clan_war_leagues import WarLeaguePlayer, WarLeagueClan

from coc_main.utils.components import clash_embed, DefaultView, DiscordButton, DiscordSelectMenu
from coc_main.utils.constants.coc_emojis import EmojisLeagues, EmojisTownHall
from coc_main.utils.constants.coc_constants import CWLLeagueGroups
from coc_main.utils.constants.ui_emojis import EmojisUI

from coc_main.utils.utils import chunks

bot_client = BotClashClient()

class CWLRosterMenu(DefaultView):
    def __init__(self,
        context:Union[commands.Context,discord.Interaction],
        season:aClashSeason,
        clan:WarLeagueClan):

        self.season = season
        self.clan = clan

        self._modified_to_save = []
        self._ph_finalize_button = None
        self._ph_save_button = None
        self._ph_reset_button = None

        self.members_only = False
        self.max_heroes = False
        self.max_offense = False
        self.not_yet_rostered = False
        self.th_filter = []
        self.group_filter = []
        
        super().__init__(context=context,timeout=300)
    
    @property
    def bot_client(self) -> BotClashClient:
        return bot_client

    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    @property
    def modified_to_save(self) -> List[WarLeaguePlayer]:
        return self._modified_to_save

    ##################################################
    ### OVERRIDE BUILT IN METHODS
    ##################################################
    async def on_timeout(self):
        timeout_embed = await clash_embed(
            context=self.ctx,
            message="Menu timed out.",
            success=False
            )
        if self.message:
            await self.message.edit(embed=timeout_embed,view=None)

        elif isinstance(self.ctx,discord.Interaction):
            if self.ctx.response.is_done():
                await self.ctx.edit_original_response(embed=timeout_embed,view=None)
            else:
                await self.ctx.response.send_message(embed=timeout_embed,view=None)
        else:
            await self.ctx.send(embed=timeout_embed,view=None)
        self.stop_menu()

        for cwl_player in self.modified_to_save:
            cwl_player.load()
    
    ##################################################
    ### MENUS START
    ##################################################
    async def setup_roster(self):        
        self.is_active = True
        await self.add_main_menu()
        embeds = await self.clan_embed()

        if isinstance(self.ctx,discord.Interaction):
            await self.ctx.edit_original_response(embeds=embeds, view=self)
            self.message = await self.ctx.original_response()
        else:
            self.message = await self.ctx.reply(embeds=embeds, view=self)
    
    ##################################################
    ### MAIN BUTTON CALLBACKS
    ##################################################
    async def _callback_home(self,interaction:discord.Interaction,button:DiscordButton):
        if not interaction.response.is_done():
            await interaction.response.defer()

        embeds = await self.clan_embed()
        await self.add_main_menu()
        await interaction.edit_original_response(embeds=embeds,view=self)
    
    async def _callback_main_help(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer(ephemeral=True)

        embed = await clash_embed(
            context=self.ctx,
            title="**CWL Rostering Help**",
            message="This menu allows you, as a roster manager, to view and modify the roster for a participating clan for the upcoming CWL season."
                + "\n\n"
                + "__**On this Menu**__"
                + f"\n\n**{EmojisUI.ADD} ADD PLAYERS**"
                + f"\n> Switches over to the Menu to add individual players to the roster. There will be a separate Help menu available."
                + f"\n\n**{EmojisUI.DOWNLOAD} SAVE**"
                + f"\n> Saves any changes you've made to the roster. This **does not** finalize the roster, can the roster can still be modified."
                + f"\n\n**{EmojisUI.REFRESH} RESET**"
                + f"\n> Removes any changes you've made in this session."
                + f"\n\n**AUTOFILL 15/30**"
                + f"\n> Automatically fills the roster with the highest eligible accounts, sorted by Town Hall and Hero Levels, taking into account registration preference (League Group). "
                + "This will **not** overwrite any accounts that have already been rostered, whether in this Clan or another Clan. "
                + f"\n> \n> You are recommended to autofill with the highest-ranked clan first."
                + f"\n> - Autofill 15 fills up to 15 participants."
                + f"\n> - Autofill 30 fills up to 30 participants."
                + f"\n> \n> **Autofill will not fill participants who registered for Lazy CWL.**"
                + f"\n\n**{EmojisUI.TASK_CHECK} FINALIZE**"
                + f"\n> Finalizes the roster, assigns the CWL roles to members, and makes it available for viewing. Once finalized, a roster cannot be modified through this panel. Rosters can only be finalized with a minimum of 15 participants.",
            )
        await interaction.followup.send(embed=embed,ephemeral=True)

    async def _callback_save(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        for cwl_player in self.modified_to_save:
            cwl_player.save()

        await self.add_main_menu()

        self._ph_save_button.label = "Saved!"
        self._ph_save_button.disabled = True
        
        embeds = await self.clan_embed()
        await interaction.edit_original_response(embeds=embeds,view=self)

    async def _callback_reset(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()

        for cwl_player in self.modified_to_save:
            cwl_player.load()
        
        await self.add_main_menu()
        
        self._ph_reset_button.label = "Roster Reset"
        self._ph_reset_button.disabled = True

        if len(self.clan.participants) < 15:
            self._ph_finalize_button.disabled = True
        else:
            self._ph_finalize_button.disabled = False

        embeds = await self.clan_embed()
        await interaction.edit_original_response(embeds=embeds,view=self)
        
    async def _callback_finalize(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()

        button.label = "Finalizing..."
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        for cwl_player in self.modified_to_save:
            cwl_player.save()
        for cwl_player in self.clan.participants:
            cwl_player.save()
        await self.clan.finalize_roster()

        await self.add_main_menu()
        embeds = await self.clan_embed()
        await interaction.edit_original_response(embeds=embeds,view=self)
        
    async def _callback_exit(self,interaction:discord.Interaction,button:DiscordButton):
        self.stop_menu()
        embed = await clash_embed(
            context=self.ctx,
            message=f"**Menu closed**")
        await interaction.response.edit_message(embed=embed,view=None)

        for cwl_player in self.modified_to_save:
            cwl_player.load()
    
    async def _callback_add_player_menu(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        
        embeds = await self.clan_embed()
        chk = await self.add_player_menu()
        if not chk:
            await interaction.followup.send("Oops! No one seems to have signed up for CWL yet.",ephemeral=True)
            return await self._callback_home(interaction,button)
        await interaction.edit_original_response(embeds=embeds,view=self)

    async def _callback_autofill_15(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        
        eligible_participants = await WarLeaguePlayer.signups_by_group(
            season=self.season,
            group=CWLLeagueGroups.from_league_name(self.clan.league)
            )
        participants_not_rostered = [p for p in eligible_participants if p.roster_clan is None and p.league_group < 99]
        unrostered_players = await asyncio.gather(*(self.client.fetch_player(p.tag) for p in participants_not_rostered))
        async for p in AsyncIter(sorted(unrostered_players,key=lambda p:(p.town_hall.level,p.hero_strength),reverse=True)):
            cwl_player = p.war_league_season(self.season)
            cwl_player.roster_clan = self.clan
            self.modified_to_save.append(cwl_player)
            if len(self.clan.participants) >= 15:
                break
        
        embeds = await self.clan_embed()
        await self.add_main_menu()
        await interaction.edit_original_response(embeds=embeds,view=self)        
    
    async def _callback_autofill_30(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        
        eligible_participants = await WarLeaguePlayer.signups_by_group(
            season=self.season,
            group=CWLLeagueGroups.from_league_name(self.clan.league)
            ) 
        participants_not_rostered = [p for p in eligible_participants if p.roster_clan is None and p.league_group < 99]
        unrostered_players = await asyncio.gather(*(self.client.fetch_player(p.tag) for p in participants_not_rostered))
        async for p in AsyncIter(sorted(unrostered_players,key=lambda p:(p.town_hall.level,p.hero_strength),reverse=True)):
            cwl_player = p.war_league_season(self.season)
            cwl_player.roster_clan = self.clan
            self.modified_to_save.append(cwl_player)
            if len(self.clan.participants) >= 30:
                break
        
        embeds = await self.clan_embed()
        await self.add_main_menu()
        await interaction.edit_original_response(embeds=embeds,view=self)

    async def _callback_remove_player(self,interaction:discord.Interaction,list:DiscordSelectMenu):
        await interaction.response.defer()
        for player_tag in list.values:
            player = WarLeaguePlayer(player_tag,self.season)
            player.roster_clan = None
            self.modified_to_save.append(player)
       
        embeds = await self.clan_embed()
        await self.add_main_menu()
        await interaction.edit_original_response(embeds=embeds,view=self)    

    ##################################################
    ### ADD PLAYER MENU CALLBACKS
    ##################################################
    async def _callback_add_player(self,interaction:discord.Interaction,list:DiscordSelectMenu):
        await interaction.response.defer()
        for player_tag in list.values:
            if len(self.clan.participants) >= 35:
                await interaction.followup.send("This clan already has 35 players in roster. You cannot add more.",ephemeral=True)
                break
            player = WarLeaguePlayer(player_tag,self.season)
            self.modified_to_save.append(player)
            player.roster_clan = self.clan
       
        embeds = await self.clan_embed()
        await self.add_player_menu()
        await interaction.edit_original_response(embeds=embeds,view=self)    
    
    async def _callback_filter_members(self,interaction:discord.Interaction,button:DiscordButton):
        if not interaction.response.is_done():
            await interaction.response.defer()

        if self.members_only:
            self.members_only = False
        else:
            self.members_only = True

        embeds = await self.clan_embed()
        chk = await self.add_player_menu()
        if not chk:
            await interaction.followup.send("There were no players found based on that filter request.",ephemeral=True)
            await self._callback_filter_members(interaction,button)
            return
        await interaction.edit_original_response(embeds=embeds,view=self)
    
    async def _callback_filter_max_heroes(self,interaction:discord.Interaction,button:DiscordButton):
        if not interaction.response.is_done():
            await interaction.response.defer()

        if self.max_heroes:
            self.max_heroes = False
        else:
            self.max_heroes = True

        embeds = await self.clan_embed()
        chk = await self.add_player_menu()
        if not chk:
            await interaction.followup.send("There were no players found based on that filter request.",ephemeral=True)
            await self._callback_filter_max_heroes(interaction,button)
            return
        await interaction.edit_original_response(embeds=embeds,view=self)

    async def _callback_filter_max_offense(self,interaction:discord.Interaction,button:DiscordButton):
        if not interaction.response.is_done():
            await interaction.response.defer()
            
        if self.max_offense:
            self.max_offense = False
        else:
            self.max_offense = True

        embeds = await self.clan_embed()
        chk = await self.add_player_menu()
        if not chk:
            await interaction.followup.send("There were no players found based on that filter request.",ephemeral=True)
            await self._callback_filter_max_offense(interaction,button)
            return
        await interaction.edit_original_response(embeds=embeds,view=self)
    
    async def _callback_filter_not_rostered(self,interaction:discord.Interaction,button:DiscordButton):
        if not interaction.response.is_done():
            await interaction.response.defer()

        if self.not_yet_rostered:
            self.not_yet_rostered = False
        else:
            self.not_yet_rostered = True

        embeds = await self.clan_embed()
        chk = await self.add_player_menu()
        if not chk:
            await interaction.followup.send("There were no players found based on that filter request.",ephemeral=True)
            await self._callback_filter_not_rostered(interaction,button)
            return
        await interaction.edit_original_response(embeds=embeds,view=self)
    
    async def _callback_filter_th(self,interaction:discord.Interaction,list:DiscordSelectMenu):
        await interaction.response.defer()
        self.th_filter = [int(th) for th in list.values]

        embeds = await self.clan_embed()
        chk = await self.add_player_menu()
        if not chk:
            await interaction.followup.send("There were no players found based on that filter request.",ephemeral=True)
            self.th_filter = []
            await self.add_player_menu()
        await interaction.edit_original_response(embeds=embeds,view=self)
    
    async def _callback_filter_group(self,interaction:discord.Interaction,list:DiscordSelectMenu):
        await interaction.response.defer()
        self.group_filter = [int(i) for i in list.values]

        embeds = await self.clan_embed()
        chk = await self.add_player_menu()
        if not chk:
            await interaction.followup.send("There were no players found based on that filter request.",ephemeral=True)
            self.group_filter = []
            await self.add_player_menu()
        await interaction.edit_original_response(embeds=embeds,view=self)
    
    async def _callback_filter_randomize(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()

        embeds = await self.clan_embed()
        await self.add_player_menu()
        await interaction.edit_original_response(embeds=embeds,view=self)
    
    async def _callback_add_help(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer(ephemeral=True)
        embed = await clash_embed(
            context=self.ctx,
            title="**CWL Rostering Help**",
            message="This menu provides options to add individual accounts to the roster. As Discord only displays a maximum of **25** accounts in a drop-down, there are filters provided to help narrow down the list of accounts to choose from."
                + "\n\nBy default, the dropdown menu will exclude participants who have not registered for this League Group (e.g. if this Clan is in League Group A, participants who have registered for League Group B will not be shown)."
                + "\n\nThe percentages shown in the dropdown correspond to a player's strength level: Heroes, Troops, Spells."
                + "\n\n**All filters operate on an AND basis.**"
                + "\n\u200b"
                )
        embed.add_field(
            name=f"{EmojisUI.FILTER} **Filters**",
            value=f"**BY TOWNHALL LEVEL**: Filters accounts by Townhall Level. You can select multiple Townhall Levels."
                + f"\n\n**BY GROUP**: Filters accounts by registered League Group. You can select multiple League Groups."
                + f"\n\n**MEMBERS ONLY**: Only displays Member accounts."
                + f"\n\n**MAX HEROES ONLY**: Only displays accounts with maxed heroes."
                + f"\n\n**MAX OFFENSE ONLY**: Only displays accounts with maxed offense (heroes/troops/spells/pets)."
                + f"\n\n**NOT YET ROSTERED**: Only displays accounts that have not yet been rostered in this Clan or another Clan."
                + f"\n\n**RANDOMIZE**: Randomizes the order of the accounts in the dropdown menu.",
            inline=False
            )
        await interaction.followup.send(embed=embed,ephemeral=True)
    
    ##################################################
    ### MENU HELPERS
    ##################################################
    async def add_main_menu(self):
        self.clear_items()
        #row 1

        if not self.clan.roster_open:
            finalized_button = DiscordButton(
                function=self._callback_home,
                label="This Roster has already been finalized!",
                style=discord.ButtonStyle.secondary,
                row=0
                )
            finalized_button.disabled = True
            self.add_item(finalized_button)
        
        else:
            add_player_button = DiscordButton(
                function=self._callback_add_player_menu,
                label="Add Players",
                emoji=EmojisUI.ADD,
                style=discord.ButtonStyle.secondary,
                row=0
                )
            if len(self.clan.participants) >= 35:
                add_player_button.disabled = True
            self.add_item(add_player_button)  

            self._ph_save_button = DiscordButton(
                function=self._callback_save,
                label="Save",
                emoji=EmojisUI.DOWNLOAD,
                style=discord.ButtonStyle.secondary,
                row=0
                )
            self.add_item(self._ph_save_button)

            self._ph_reset_button = DiscordButton(
                function=self._callback_reset,
                label="Reset",
                emoji=EmojisUI.REFRESH,
                style=discord.ButtonStyle.secondary,
                row=0
                )
            self.add_item(self._ph_reset_button)                      

            autofill_button_15 = DiscordButton(
                function=self._callback_autofill_15,
                label="Autofill 15",
                style=discord.ButtonStyle.secondary,
                row=1
                )
            if len(self.clan.participants) >= 15:
                autofill_button_15.disabled = True
            self.add_item(autofill_button_15)

            autofill_button_30 = DiscordButton(
                function=self._callback_autofill_30,
                label="Autofill 30",
                style=discord.ButtonStyle.secondary,
                row=1
                )
            if len(self.clan.participants) >= 30:
                autofill_button_30.disabled = True
            self.add_item(autofill_button_30)
            #row3

            #remove player
            if len(self.clan.participants) > 0:
                select_participants = []
                async for cwl_player in AsyncIter(self.clan.participants):
                    player = await self.client.fetch_player(cwl_player.tag)
                    select_participants.append(discord.SelectOption(
                        label=str(player),
                        value=player.tag,
                        emoji=player.town_hall.emoji,
                        description=f"{round((player.hero_strength/player.max_hero_strength)*100)}% "
                            + f"| {round((player.troop_strength/player.max_troop_strength)*100)}% "
                            + f"| {round((player.spell_strength/player.max_spell_strength)*100)}% "
                            + (f"| Current Roster: {cwl_player.roster_clan.name[:12]}" if cwl_player.roster_clan else f"| {CWLLeagueGroups.get_description_no_emoji(cwl_player.league_group)}"),
                        default=False))
                
                self.add_item(DiscordSelectMenu(
                    function=self._callback_remove_player,
                    options=select_participants[:15],
                    placeholder=f"Remove Participants (1-15)",
                    min_values=0,
                    max_values=len(select_participants[:15]),
                    row=2
                    ))            
                if len(select_participants) > 15:
                    self.add_item(DiscordSelectMenu(
                        function=self._callback_remove_player,
                        options=select_participants[15:35],
                        placeholder=f"Remove Participants (16-35)",
                        min_values=0,
                        max_values=len(select_participants[15:35]),
                        row=3
                        ))
                    
        self._ph_finalize_button = DiscordButton(
            function=self._callback_finalize,
            label="Finalize",
            emoji=EmojisUI.TASK_CHECK,
            style=discord.ButtonStyle.green,
            row=4
            )
        if len(self.clan.participants) < 15:
            self._ph_finalize_button.disabled = True
        if not self.clan.roster_open:
            self._ph_finalize_button.disabled = True
        self.add_item(self._ph_finalize_button)
                    
        self.add_item(DiscordButton(
            function=self._callback_exit,
            emoji=EmojisUI.LOGOUT,
            label="Exit",
            style=discord.ButtonStyle.red,
            row=4
            ))
        
        self.add_item(DiscordButton(
            function=self._callback_main_help,
            emoji=EmojisUI.HELP,
            label="Help",
            style=discord.ButtonStyle.blurple,
            row=4
            ))
    
    async def add_player_menu(self):
        self.clear_items()
        all_participants, eligible_participants = await self.get_eligible_participants()

        sample = random.sample(eligible_participants,min(25,len(eligible_participants)))
        sampled_players = await asyncio.gather(*(self.client.fetch_player(p.tag) for p in sample))

        select_participants = []
        async for a in AsyncIter(sorted(sampled_players,key=lambda p:(p.town_hall.level,p.hero_strength),reverse=True)):
            cwl_player = a.war_league_season(self.season)
            select_participants.append(discord.SelectOption(
                label=str(a),
                value=a.tag,
                emoji=a.town_hall.emoji,
                description=(f"{round((a.hero_strength/a.max_hero_strength)*100)}% " if a.max_hero_strength > 0 else "0% ")
                    + f"| " + (f"{round((a.troop_strength/a.max_troop_strength)*100)}% " if a.max_troop_strength > 0 else "0% ")
                    + f"| " + (f"{round((a.spell_strength/a.max_spell_strength)*100)}% " if a.max_spell_strength > 0 else "0% ")
                    + (f"| Current Roster: {cwl_player.roster_clan.name[:12]}" if cwl_player.roster_clan else f"| {CWLLeagueGroups.get_description_no_emoji(cwl_player.league_group)}"),
                default=False))
        if len(select_participants) == 0:
            return False
        
        self.add_item(DiscordSelectMenu(
            function=self._callback_add_player,
            options=select_participants,
            placeholder=f"Select Players to add (filtered: {len(select_participants)} of {len(all_participants)}).",
            min_values=0,
            max_values=len(select_participants),
            row=0
            ))        
        #row2
        #filter by th
        select_th = [discord.SelectOption(
            label=f"TH{th}",
            value=th,
            emoji=EmojisTownHall.get(th),
            default=th in self.th_filter)
            for th in sorted(list(set([p.town_hall_level for p in all_participants])),reverse=True)]
        if len(select_th) > 0:
            self.add_item(DiscordSelectMenu(
                function=self._callback_filter_th,
                options=select_th,
                placeholder=f"Filter by TH Level",
                min_values=0,
                max_values=len(select_th),
                row=1
                ))
        
        select_group = [discord.SelectOption(
            label=CWLLeagueGroups.get_description_no_emoji(i),
            value=i,
            emoji=CWLLeagueGroups.league_groups_emoji.get(i),
            default=i in self.group_filter)
            for i in [1,2,9,99]]
        self.add_item(DiscordSelectMenu(
            function=self._callback_filter_group,
            options=select_group,
            placeholder=f"Filter by League Group",
            min_values=0,
            max_values=len(select_group),
            row=2
            ))
        
        #row1
        #filter members only
        self.add_item(DiscordButton(
            function=self._callback_filter_members,
            label="Members Only" if not self.members_only else "All Participants",
            emoji=EmojisUI.FILTER,
            style=discord.ButtonStyle.secondary,
            row=3
            ))
        #filter max heroes only
        self.add_item(DiscordButton(
            function=self._callback_filter_max_heroes,
            label="Max Heroes Only" if not self.max_heroes else "All Hero Levels",
            emoji=EmojisUI.FILTER,
            style=discord.ButtonStyle.secondary,
            row=3
            ))
        #filter max offense only
        self.add_item(DiscordButton(
            function=self._callback_filter_max_offense,
            label="Max Offense Only" if not self.max_offense else "All Offense Levels",
            emoji=EmojisUI.FILTER,
            style=discord.ButtonStyle.secondary,
            row=3
            ))
        
        self.add_item(DiscordButton(
            function=self._callback_filter_not_rostered,
            label="Not Yet Rostered" if not self.not_yet_rostered else "All Players",
            emoji=EmojisUI.FILTER,
            style=discord.ButtonStyle.secondary,
            row=3
            ))        
        
        self.add_item(DiscordButton(
            function=self._callback_home,
            label="Back to Main Page",
            emoji=EmojisUI.GREEN_FIRST,
            style=discord.ButtonStyle.secondary,
            row=4
            ))
        self.add_item(DiscordButton(
            function=self._callback_filter_randomize,
            label="Randomize",
            emoji=EmojisUI.REFRESH,
            style=discord.ButtonStyle.secondary,
            row=4
            ))
        self.add_item(DiscordButton(
            function=self._callback_add_help,
            emoji=EmojisUI.HELP,
            label="Help",
            style=discord.ButtonStyle.blurple,
            row=4
            ))
        return True

    ##################################################
    ### CONTENT HELPERS
    ##################################################
    async def clan_embed(self):
        embed_1 = await clash_embed(
            context=self.ctx,
            title=f"CWL Roster: {self.clan.name} ({self.clan.tag})",
            message=f"**Season:** {self.clan.season.description}"
                + f"\n**League:** {self.clan.league}"
                + f"\n**Group:** {CWLLeagueGroups.get_description(CWLLeagueGroups.from_league_name(self.clan.league))}"
            )
        embed_2 = await clash_embed(
            context=self.ctx,
            show_author=False,
            )
        embed_3 = await clash_embed(
            context=self.ctx,
            show_author=False,
            )
        participants = AsyncIter(self.clan.participants[:35])
        async for i,p in participants.enumerate(start=1):
            player = await self.client.fetch_player(p.tag)
            if i <= 15:
                embed_1.add_field(
                    name=f"{i}\u3000**{player.title}**",
                    value=f"\u200b\u3000\u3000{player.hero_description}",
                    inline=False
                    )
            elif i <= 30:
                embed_2.add_field(
                    name=f"{i}\u3000**{player.title}**",
                    value=f"\u200b\u3000\u3000{player.hero_description}",
                    inline=False
                    )
            elif i <= 35:
                embed_3.add_field(
                    name=f"{i}\u3000**{player.title}**",
                    value=f"\u200b\u3000\u3000{player.hero_description}",
                    inline=False
                    )
            else:
                break        
        if len(embed_1) + len(embed_2) + len(embed_3) >= 6000:
            embed_1 = await clash_embed(
                context=self.ctx,
                title=f"CWL Roster: {self.clan.name} ({self.clan.tag})",
                message=f"**Season:** {self.clan.season.description}"
                    + f"\n**League:** {self.clan.league}"
                    + f"\n**Group:** {CWLLeagueGroups.get_description(CWLLeagueGroups.from_league_name(self.clan.league))}"
                )
            embed_2 = await clash_embed(
                context=self.ctx,
                show_author=False,
                )
            embed_3 = await clash_embed(
                context=self.ctx,
                show_author=False,
                )
            participants = AsyncIter(self.clan.participants[:35])
            async for i,p in participants.enumerate(start=1):
                player = await self.client.fetch_player(p.tag)
                if i <= 15:
                    embed_1.add_field(
                        name=f"{i}\u3000TH{player.town_hall.level}\u3000**{str(player)}**",
                        value=f"\u200b\u3000\u3000{player.hero_description}",
                        inline=False
                        )
                elif i <= 30:
                    embed_2.add_field(
                        name=f"{i}\u3000TH{player.town_hall.level}\u3000**{str(player)}**",
                        value=f"\u200b\u3000\u3000{player.hero_description}",
                        inline=False
                        )
                elif i <= 35:
                    embed_3.add_field(
                        name=f"{i}\u3000TH{player.town_hall.level}\u3000**{str(player)}**",
                        value=f"\u200b\u3000\u3000{player.hero_description}",
                        inline=False
                        )
                else:
                    break
        if len(embed_1) + len(embed_2) + len(embed_3) >= 6000:
            embed_1 = await clash_embed(
                context=self.ctx,
                title=f"CWL Roster: {self.clan.name} ({self.clan.tag})",
                message=f"**Season:** {self.clan.season.description}"
                    + f"\n**League:** {self.clan.league}"
                    + f"\n**Group:** {CWLLeagueGroups.get_description(CWLLeagueGroups.from_league_name(self.clan.league))}"
                )
            embed_2 = await clash_embed(
                context=self.ctx,
                show_author=False,
                )
            embed_3 = await clash_embed(
                context=self.ctx,
                show_author=False,
                )
            participants = AsyncIter(self.clan.participants[:35])
            async for i,p in participants.enumerate(start=1):
                player = await self.client.fetch_player(p.tag)
                if i <= 15:
                    embed_1.add_field(
                        name=f"{i}\u3000TH{player.town_hall.level}\u3000**{str(player)}**",
                        value=f"\u200b\u3000\u3000{player.hero_description_no_emoji}",
                        inline=False
                        )
                elif i <= 30:
                    embed_2.add_field(
                        name=f"{i}\u3000TH{player.town_hall.level}\u3000**{str(player)}**",
                        value=f"\u200b\u3000\u3000{player.hero_description_no_emoji}",
                        inline=False
                        )
                elif i <= 35:
                    embed_3.add_field(
                        name=f"{i}\u3000TH{player.town_hall.level}\u3000**{str(player)}**",
                        value=f"\u200b\u3000\u3000{player.hero_description_no_emoji}",
                        inline=False
                        )
                else:
                    break
        if len(self.clan.participants) > 30:
            return [embed_1,embed_2,embed_3]
        elif len(self.clan.participants) > 15:
            return [embed_1,embed_2]
        return [embed_1]
    
    @staticmethod
    async def clan_roster_embed(ctx:Union[discord.Interaction,commands.Context],clan:WarLeagueClan):

        #Prior to CWL Start:
        #   - Show players in roster + in clan
        #   - Indicate if in clan or not
        #After CWL Start:
        #   - Show players in master roster ONLY
        #   - Indicate if player was rostered
        #   - Indicate if in clan or not

        def evaluate_player_status(player):
            if clan.status in ['CWL Started']:
                if player.tag in [p.tag for p in clan.participants] and player.tag in [p.tag for p in clan.master_roster]:
                    return f"{EmojisUI.YES}"
                if player.tag not in [p.tag for p in clan.participants] and player.tag in [p.tag for p in clan.master_roster]:
                    return f"{EmojisUI.QUESTION}"
            else:
                if player.tag in [p.tag for p in clan.participants]:
                    return f"{EmojisUI.YES}"
            return f"{EmojisUI.SPACER}"

        coc = bot_client.bot.get_cog("ClashOfClansClient")

        collect_embeds = {}
        header_text = ""
            
        header_text += f"**Season:** {clan.season.description}"
        header_text += f"\n**Status:** {clan.status}"
        header_text += f"\n**League:** {EmojisLeagues.get(clan.league)}{clan.league}"
        if clan.status in ["CWL Started"]:
            roster_players = await asyncio.gather(*(coc.fetch_player(p.tag) for p in clan.master_roster))
            header_text += f"\n\n**Participants:** {len([p for p in roster_players if p.clan.tag == clan.tag])} In Clan / {len([p for p in clan.master_roster])} in CWL"
        else:
            roster_players = await asyncio.gather(*(coc.fetch_player(p.tag) for p in clan.participants))
            header_text += f"\n\n**Rostered:** {len([p for p in roster_players if p.clan.tag == clan.tag])} In Clan / {len([p for p in clan.participants])} Rostered"

        header_text += f"\n"
        header_text += (f"{EmojisUI.YES}: a Rostered CWL Player\n" if clan.status in ["Roster Finalized","Roster Pending"] else "")
        header_text += (f"{EmojisUI.YES}: a Rostered CWL Player in the in-game Roster\n" if clan.status in ["CWL Started"] else "")
        header_text += (f"{EmojisUI.QUESTION}: **NOT** Rostered but is in the in-game CWL Roster\n" if clan.status in ["CWL Started"] else "")
        header_text += f"{EmojisUI.LOGOUT}: this player is not in the in-game Clan.\n\n"
            
        if clan.status in ["CWL Started"]:
            ref_members = await asyncio.gather(*(coc.fetch_player(m.tag) for m in clan.master_roster))
        else:
            ref_members = await asyncio.gather(*(coc.fetch_player(m.tag) for m in clan.participants))
            full_clan = await coc.fetch_clan(clan.tag)
            mem_in_clan = await asyncio.gather(*(coc.fetch_player(m.tag) for m in full_clan.members))
                                               
            async for mem in AsyncIter(mem_in_clan):
                if mem.tag not in [p.tag for p in ref_members]:
                    ref_members.append(mem)

        chunked_members = list(chunks(ref_members,25))
        iter_chunks = AsyncIter(chunked_members)
        async for i, members_chunk in iter_chunks.enumerate(start=1):
            member_text = "\n".join([
                (f"{evaluate_player_status(player)}")
                + (f"{EmojisUI.LOGOUT}" if player.clan.tag != clan.tag else f"{EmojisUI.SPACER}")
                + f"{EmojisTownHall.get(player.town_hall.level)}"
                + f"`{re.sub('[_*/]','',player.clean_name)[:13]:<13}`\u3000" + f"`{'':^1}{player.tag:<11}`\u3000"
                + (f"`{'':^1}{getattr(ctx.guild.get_member(player.discord_user),'display_name','Not Found')[:12]:<12}`" if player.discord_user else f"`{'':<13}`")
                for player in members_chunk]
                )
            embed = await clash_embed(
                context=ctx,
                title=f"CWL Roster: {clan.clean_name} ({clan.tag})",
                message=header_text+member_text,
                thumbnail=clan.badge,
                )
            collect_embeds[i] = embed        
        return list(collect_embeds.values())
    
    async def get_eligible_participants(self):
        def eligible_for_rostering(player:aPlayer):
            if not player.war_league_season(self.season).roster_clan or player.war_league_season(self.season).roster_clan.roster_open:
                return True
            return False
        def pred_members_only(player:aPlayer):
            if self.members_only:
                return player.is_member
            return True
        def pred_max_heroes_only(player:aPlayer):
            if self.max_heroes:
                return player.hero_strength == player.max_hero_strength
            return True
        def pred_max_offense_only(player:aPlayer):
            if self.max_offense:
                if player.hero_strength != player.max_hero_strength:
                    return False
                if player.troop_strength != player.max_troop_strength:
                    return False
                if player.spell_strength != player.max_spell_strength:
                    return False
            return True
        def pred_not_yet_rostered(player:aPlayer):
            if self.not_yet_rostered:
                return not player.war_league_season(self.season).roster_clan
            return True
        def pred_townhall_levels(player:aPlayer):
            if len(self.th_filter) > 0:
                return player.town_hall.level in self.th_filter
            return True
        def pred_registration_group(player:aPlayer):
            if len(self.group_filter) > 0:
                return player.war_league_season(self.season).league_group in self.group_filter
            return True
        
        signups = await WarLeaguePlayer.signups_by_season(self.season)
        participants = await asyncio.gather(*(self.client.fetch_player(p.tag) for p in signups))

        all_participants = sorted(participants,key=lambda x:(x.town_hall.level,x.hero_strength),reverse=True)
        eligible_participants = sorted(
            [p for p in participants if eligible_for_rostering(p) and pred_members_only(p) and pred_max_heroes_only(p) and pred_max_offense_only(p) and pred_townhall_levels(p) and pred_not_yet_rostered(p) and pred_registration_group(p)],
            key=lambda x:(x.town_hall.level,x.hero_strength),reverse=True
            )

        return [p.war_league_season(self.season) for p in all_participants], [p.war_league_season(self.season) for p in eligible_participants]