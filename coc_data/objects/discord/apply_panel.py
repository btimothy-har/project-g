import asyncio
import discord
import pendulum

from typing import *
from mongoengine import *
from numerize import numerize

from redbot.core.utils import AsyncIter

from coc_client.api_client import BotClashClient

from ..players.player import aPlayer
from ..clans.clan import aClan

from ...utilities.components import *

from ...constants.coc_constants import *
from ...constants.coc_emojis import *
from ...constants.ui_emojis import *
from ...exceptions import *

##################################################
#####
##### ATTRIBUTES
#####
##################################################
class db_GuildApplyPanel(Document):
    #ID using format {'guild':int,'channel':123}
    panel_id = DictField(primary_key=True,required=True)

    server_id = IntField(default=0,required=True)
    channel_id = IntField(default=0,required=True)
    message_id = IntField(default=0)

    #config
    select_clans = BooleanField(default=True)
    
    #tickettool link
    ticket_prefix = StringField(default="")
    listener_channel = IntField(default=0)

    #questions
    text_q1 = StringField(default="")
    placeholder_q1 = StringField(default="")
    text_q2 = StringField(default="")
    placeholder_q2 = StringField(default="")
    text_q3 = StringField(default="")
    placeholder_q3 = StringField(default="")
    text_q4 = StringField(default="")
    placeholder_q4 = StringField(default="")

class db_ClanApplication(Document):
    applicant_id = IntField(required=True)
    guild_id = IntField(required=True)
    created = IntField(required=True)
    tags = ListField(StringField(),default=[])
    clans = ListField(StringField(),default=[])

    answer_q1 = ListField(StringField(),default=[])
    answer_q2 = ListField(StringField(),default=[])
    answer_q3 = ListField(StringField(),default=[])
    answer_q4 = ListField(StringField(),default=[])

    ticket_channel = IntField(default=0)
    bot_prefix = StringField(default="")

##################################################
#####
##### PANEL
#####
##################################################
class GuildApplicationPanel():

    @staticmethod
    async def start_rtd_onboarding(interaction:discord.Interaction):
        rtd_clan = await aClan.create(tag='#2L90QPRL9')
        view = ClanApplyMenuUser(interaction,[rtd_clan])
        await view.rtd_onboarding()

    @staticmethod
    async def start_user_application(interaction:discord.Interaction,clan_tags:Optional[list[str]]=[]):
        clans = [await aClan.create(tag=tag) for tag in clan_tags]
        view = ClanApplyMenuUser(interaction,clans)
        await view.start()

    def __init__(self,database_entry:db_GuildApplyPanel):
        self.client = BotClashClient()
        self.bot = self.client.bot
        
        self.id = database_entry.panel_id
        
        self.guild_id = database_entry.server_id
        self.channel_id = database_entry.channel_id
        self.message_id = database_entry.message_id

        self.can_user_select_clans = database_entry.select_clans

        self.tickettool_prefix = database_entry.ticket_prefix
        self._tickettool_channel = database_entry.listener_channel

        self.text_q1 = database_entry.text_q1
        self.placeholder_q1 = database_entry.placeholder_q1
        self.text_q2 = database_entry.text_q2
        self.placeholder_q2 = database_entry.placeholder_q2
        self.text_q3 = database_entry.text_q3
        self.placeholder_q3 = database_entry.placeholder_q3
        self.text_q4 = database_entry.text_q4
        self.placeholder_q4 = database_entry.placeholder_q4
    
    def __str__(self):
        return f"Application Panel (Channel: {getattr(self.channel,'name','Unknown Channel')})"
    
    def save(self):
        db_panel = db_GuildApplyPanel(
            panel_id = self.id,
            server_id = self.guild_id,
            channel_id = self.channel_id,
            message_id = self.message_id,
            select_clans = self.can_user_select_clans,
            ticket_prefix = self.tickettool_prefix,
            listener_channel = self._tickettool_channel,
            text_q1 = self.text_q1,
            placeholder_q1 = self.placeholder_q1,
            text_q2 = self.text_q2,
            placeholder_q2 = self.placeholder_q2,
            text_q3 = self.text_q3,
            placeholder_q3 = self.placeholder_q3,
            text_q4 = self.text_q4,
            placeholder_q4 = self.placeholder_q4
            )
        db_panel.save()
    
    def delete(self):
        db_GuildApplyPanel.objects(panel_id=self.id).delete()
    
    @classmethod
    def get_from_id(cls,panel_id:dict):
        try:
            panel = db_GuildApplyPanel.objects.get(panel_id=panel_id)
        except DoesNotExist:
            return None
        return cls(panel)

    @classmethod
    def get_guild_panels(cls,guild_id:int):
        return [cls(link) for link in db_GuildApplyPanel.objects(server_id=guild_id)]
    
    @classmethod
    def get_panel(cls,guild_id:int,channel_id:int):
        try:
            panel = db_GuildApplyPanel.objects.get(
                server_id=guild_id,
                channel_id=channel_id
                )
        except DoesNotExist:
            return None
        return cls(panel)
    
    @classmethod
    async def create(cls,guild_id:int,channel_id:int):
        panel_id = {'guild':guild_id,'channel':channel_id}

        try:
            panel = db_GuildApplyPanel.objects.get(
                server_id=guild_id,
                channel_id=channel_id
                )
        except DoesNotExist:
            panel = db_GuildApplyPanel(
                panel_id = panel_id,
                server_id = guild_id,
                channel_id = channel_id
                )
            panel.save()        
        return cls(panel)

    @property
    def guild(self):
        return self.bot.get_guild(self.guild_id)
    
    @property
    def channel(self):
        if not self.guild:
            return None
        return self.guild.get_channel(self.channel_id)

    @property
    def listener_channel(self):
        return self.guild.get_channel(self._tickettool_channel)
    
    async def fetch_message(self):
        if self.channel:
            try:
                return await self.channel.fetch_message(self.message_id)
            except discord.NotFound:
                pass
        return None
    
    async def send_to_discord(self,clans:aClan,embed:discord.Embed):
        try:
            if not self.channel:
                self.delete()
                return
            
            apply_view = ClanApplyMenu(self,clans)
            message = await self.fetch_message()
            if not message:
                message = await self.channel.send(embed=embed,view=apply_view)
                self.message_id = message.id
                self.save()
            else:
                message = await message.edit(embed=embed,view=apply_view)
        
        except Exception as exc:
            self.client.cog.coc_main_log.exception(
                f"Error sending Application Panel to Discord: {self.guild.name} {getattr(self.channel,'name','Unknown Channel')}. {exc}"
                )

