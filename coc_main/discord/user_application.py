import asyncio
import coc
import discord
import pendulum
import re

from typing import *
from mongoengine import *

from redbot.core.utils import AsyncIter

from ..cog_coc_client import ClashOfClansClient
from ..api_client import BotClashClient as client

from ..coc_objects.players.player import aPlayer, db_Player
from ..coc_objects.clans.clan import aClan

from .mongo_discord import db_GuildApplyPanel, db_ClanApplication, db_ClanGuildLink
from .helpers import account_recruiting_summary

from ..utils.components import DefaultView, DiscordButton, DiscordSelectMenu, DiscordModal, clash_embed
from ..utils.constants.coc_emojis import EmojisClash
from ..exceptions import InvalidTag, ClashAPIError

bot_client = client()

class ClanApplyMenuUser(DefaultView):
    
    @classmethod
    async def start_user_application(cls,interaction:discord.Interaction,clan_tags:Optional[List[str]]=None):
        view = cls(interaction,clan_tags)
        await view.start()
    
    # @classmethod
    # async def start_rtd_onboarding(cls,interaction:discord.Interaction):
    #     view = cls(interaction,['#2L90QPRL9'])
    #     await view.rtd_onboarding()

    def __init__(self,
        context:discord.Interaction,
        applied_to_tags:Optional[List[str]]=None):

        self.clan_tags = applied_to_tags
        self.clans = []

        self.member = context.guild.get_member(context.user.id)
        super().__init__(context,timeout=300)
    
    @property
    def coc_client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    async def on_timeout(self):
        try:
            await self.ctx.followup.edit_message(self.message.id,content=f"Sorry, you timed out!",view=None)
        except:
            pass        
        self.stop_menu()
    
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

        try:
            panel = db_GuildApplyPanel.objects.get(
                server_id=self.guild.id,
                channel_id=self.channel.id
                )
        except DoesNotExist:
            pass
        else:
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

    ##################################################
    #####
    ##### STANDARD APPLICATION FUNCTIONS
    #####
    ##################################################
    async def start(self):
        if self.clan_tags:
            self.clans = await asyncio.gather(*(self.coc_client.fetch_clan(tag=tag) for tag in self.clan_tags))

        self.is_active = True
        dropdown_options = []

        account_tags = [db.tag for db in db_Player.objects(discord_user=self.member.id).only('tag')]

        get_accounts = await asyncio.gather(*(self.coc_client.fetch_player(tag=a) for a in account_tags[:10]),return_exceptions=True)
        accounts = [a for a in get_accounts if isinstance(a,aPlayer)]
        
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
        q_tags = [q for q in modal.children if q.label == "Your Clash Player Tags, separated by spaces."][0]
        tags = re.split('[^a-zA-Z0-9]', q_tags.value)

        q1 = modal.children[1] if len(modal.children) > 1 else None
        q2 = modal.children[2] if len(modal.children) > 2 else None
        q3 = modal.children[3] if len(modal.children) > 3 else None
        q4 = modal.children[4] if len(modal.children) > 4 else None

        tags_chk = []
        async for a in AsyncIter(tags):
            if not coc.utils.is_valid_tag(a):
                continue
            ntag = coc.utils.correct_tag(a)
            try:
                player = await self.coc_client.fetch_player(tag=ntag)
            except InvalidTag:
                continue
            except ClashAPIError:
                tags_chk.append(ntag)
            else:
                tags_chk.append(player.tag)
                if player.discord_user == 0:
                    player.discord_user = self.member.id
        
        if len(self.clans) == 0:
            eligible_townhalls = set([a.town_hall.level for a in accounts])
            guild_clans = await asyncio.gather(*(self.coc_client.fetch_clan(tag=c.tag) for c in db_ClanGuildLink.objects(guild_id=interaction.guild.id)))

            async for clan in AsyncIter(guild_clans):
                recruiting_ths = set(clan.recruitment_level)
                if len(recruiting_ths.intersection(eligible_townhalls)) > 0:
                    self.clans.append(clan)
        
        try:
            panel = db_GuildApplyPanel.objects.get(
                server_id=self.guild.id,
                channel_id=self.channel.id
                )
        except DoesNotExist:
            panel = None

        new_application = db_ClanApplication(
            applicant_id = self.member.id,
            guild_id = self.member.guild.id,
            created = pendulum.now().int_timestamp,
            tags = tags_chk,
            clans = [c.tag for c in self.clans],
            answer_q1 = [getattr(q1,'label',''),getattr(q1,'value','')],
            answer_q2 = [getattr(q2,'label',''),getattr(q2,'value','')],
            answer_q3 = [getattr(q3,'label',''),getattr(q3,'value','')],
            answer_q4 = [getattr(q4,'label',''),getattr(q4,'value','')],
            bot_prefix = getattr(panel,'ticket_prefix','')
            )
        application = new_application.save()
        app_id = str(application.pk)

        if getattr(panel,'listener_channel',None):
            channel = interaction.guild.get_channel(panel.listener_channel)
            if channel:
                await channel.send(f"{getattr(panel,'ticket_prefix','')}ticket {app_id} {self.member.id}")

        # if interaction.guild.id == 680798075685699691:
        #     await self.panel.listener_channel.send(
        #         f"Tags: {tags_chk}"
        #         )

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
    
    # ##################################################
    # #####
    # ##### RTD ONBOARDING
    # #####
    # ##################################################
    # async def rtd_onboarding(self):
    #     self.is_active = True
    #     start_button = DiscordButton(
    #         function=self._callback_start_rtd_onboarding,
    #         label="Click to Start"
    #         )
    #     self.add_item(start_button)
    #     self.message = await self.ctx.followup.send(
    #         wait=True,
    #         content=f"Hey, {self.member.mention}!"
    #             + f"\n\nWelcome to **The Assassins Guild**! We're really pleased to be partnering with Way of Life & Road to Death in building this new community."
    #             + f"\n\nTo get you set up in the Guild, we'll need your Clash Player Tags to link your accounts. Click on the button below to get started.",
    #         view=self,
    #         ephemeral=True
    #         )

    # async def _callback_start_rtd_onboarding(self,interaction:discord.Interaction,button:DiscordButton):
    #     apply_modal = DiscordModal(
    #         function=self._callback_complete_rtd_onboarding,
    #         title=f"Welcome to The Assassins Guild!",
    #         )
    #     question_tag = discord.ui.TextInput(
    #         label="Clash Player Tags, separated by spaces.",
    #         style=discord.TextStyle.short,
    #         placeholder="Example: #LJC8V0GCJ #8G9L8JV2R",
    #         required=True
    #         )
    #     apply_modal.add_item(question_tag)
    #     await interaction.response.send_modal(apply_modal)
    
    # async def _callback_complete_rtd_onboarding(self,interaction:discord.Interaction,modal:DiscordModal):
    #     await interaction.response.defer(ephemeral=True)

    #     rtd_clan = await aClan.create(tag='#2L90QPRL9')
    #     new_members = []

    #     q_tags = modal.children[0]
    #     tags = re.split('[^a-zA-Z0-9]', q_tags.value)

    #     async for tag in AsyncIter(tags):
    #         try:
    #             player = await self.coc_client.fetch_player(tag=tag)
    #         except:
    #             continue
    #         else:
    #             if not isinstance(player,aPlayer):
    #                 continue
    #             if player.is_member:
    #                 continue
    #             player.new_member(interaction.user.id,rtd_clan)
    #             new_members.append(player)
        
    #     message = f"{interaction.user.mention} You've linked the following accounts as Member Accounts to Road to Death!\n"
    #     async for player in AsyncIter(new_members):
    #         message += f"\n{player.title}"
    #     await interaction.edit_original_response(content=message,view=None)

    #     member = botclient.cog.get_member(interaction.user.id,interaction.guild.id)
    #     await member.sync_clan_roles()

