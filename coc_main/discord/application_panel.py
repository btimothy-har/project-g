import asyncio
import discord
import re
import pendulum
import bson

from typing import *

from redbot.core.utils import AsyncIter

from .clan_link import ClanGuildLink
from .add_delete_link import AddLinkMenu
from .helpers import account_recruiting_summary

from ..cog_coc_client import ClashOfClansClient
from ..api_client import BotClashClient as client

from ..coc_objects.players.player import BasicPlayer, aPlayer
from ..coc_objects.clans.clan import aClan

from ..utils.components import DefaultView, DiscordButton, DiscordSelectMenu, DiscordModal, clash_embed, handle_command_error
from ..utils.constants.coc_emojis import EmojisClash
from ..utils.constants.ui_emojis import EmojisUI

from ..exceptions import ClashAPIError

bot_client = client()

##################################################
#####
##### APPLICATION PANEL
#####
##################################################
class GuildApplicationPanel():

    @classmethod
    async def get_for_guild(cls,guild_id:int):
        db = bot_client.coc_db.db__guild_apply_panel.find({'server_id':guild_id})
        return [cls(panel) async for panel in db]

    @classmethod
    async def get_panel(cls,guild_id:int,channel_id:int):
        db = await bot_client.coc_db.db__guild_apply_panel.find_one({'server_id':guild_id,'channel_id':channel_id})
        if db:
            return cls(db)
        return None

    def __init__(self,database_entry:dict):        
        self.id = database_entry.get('_id',None)
        
        self.guild_id = database_entry.get('server_id',0)
        self.channel_id = database_entry.get('channel_id',0)
        self.message_id = database_entry.get('message_id',0)

        self.can_user_select_clans = database_entry.get('select_clans',False)

        self.tickettool_prefix = database_entry.get('ticket_prefix','')
        self._tickettool_channel = database_entry.get('listener_channel',0)

        self.text_q1 = database_entry.get('text_q1','')
        self.placeholder_q1 = database_entry.get('placeholder_q1','')
        self.text_q2 = database_entry.get('text_q2','')
        self.placeholder_q2 = database_entry.get('placeholder_q2','')
        self.text_q3 = database_entry.get('text_q3','')
        self.placeholder_q3 = database_entry.get('placeholder_q3','')
        self.text_q4 = database_entry.get('text_q4','')
        self.placeholder_q4 = database_entry.get('placeholder_q4','')
    
    def __str__(self):
        return f"Application Panel (Channel: {getattr(self.channel,'name','Unknown Channel')})"
    
    @classmethod
    async def create(cls,guild_id:int,channel_id:int,**kwargs):        
        await bot_client.coc_db.db__guild_apply_panel.insert_one(
            {
            '_id':{'guild':guild_id,'channel':channel_id},
            'server_id':guild_id,
            'channel_id':channel_id,
            'select_clans':kwargs.get('select_clans',False),
            'ticket_prefix':kwargs.get('ticket_prefix','.'),
            'listener_channel':kwargs.get('listener_channel',0),
            'text_q1':kwargs.get('text_q1',''),
            'placeholder_q1':kwargs.get('placeholder_q1',''),
            'text_q2':kwargs.get('text_q2',''),
            'placeholder_q2':kwargs.get('placeholder_q2',''),
            'text_q3':kwargs.get('text_q3',''),
            'placeholder_q3':kwargs.get('placeholder_q3',''),
            'text_q4':kwargs.get('text_q4',''),
            'placeholder_q4':kwargs.get('placeholder_q4','')
            }
        )
        return await cls.get_panel(guild_id,channel_id)

    async def delete(self):        
        message = await self.fetch_message()
        if message:
            await message.delete()        
        await bot_client.coc_db.db__guild_apply_panel.delete_one({'_id':self.id})

    @property
    def guild(self) -> Optional[discord.Guild]:
        return bot_client.bot.get_guild(self.guild_id)
    
    @property
    def channel(self) -> Optional[discord.TextChannel]:
        return bot_client.bot.get_channel(self.channel_id)

    @property
    def listener_channel(self) -> Optional[discord.TextChannel]:
        return bot_client.bot.get_channel(self._tickettool_channel)
    
    async def fetch_message(self) -> Optional[discord.Message]:
        if self.channel:
            try:
                return await self.channel.fetch_message(self.message_id)
            except discord.NotFound:
                pass
        return None
    
    async def send_to_discord(self,embed:discord.Embed,view:discord.ui.View):
        try:
            if not self.channel:
                await self.delete()
                return
            
            message = await self.fetch_message()
            if not message:
                message = await self.channel.send(
                    embed=embed,
                    view=view
                    )
                await bot_client.coc_db.db__guild_apply_panel.update_one(
                    {'_id':self.id},
                    {'$set':{
                        'message_id':message.id
                        }
                        }
                    )
            else:
                message = await message.edit(
                    embed=embed,
                    view=view
                    )
        
        except Exception as exc:
            bot_client.coc_main_log.exception(
                f"Error sending Application Panel to Discord: {self.guild.name} {getattr(self.channel,'name','Unknown Channel')}. {exc}"
                )