class ClanApplyMenu(discord.ui.View):
    def __init__(self,panel:GuildApplicationPanel,list_of_clans:list[aClan]):
        
        self.panel = panel
        self.clans = list_of_clans
        super().__init__(timeout=None)

        if self.panel.can_user_select_clans:
            self.add_item(self.select_menu())
        else:
            self.add_item(self.apply_button())

    async def on_timeout(self):
        pass

    def select_menu(self):
        dropdown_options = [discord.SelectOption(
            label=f"{clan.name}" + " | " + f"{clan.tag}",
            value=clan.tag,
            emoji=clan.emoji
            )
            for clan in self.clans
            ]
        if self.panel.guild_id == 1132581106571550831:
            dropdown_options.append(discord.SelectOption(
                label=f"I am an existing member of WOL/RTD.",
                value="rtd_onboarding"
                ))
        dropdown_menu = DiscordSelectMenu(
            function=self._callback_select_clan,
            options=dropdown_options,
            placeholder="Select one or more Clan(s) to apply to.",
            min_values=1,
            max_values=len(dropdown_options)
            )
        return dropdown_menu

    async def _callback_select_clan(self,interaction:discord.Interaction,select:discord.ui.Select):
        await interaction.response.defer(ephemeral=True)

        if 'rtd_onboarding' in select.values:            
            await GuildApplicationPanel.start_rtd_onboarding(interaction)
        else:
            await GuildApplicationPanel.start_user_application(interaction,select.values)

        self.clear_items()
        if self.panel.can_user_select_clans:
            self.add_item(self.select_menu())
        else:
            self.add_item(self.apply_button())

        await interaction.followup.edit_message(interaction.message.id,view=self)
    
    def apply_button(self):
        apply_button = DiscordButton(
            function=self._callback_apply,
            label="Click to Apply",
            style=discord.ButtonStyle.blurple
            )
        return apply_button
    
    async def _callback_apply(self,interaction:discord.Interaction,select:discord.ui.Button):
        await interaction.response.defer(ephemeral=True)        
        await GuildApplicationPanel.start_user_application(interaction)

        self.clear_items()
        if self.panel.can_user_select_clans:
            self.add_item(self.select_menu())
        else:
            self.add_item(self.apply_button())

        await interaction.followup.edit_message(interaction.message.id,view=self)