async def listener_user_application(channel:discord.TextChannel,application_id:str):

    newline = "\n"
    coc_client = bot_client.bot.get_cog("ClashOfClansClient")

    try:
        application = db_ClanApplication.objects.get(id=application_id)
    except DoesNotExist:
        embed = await clash_embed(
            context=bot_client.bot,
            message=f"**Could not find application.**",
            success=False
            )
        return await channel.send(embed=embed)
    
    account_tasks = await asyncio.gather(*(coc_client.fetch_player(tag=i) for i in application.tags),return_exceptions=True)
    clan_tasks = await asyncio.gather(*(coc_client.fetch_clan(tag=i) for i in application.clans),return_exceptions=True)
    
    member = channel.guild.get_member(application.applicant_id)
    
    clans = [c for c in clan_tasks if isinstance(c,aClan)]

    application_embed = await clash_embed(
        context=bot_client.bot,
        title=f"{member.display_name}",
        message=f"`{member.id}`"
            + f"\n**Joined Discord**"
            + f"\n<t:{int(member.created_at.timestamp())}:f>"
            + f"\n\n**Joined {member.guild.name}**"
            + f"\n<t:{int(member.joined_at.timestamp())}:f>"
            + (f"\n\n**Applied to Clans**" if len(clans) > 0 else "")
            + (f"\n{newline.join([c.title for c in clans])}" if len(clans) > 0 else "")
            + f"\n\u200b",
        thumbnail=member.display_avatar)
    
    if application.answer_q1[1]:
        application_embed.add_field(
            name=f"**{application.answer_q1[0]}**",
            value=f"{application.answer_q1[1]}\n\u200b",
            inline=False
            )
    if application.answer_q2[1]:
        application_embed.add_field(
            name=f"**{application.answer_q2[0]}**",
            value=f"{application.answer_q2[1]}\n\u200b",
            inline=False
            )
    if application.answer_q3[1]:
        application_embed.add_field(
            name=f"**{application.answer_q3[0]}**",
            value=f"{application.answer_q3[1]}\n\u200b",
            inline=False
            )
    if application.answer_q4[1]:
        application_embed.add_field(
            name=f"**{application.answer_q4[0]}**",
            value=f"{application.answer_q4[1]}\n\u200b",
            inline=False
            )
 
    accounts = sorted([a for a in account_tasks if isinstance(a,aPlayer)],key=lambda x:(x.town_hall.level,x.exp_level),reverse=True)
    accounts_townhalls = sorted(list(set([a.town_hall.level for a in accounts])),reverse=True)

    member_account_tags = [db.tag for db in db_Player.objects(discord_user=member.id).only('tag')]
    other_accounts = [tag for tag in member_account_tags if tag not in application.tags]

    if len(accounts) == 0:
        accounts_embed_text = "Did not find any valid accounts. Received Tags: " + ", ".join(application.tags)
    else:
        accounts_embed_text = ""
        async for a in AsyncIter(accounts):
            accounts_embed_text += account_recruiting_summary(a)
    
    accounts_embed = await clash_embed(
        context=bot_client.bot,
        title=f"{member.name}",
        message=accounts_embed_text + "\u200b",
        thumbnail=member.display_avatar
        )
    if len(other_accounts) > 0:
        list_oa = []
        other_accounts_embed_text = ""
        async for a in AsyncIter(other_accounts[:5]):
            try:
                account = await coc_client.fetch_player(tag=a)
            except Exception:
                continue
            else:
                list_oa.append(account)
        
        list_oa.sort(key=lambda x:(x.town_hall.level,x.exp_level),reverse=True)
        async for a in AsyncIter(list_oa):
            other_accounts_embed_text += f"{a.title}\n\u200b\u3000{EmojisClash.CLAN} {a.clan_description}\n\n"

        accounts_embed.add_field(
            name=f"**Other Accounts (max. 5)**",
            value="\n" + other_accounts_embed_text,
            inline=False
            )
                    
    application.ticket_channel = channel.id
    application.save()
    
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
    
    for c in clans:
        if c.unicode_emoji:
            channel_name += f"{c.unicode_emoji}"
        else:
            channel_name += f"-{c.abbreviation}"
    
    for th in accounts_townhalls:
        channel_name += f"-th{th}"
    
    await channel.edit(name=channel_name.lower())    
    await channel.set_permissions(member,read_messages=True)    
    async for c in AsyncIter(clans):
        try:
            link = db_ClanGuildLink.objects.get(tag=c.tag,guild_id=channel.guild.id)
        except DoesNotExist:
            continue
        else:
            coleader_role = channel.guild.get_role(link.coleader_role)        
            if coleader_role:
                await channel.set_permissions(coleader_role,read_messages=True)
                if len(channel.threads) > 0:
                    thread = channel.threads[0]
                    await thread.send(
                        f"{coleader_role.mention} {c.emoji} {c.name} has a new applicant: {', '.join(f'TH{num}' for num in accounts_townhalls)}.",
                        allowed_mentions=discord.AllowedMentions(roles=True)
                        )