##################################################
#####
##### VIEW FOR APPLICATION PANEL
#####
##################################################
class ClanApplyMenu(discord.ui.View):
    def __init__(self,panel:GuildApplicationPanel,list_of_clans:List[aClan]):
        
        self.panel = panel
        self.clans = list_of_clans
        super().__init__(timeout=None)

        self.reload_items()

    @property
    def coc_client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")

    async def on_timeout(self):
        pass

    def reload_items(self):
        self.clear_items()
        if self.panel.can_user_select_clans:
            self.add_item(self.select_menu())
        else:
            self.add_item(self.apply_button())
        self.add_item(self.add_link_button())

    def select_menu(self):
        dropdown_options = [discord.SelectOption(
            label=f"{clan.name}" + " | " + f"{clan.tag}",
            value=clan.tag,
            emoji=clan.emoji
            )
            for clan in self.clans
            ]
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

        self.reload_items()
        await interaction.followup.edit_message(interaction.message.id,view=self)
        await ClanApplyMenuUser.start_user_application(interaction,select.values)
    
    def apply_button(self):
        apply_button = DiscordButton(
            function=self._callback_apply,
            label="Click here to apply to any of our Clans!",
            style=discord.ButtonStyle.blurple
            )
        return apply_button
    
    async def _callback_apply(self,interaction:discord.Interaction,select:discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        self.reload_items()
        await interaction.followup.edit_message(interaction.message.id,view=self)
        await ClanApplyMenuUser.start_user_application(interaction)
    
    def add_link_button(self):
        add_button = DiscordButton(
            function=self._callback_add_link,
            emoji=EmojisUI.ADD,
            label="Link a Clash Account",
            style=discord.ButtonStyle.blurple
            )
        return add_button
    
    async def _callback_add_link(self,interaction:discord.Interaction,select:discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        self.reload_items()
        await interaction.followup.edit_message(interaction.message.id,view=self)
        
        add_link_view = AddLinkMenu(interaction,interaction.user)
        await add_link_view._start_add_link()

##################################################
#####
##### APPLICAITON MENU FOR USER
#####
##################################################
class ClanApplyMenuUser(discord.ui.View):
    @classmethod
    async def start_user_application(cls,interaction:discord.Interaction,clan_tags:Optional[List[str]]=None):
        view = cls(interaction.user,interaction.channel,clan_tags)
        chk = await view.load_items()

        if chk:
            text = "I found the following Accounts linked to your User ID. Please select the Account(s) you would like to apply with."
        else:
            text = "I couldn't find any Accounts linked to your User ID. Click the button below to continue with your application."

        await interaction.followup.send(
            content=f"Hey, {interaction.user.mention}!"
                + f"\n\n{text}",
            view=view,
            ephemeral=True
            )
        
        wait = await view.wait()
        if wait or not view.application_id:
            return
        
        channel_found = False
        now = pendulum.now()
        while True:
            rt = pendulum.now()
            if rt.int_timestamp - now.int_timestamp > 60:
                break

            application = await bot_client.coc_db.db__clan_application.find_one({'_id':view.application_id})
            channel = interaction.guild.get_channel(application.get('ticket_channel',0))
            if channel:
                await interaction.followup.send(
                    f"{interaction.user.mention} Your application has been created in {channel.mention}.",
                    ephemeral=True
                    )
                channel_found = True
                break
            await asyncio.sleep(0.5)
        
        if not channel_found:
            await interaction.followup.send(
                f"{interaction.user.mention} An error seems to have occurred. Please contact a Moderator via DMs.",
                ephemeral=True
                )
    
    @classmethod
    async def assistant_user_application(cls,user:discord.User,channel:discord.TextChannel):
        view = cls(user,channel)
        chk = await view.load_items()

        if chk:
            text = "I found the following Accounts linked to your User ID. Please select the Account(s) you would like to apply with."
        else:
            text = "I couldn't find any Accounts linked to your User ID. Click the button below to continue with your application."
        
        embed = await clash_embed(
            context=bot_client.bot,
            message=f"{text}",
            timestamp=pendulum.now()
            )
        await channel.send(content=f"Hey, {user.mention}!",embed=embed,view=view)

        wait = await view.wait()
        if wait or not view.application_id:
            return None
        return view.application_id

    def __init__(self,
        user:discord.User,
        channel:discord.TextChannel,
        applied_to_tags:Optional[List[str]]=None):

        self.clan_tags = applied_to_tags
        self.clans = []

        self.member = user
        self.channel = channel
        self.application_id = None
        super().__init__(timeout=600)
    
    async def interaction_check(self,interaction:discord.Interaction):
        if interaction.user.id != self.member.id:
            await interaction.response.send_message(
                content="This doesn't belong to you!", ephemeral=True
                )
            return False
        return True

    async def on_timeout(self):
        self.stop()

    async def on_error(self, interaction:discord.Interaction, error:Exception, item):
        err = await handle_command_error(error,interaction)
        if err:
            return
        self.stop()
    
    @property
    def coc_client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    ##################################################
    #####
    ##### STANDARD APPLICATION FUNCTIONS
    #####
    ##################################################
    async def load_items(self):
        if self.clan_tags:
            self.clans = [a async for a in bot_client.coc.get_clans(self.clan_tags)]

        self.is_active = True
        dropdown_options = []

        tags_query = bot_client.coc_db.db__player.find({'discord_user':self.member.id},{'_id':1})
        account_tags = [db['_id'] async for db in tags_query]
        accounts = [p async for p in bot_client.coc.get_players(account_tags[:10])]

        if len(accounts) == 0:
            button = DiscordButton(
                function=self._callback_application,
                label="Click here to apply with your Clash Account!",
                style=discord.ButtonStyle.blurple
                )
            self.add_item(button)
            return False

        else:
            dropdown_options.extend([
                discord.SelectOption(
                    label=f"{player.clean_name}" + " | " + f"{player.tag}",
                    value=player.tag,
                    emoji=player.town_hall.emoji
                    )
                for player in sorted(accounts,key=lambda x:(x.town_hall.level,x.exp_level),reverse=True)
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
            return True
    
    async def _callback_application(self,interaction:discord.Interaction,object:Union[discord.ui.Select,discord.ui.Button]):
        
        default_tags = [i for i in getattr(object,'values',[]) if i != 'not_listed']

        get_panels = await GuildApplicationPanel.get_for_guild(self.channel.guild.id)
        panel = get_panels[0]
        modal = ClanApplyMenuUser.clan_application_modal(
            view=self,
            panel=panel,
            default_tags=default_tags,
            applied_to_clans=self.clans
            )

        await interaction.response.send_modal(modal)
        await interaction.followup.delete_message(interaction.message.id)
    
    @staticmethod
    def clan_application_modal(view:discord.ui.View,panel:GuildApplicationPanel,default_tags:list[str] = [],applied_to_clans:list[aClan] = []):
        apply_modal = DiscordModal(
            function=ClanApplyMenuUser._callback_complete_application,
            title=f"Member Application",
            )
        apply_modal.view = view
        apply_modal.panel = panel
        apply_modal.clans = applied_to_clans
        question_tag = discord.ui.TextInput(
            label="Your Clash Player Tags, separated by spaces.",
            default=" ".join(default_tags),
            style=discord.TextStyle.short,
            placeholder="Example: #LJC8V0GCJ #8G9L8JV2R",
            required=True
            )
        apply_modal.add_item(question_tag)
        
        if len(str(panel.text_q1)) > 0:
            question_1 = discord.ui.TextInput(
                label=str(panel.text_q1),
                style=discord.TextStyle.long,
                placeholder=str(panel.placeholder_q1),
                required=True
                )
            apply_modal.add_item(question_1)
        
        if len(str(panel.text_q2)) > 0:
            question_2 = discord.ui.TextInput(
                label=str(panel.text_q2),
                style=discord.TextStyle.long,
                placeholder=str(panel.placeholder_q2),
                required=True
                )
            apply_modal.add_item(question_2)
        
        if len(str(panel.text_q3)) > 0:
            question_3 = discord.ui.TextInput(
                label=str(panel.text_q3),
                style=discord.TextStyle.long,
                placeholder=str(panel.placeholder_q3),
                required=True
                )
            apply_modal.add_item(question_3)
        
        if len(str(panel.text_q4)) > 0:
            question_4 = discord.ui.TextInput(
                label=str(panel.text_q4),
                style=discord.TextStyle.long,
                placeholder=str(panel.placeholder_q4),
                required=True
                )
            apply_modal.add_item(question_4)
        return apply_modal

    @staticmethod
    async def _callback_complete_application(interaction:discord.Interaction,modal:DiscordModal):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(
            content=f"{interaction.user.mention} Please wait while I process your application...",
            ephemeral=True
            )

        q_tags = [q for q in modal.children if q.label == "Your Clash Player Tags, separated by spaces."][0]
        tags = re.split('[^a-zA-Z0-9]', q_tags.value)
        clans = modal.clans if len(modal.clans) > 0 else []
        api_error = False

        q1 = modal.children[1] if len(modal.children) > 1 else None
        q2 = modal.children[2] if len(modal.children) > 2 else None
        q3 = modal.children[3] if len(modal.children) > 3 else None
        q4 = modal.children[4] if len(modal.children) > 4 else None
        
        application = await bot_client.coc_db.db__clan_application.insert_one(
            {
            'applicant_id':interaction.user.id,
            'guild_id':interaction.guild.id,
            'created':pendulum.now().int_timestamp,
            'tags':tags,
            'clans':[c.tag for c in clans],
            'answer_q1':[getattr(q1,'label',''),getattr(q1,'value','')],
            'answer_q2':[getattr(q2,'label',''),getattr(q2,'value','')],
            'answer_q3':[getattr(q3,'label',''),getattr(q3,'value','')],
            'answer_q4':[getattr(q4,'label',''),getattr(q4,'value','')],
            'bot_prefix':getattr(modal.panel,'tickettool_prefix',''),
            'api_error':api_error
            }
        )
        
        application_id = application.inserted_id
        l_channel = modal.panel.listener_channel
        if l_channel:
            await l_channel.send(f"{getattr(modal.panel,'tickettool_prefix','')}ticket {application_id} {interaction.user.id}")

        if interaction.guild.id == 680798075685699691:
            await modal.panel.listener_channel.send(
                f"Tags: {tags}"
                )
        modal.view.application_id = application_id
        modal.view.stop()

async def listener_user_application(channel:discord.TextChannel,application_id:str):
    newline = "\n"

    application = await bot_client.coc_db.db__clan_application.find_one({'_id':bson.ObjectId(application_id)})
    if not application:
        embed = await clash_embed(
            context=bot_client.bot,
            message=f"**Could not find application.**",
            success=False
            )
        return await channel.send(embed=embed)
    
    application_accounts = [p async for p in bot_client.coc.get_players(application.get('tags',[]))]

    clan_tags = application.get('clans',[])
    if len(clan_tags) == 0:
        application_clans = []
        eligible_townhalls = set([a.town_hall.level for a in accounts])
        linked_clans = await ClanGuildLink.get_for_guild(channel.guild.id)

        async for clan in bot_client.coc.get_clans([c.tag for c in linked_clans]):
            recruiting_ths = set(clan.recruitment_level)
            if len(recruiting_ths.intersection(eligible_townhalls)) > 0:
                application_clans.append(clan)
    else:
        application_clans = [c async for c in bot_client.coc.get_clans(clan_tags)]

    member = channel.guild.get_member(application.get('applicant_id',0))

    application_embed = await clash_embed(
        context=bot_client.bot,
        title=f"{member.display_name}",
        message=f"`{member.id}`"
            + f"\n**Joined Discord**"
            + f"\n<t:{int(member.created_at.timestamp())}:f>"
            + f"\n\n**Joined {member.guild.name}**"
            + f"\n<t:{int(member.joined_at.timestamp())}:f>"
            + (f"\n\n**Applied to Clans**" if len(application_clans) > 0 else "")
            + (f"\n{newline.join([c.title for c in application_clans])}" if len(application_clans) > 0 else "")
            + f"\n\u200b",
        thumbnail=member.display_avatar)
    
    if application.get('answer_q1',[])[1]:
        application_embed.add_field(
            name=f"**{application.get('answer_q1',[])[0]}**",
            value=f"{application.get('answer_q1',[])[1]}\n\u200b",
            inline=False
            )
    if application.get('answer_q2',[])[1]:
        application_embed.add_field(
            name=f"**{application.get('answer_q2',[])[0]}**",
            value=f"{application.get('answer_q2',[])[1]}\n\u200b",
            inline=False
            )
    if application.get('answer_q3',[])[1]:
        application_embed.add_field(
            name=f"**{application.get('answer_q3',[])[0]}**",
            value=f"{application.get('answer_q3',[])[1]}\n\u200b",
            inline=False
            )
    if application.get('answer_q4',[])[1]:
        application_embed.add_field(
            name=f"**{application.get('answer_q4',[])[0]}**",
            value=f"{application.get('answer_q4',[])[1]}\n\u200b",
            inline=False
            )
        
    accounts = sorted(
        [a for a in application_accounts if isinstance(a,aPlayer)],
        key=lambda x:(x.town_hall.level,x.exp_level),reverse=True
        )
    accounts_townhalls = sorted(list(set([a.town_hall.level for a in accounts])),reverse=True)

    tags_query = bot_client.coc_db.db__player.find({'discord_user':member.id},{'_id':1})
    member_account_tags = [db['_id'] async for db in tags_query]
    other_accounts = [tag for tag in member_account_tags if tag not in application.get('tags')]

    if len(accounts) == 0:
        accounts_embed_text = "Did not find any valid accounts. Received Tags: " + ", ".join(application.get('tags'))
    else:
        accounts_embed_text = ""
        async for a in AsyncIter(accounts):
            if a.discord_user == 0:
                await BasicPlayer.set_discord_link(a.tag,member.id)
            accounts_embed_text += account_recruiting_summary(a)
    
    accounts_embed = await clash_embed(
        context=bot_client.bot,
        title=f"{member.name}",
        message=accounts_embed_text + "\u200b",
        thumbnail=member.display_avatar
        )
    if len(other_accounts) > 0:
        list_oa = [p async for p in bot_client.coc.get_players(other_accounts[:5])]                
        list_oa.sort(key=lambda x:(x.town_hall.level,x.exp_level),reverse=True)

        async for a in AsyncIter(list_oa):
            other_accounts_embed_text += f"{a.title}\n\u200b\u3000{EmojisClash.CLAN} {a.clan_description}\n\n"

        accounts_embed.add_field(
            name=f"**Other Accounts (max. 5)**",
            value="\n" + other_accounts_embed_text,
            inline=False
            )
    
    await bot_client.coc_db.db__clan_application.update_one(
        {'_id':bson.ObjectId(application_id)},
        {'$set':{
            'ticket_channel':channel.id
            }
        })
                
    await channel.send(embed=application_embed)
    await channel.send(embed=accounts_embed)

    channel_name = ""
    if channel.name.startswith('ticket-'):
        channel_name += f"{re.split('-', channel.name)[1]}-"
    else:
        if channel.guild.id == 1132581106571550831: #guild
            channel_name += f"{re.split('-', channel.name)[0]}-"
        elif channel.guild.id == 688449973553201335: #arix
            channel_name += f"{re.split('📝', channel.name)[0]}-"
    
    for c in application_clans:
        if c.unicode_emoji:
            channel_name += f"{c.unicode_emoji}"
        else:
            channel_name += f"-{c.abbreviation}"
    
    for th in accounts_townhalls:
        channel_name += f"-th{th}"
    
    await channel.edit(name=channel_name.lower())
    await asyncio.sleep(5)

    c_iter = AsyncIter(application_clans)
    async for c in c_iter:
        link = await ClanGuildLink.get_link(c.tag,channel.guild.id)
        if getattr(link,'coleader_role',None):
            await channel.send(f"{application.get('bot_prefix','.')}add {link.coleader_role.mention}")
            if len(channel.threads) > 0:                
                thread = channel.threads[0]
                await thread.send(
                    f"{link.coleader_role.mention} {c.emoji} {c.name} has a new applicant: {', '.join(f'TH{num}' for num in accounts_townhalls)}.",
                    allowed_mentions=discord.AllowedMentions(roles=True)
                    )