class ClanApplyMenuUser(DefaultView):
    def __init__(self,
        context:discord.Interaction,
        apply_clans:Optional[list[aClan]]):

        self.client = BotClashClient()

        try:
            self.panel = GuildApplicationPanel.get_panel(
                guild_id=context.guild.id,
                channel_id=context.channel.id
                )
        except DoesNotExist:
            self.panel = None
        self.member = self.client.cog.get_member(context.user.id,context.guild.id)
        self.clans = apply_clans        

        super().__init__(context,timeout=300)
    
    async def on_timeout(self):
        try:
            await self.ctx.followup.edit_message(self.message.id,content=f"Sorry, you timed out!",view=None)
        except:
            pass        
        self.stop_menu()

    ##################################################
    #####
    ##### STANDARD APPLICATION FUNCTIONS
    #####
    ##################################################
    async def start(self):
        self.is_active = True
        available_accounts = []
        dropdown_options = []

        async for a in AsyncIter(self.member.account_tags[:20]):
            try:
                player = await self.client.cog.fetch_player(tag=a)
            except Exception:
                pass
            else:
                available_accounts.append(player)
        
        dropdown_options.extend([
            discord.SelectOption(
                label=f"{player.name}" + " | " + f"{player.tag}",
                value=player.tag,
                emoji=player.town_hall.emoji
                )
            for player in sorted(available_accounts,key=lambda x:(x.town_hall.level,x.exp_level),reverse=True)
            ])
        dropdown_options.append(
            discord.SelectOption(
                label=f"The account I want to apply with is not listed.",
                value="not_listed"
                )
            )
        dropdown_menu = DiscordSelectMenu(
            function=self._callback_application,
            options=dropdown_options,
            placeholder="Select one or more Account(s) to apply with.",
            min_values=1,
            max_values=len(dropdown_options)
            )
        self.add_item(dropdown_menu)
        
        self.message = await self.ctx.followup.send(
            wait=True,
            content=f"Hey, {self.member.mention}!"
                + f"\n\nI found the following Accounts linked to your User ID. Please select the Account(s) you would like to apply with.",
            view=self,
            ephemeral=True
            )
    
    async def _callback_application(self,interaction:discord.Interaction,select:discord.ui.Select):
        default_tags = [i for i in select.values if i != 'not_listed']
        modal = self.clan_application_modal(default_tags)
        await interaction.response.send_modal(modal)

        await interaction.followup.delete_message(interaction.message.id)
    
    async def _callback_complete_application(self,interaction:discord.Interaction,modal:DiscordModal):
        await interaction.response.defer(ephemeral=True)

        accounts = []
        q_tags = modal.children[0]
        tags = re.split('[^a-zA-Z0-9]', q_tags.value)

        accounts_task = [asyncio.create_task(
            self.client.cog.fetch_player(tag=a) for a in tags
            )]

        q1 = modal.children[1] if len(modal.children) > 1 else None
        q2 = modal.children[2] if len(modal.children) > 2 else None
        q3 = modal.children[3] if len(modal.children) > 3 else None
        q4 = modal.children[4] if len(modal.children) > 4 else None

        accounts_return = await asyncio.gather(*accounts_task,return_exceptions=True)        
        async for a in AsyncIter(accounts_return):
            if isinstance(a,aPlayer):
                accounts.append(a)                
                if a.discord_user == 0:
                    a.discord_user = self.member.user_id

        new_application = db_ClanApplication(
            applicant_id = self.member.user_id,
            guild_id = self.member.guild_id,
            created = pendulum.now().int_timestamp,
            tags = [a.tag for a in accounts],
            clans = [c.tag for c in self.clans],
            answer_q1 = [getattr(q1,'label',''),getattr(q1,'value','')],
            answer_q2 = [getattr(q2,'label',''),getattr(q2,'value','')],
            answer_q3 = [getattr(q3,'label',''),getattr(q3,'value','')],
            answer_q4 = [getattr(q4,'label',''),getattr(q4,'value','')],
            bot_prefix = self.panel.tickettool_prefix
            )
        application = new_application.save()
        app_id = str(application.pk)

        await self.panel.listener_channel.send(f"{self.panel.tickettool_prefix}ticket {app_id} {self.member.user_id}")

        now = pendulum.now()
        while True:
            rt = pendulum.now()
            if rt.int_timestamp - now.int_timestamp > 60:
                break
            application = db_ClanApplication.objects.get(pk=app_id)
            channel = interaction.guild.get_channel(application.ticket_channel)
            if channel:
                interaction.response.edit_message
                await interaction.followup.send(
                    f"{self.member.mention} Your application has been created in {channel.mention}.",
                    ephemeral=True
                    )
                break
            await asyncio.sleep(0)

    def clan_application_modal(self,default_tags:list[str] = []):
        apply_modal = DiscordModal(
            function=self._callback_complete_application,
            title=f"Member Application",
            )
        question_tag = discord.ui.TextInput(
            label="Your Clash Player Tags, separated by spaces.",
            default=" ".join(default_tags),
            style=discord.TextStyle.short,
            placeholder="Example: #LJC8V0GCJ #8G9L8JV2R",
            required=True
            )
        apply_modal.add_item(question_tag)
        
        if self.panel:
            if len(str(self.panel.text_q1)) > 0:
                question_1 = discord.ui.TextInput(
                    label=str(self.panel.text_q1),
                    style=discord.TextStyle.long,
                    placeholder=str(self.panel.placeholder_q1),
                    required=True
                    )
                apply_modal.add_item(question_1)
            
            if len(str(self.panel.text_q2)) > 0:
                question_2 = discord.ui.TextInput(
                    label=str(self.panel.text_q2),
                    style=discord.TextStyle.long,
                    placeholder=str(self.panel.placeholder_q2),
                    required=True
                    )
                apply_modal.add_item(question_2)
            
            if len(str(self.panel.text_q3)) > 0:
                question_3 = discord.ui.TextInput(
                    label=str(self.panel.text_q3),
                    style=discord.TextStyle.long,
                    placeholder=str(self.panel.placeholder_q3),
                    required=True
                    )
                apply_modal.add_item(question_3)
            
            if len(str(self.panel.text_q4)) > 0:
                question_4 = discord.ui.TextInput(
                    label=str(self.panel.text_q4),
                    style=discord.TextStyle.long,
                    placeholder=str(self.panel.placeholder_q4),
                    required=True
                    )
                apply_modal.add_item(question_4)
        return apply_modal
    
    ##################################################
    #####
    ##### RTD ONBOARDING
    #####
    ##################################################
    async def rtd_onboarding(self):
        self.is_active = True
        start_button = DiscordButton(
            function=self._callback_start_rtd_onboarding,
            label="Click to Start"
            )
        self.add_item(start_button)
        self.message = await self.ctx.followup.send(
            wait=True,
            content=f"Hey, {self.member.mention}!"
                + f"\n\nWelcome to **The Assassins Guild**! We're really pleased to be partnering with Way of Life & Road to Death in building this new community."
                + f"\n\nTo get you set up in the Guild, we'll need your Clash Player Tags to link your accounts. Click on the button below to get started.",
            view=self,
            ephemeral=True
            )

    async def _callback_start_rtd_onboarding(self,interaction:discord.Interaction,button:DiscordButton):
        apply_modal = DiscordModal(
            function=self._callback_complete_rtd_onboarding,
            title=f"Welcome to The Assassins Guild!",
            )
        question_tag = discord.ui.TextInput(
            label="Clash Player Tags, separated by spaces.",
            style=discord.TextStyle.short,
            placeholder="Example: #LJC8V0GCJ #8G9L8JV2R",
            required=True
            )
        apply_modal.add_item(question_tag)
        await interaction.response.send_modal(apply_modal)
    
    async def _callback_complete_rtd_onboarding(self,interaction:discord.Interaction,modal:DiscordModal):
        await interaction.response.defer(ephemeral=True)

        rtd_clan = await aClan.create(tag='#2L90QPRL9')
        new_members = []

        q_tags = modal.children[0]
        tags = re.split('[^a-zA-Z0-9]', q_tags.value)

        async for tag in AsyncIter(tags):
            try:
                player = await aPlayer.create(tag=tag)
            except:
                continue
            else:
                if not isinstance(player,aPlayer):
                    continue
                if player.is_member:
                    continue
                player.new_member(interaction.user.id,rtd_clan)
                new_members.append(player)
        
        message = f"{interaction.user.mention} You've linked the following accounts as Member Accounts to Road to Death!\n"
        async for player in AsyncIter(new_members):
            message += f"\n{player.title}"
        await interaction.edit_original_response(content=message,view=None)

        member = self.client.cog.get_member(interaction.user.id,interaction.guild.id)
        await member.sync_clan_roles()

def account_recruiting_summary(account:aPlayer):
    text = ""
    text += f"### __**{account.name}**__"
    text += f"\n**[Open In-Game: {account.tag}]({account.share_link})**"
    text += f"\n\n<:Exp:825654249475932170> {account.exp_level}\u3000<:Clan:825654825509322752> {account.clan_description}"
    text += f"\n{account.town_hall.emote} {account.town_hall.description}\u3000{EmojisLeagues.get(account.league.name)} {account.trophies} (best: {account.best_trophies})"
    text += f"\n{account.hero_description}" if account.town_hall.level >= 7 else ""           
    text += f"\n\n{EmojisClash.BOOKFIGHTING} {account.troop_strength} / {account.max_troop_strength} *(rushed: {account.troop_rushed_pct}%)*\n"
    text += (f"{EmojisClash.BOOKSPELLS} {account.spell_strength} / {account.max_spell_strength} *(rushed: {account.spell_rushed_pct}%)*\n" if account.town_hall.level >= 5 else "")
    text += (f"{EmojisClash.BOOKHEROES} {account.hero_strength} / {account.max_hero_strength} *(rushed: {account.hero_rushed_pct}%)*\n" if account.town_hall.level >= 7 else "")
    return text

async def account_recruiting_embed(account:aPlayer):
    embed = await clash_embed(
        context=BotClashClient().bot,
        title=f"{account}",
        message=f"{EmojisClash.EXP} {account.exp_level}\u3000{EmojisClash.CLAN} {account.clan_description}"
            + (f"\n{account.discord_user_str}" if account.discord_user else "")
            + f"\n\n{account.town_hall.emoji} {account.town_hall.description}\u3000{EmojisLeagues.get(getattr(account.league,'name',''))} {account.trophies} (best: {account.best_trophies})"
            + f"\nWar Stars: {EmojisClash.STAR} {account.war_stars:,}"
            + f"\nLeague Stars: {EmojisClash.WARLEAGUES} {getattr(account.get_achievement('War League Legend'),'value',0)}"
            + f"\nCapital Gold Raided: {EmojisClash.CAPITALRAID} {numerize.numerize(getattr(account.get_achievement('Aggressive Capitalism'),'value',0),1)}"
            + f"\n**[Player Link: {account.tag}]({account.share_link})**"
            + f"\n\n"
            + f"{EmojisClash.BOOKFIGHTING} {account.troop_strength} / {account.max_troop_strength} *(rushed: {account.troop_rushed_pct}%)*\n"
            + (f"{EmojisClash.BOOKSPELLS} {account.spell_strength} / {account.max_spell_strength} *(rushed: {account.spell_rushed_pct}%)*\n" if account.town_hall.level >= 5 else "")
            + (f"{EmojisClash.BOOKHEROES} {account.hero_strength} / {account.max_hero_strength} *(rushed: {account.hero_rushed_pct}%)*\n" if account.town_hall.level >= 7 else "")
            + f"\n"
            + f"An asterisk (*) below indicates rushed levels.",
        show_author=False,
        )
    if len(account.heroes) > 0:
        hero_list = []
        for i, hero in enumerate(account.heroes):
            hero_t = f"{hero.emoji}`{str(hero.level):>2}{'*' if hero.is_rushed else '':>1}/{str(hero.maxlevel_for_townhall):^3}` "
            if i % 2 == 0:
                hero_list.append(hero_t)
            else:
                hero_list[-1] += "\u200b" + hero_t
        embed.add_field(
            name=f"Heroes (rushed: {len([h for h in account.heroes if h.is_rushed])}/{len(account.heroes)})",
            value="\n".join(hero_list)+"\n\u200b",
            inline=False
            )            
    if len(account.pets) > 0:
        pet_list = []
        for i, pet in enumerate(account.pets):
            pet_t = f"{pet.emoji}`{str(pet.level):>2}{'*' if pet.is_rushed else '':>1}/{str(pet.maxlevel_for_townhall):^3}` "
            if i % 2 == 0:
                pet_list.append(pet_t)
            else:
                pet_list[-1] += "\u200b" + pet_t
        embed.add_field(
            name=f"Hero Pets (rushed: {len([p for p in account.pets if p.is_rushed])}/{len(account.pets)})",
            value="\n".join(pet_list)+"\n\u200b",
            inline=False
            )
    if len(account.elixir_troops) > 0:
        troop_list = []
        for i, troop in enumerate(account.elixir_troops,start=1):
            troop_t = f"{troop.emoji}`{str(troop.level):>2}{'*' if troop.is_rushed else '':>1}/{str(troop.maxlevel_for_townhall):^3}` "
            if i % 3 == 1:
                troop_list.append(troop_t)
            else:
                troop_list[-1] += "\u200b" + troop_t
        embed.add_field(
            name=f"Elixir Troops (rushed: {len([t for t in account.elixir_troops if t.is_rushed])}/{len(account.elixir_troops)})",
            value="\n".join(troop_list)+"\n\u200b",
            inline=False
            )
    if len(account.darkelixir_troops) > 0:
        troop_list = []
        for i, troop in enumerate(account.darkelixir_troops,start=1):
            troop_t = f"{troop.emoji}`{str(troop.level):>2}{'*' if troop.is_rushed else '':>1}/{str(troop.maxlevel_for_townhall):^3}` "
            if i % 3 == 1:
                troop_list.append(troop_t)
            else:
                troop_list[-1] += "\u200b" + troop_t
        embed.add_field(
            name=f"Dark Elixir Troops (rushed: {len([t for t in account.darkelixir_troops if t.is_rushed])}/{len(account.darkelixir_troops)})",
            value="\n".join(troop_list)+"\n\u200b",
            inline=False
            )
    if len(account.siege_machines) > 0:
        siege_list = []
        for i, siege in enumerate(account.siege_machines,start=1):
            siege_t = f"{siege.emoji}`{str(siege.level):>2}{'*' if siege.is_rushed else '':>1}/{str(siege.maxlevel_for_townhall):^3}` "
            if i % 3 == 1:
                siege_list.append(siege_t)
            else:
                siege_list[-1] += "\u200b" + siege_t
        embed.add_field(
            name=f"Siege Machines (rushed: {len([s for s in account.siege_machines if s.is_rushed])}/{len(account.siege_machines)})",
            value="\n".join(siege_list)+"\n\u200b",
            inline=False
            )
    if len(account.elixir_spells) > 0:
        spell_list = []
        for i, spell in enumerate(account.elixir_spells,start=1):
            spell_t = f"{spell.emoji}`{str(spell.level):>2}{'*' if spell.is_rushed else '':>1}/{str(spell.maxlevel_for_townhall):^3}` "
            if i % 3 == 1:
                spell_list.append(spell_t)
            else:
                spell_list[-1] += "\u200b" + spell_t
        embed.add_field(
            name=f"Elixir Spells (rushed: {len([s for s in account.elixir_spells if s.is_rushed])}/{len(account.elixir_spells)})",
            value="\n".join(spell_list)+"\n\u200b",
            inline=False
            )
    if len(account.darkelixir_spells) > 0:
        spell_list = []
        for i, spell in enumerate(account.darkelixir_spells,start=1):
            spell_t = f"{spell.emoji}`{str(spell.level):>2}{'*' if spell.is_rushed else '':>1}/{str(spell.maxlevel_for_townhall):^3}` "
            if i % 3 == 1:
                spell_list.append(spell_t)
            else:
                spell_list[-1] += "\u200b" + spell_t
        embed.add_field(
            name=f"Dark Elixir Spells (rushed: {len([s for s in account.darkelixir_spells if s.is_rushed])}/{len(account.darkelixir_spells)})",
            value="\n".join(spell_list)+"\n\u200b",
            inline=False
            )
    return embed