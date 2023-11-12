import asyncio
import discord
import pendulum

from typing import *
from mongoengine import *

from ..api_client import BotClashClient as client

from .mongo_discord import db_RecruitingPost

from ..utils.components import get_bot_webhook, clash_embed, DiscordButton
from ..utils.constants.ui_emojis import EmojisUI

bot_client = client()

class RecruitingReminder():
    _locks = {}

    @classmethod
    async def get_by_id(cls,id:str) -> 'RecruitingReminder':
        def _query_db():
            try:
                return db_RecruitingPost.objects.get(id=id)
            except DoesNotExist:
                return None
        db = await bot_client.run_in_thread(_query_db)
        if db:
            return cls(db)
        return None

    @classmethod
    async def get_for_guild(cls,guild_id:int) -> List['RecruitingReminder']:
        def _query_db():
            return [db for db in db_RecruitingPost.objects(guild=guild_id)]        
        db = await bot_client.run_in_thread(_query_db)
        return [cls(p) for p in db]

    @classmethod
    async def get_all_active(cls):
        def _query_db():
            return [db for db in db_RecruitingPost.objects(is_active=True)]
        db = await bot_client.run_in_thread(_query_db)
        return [cls(p) for p in db]

    def __init__(self,db_post:db_RecruitingPost):
        self.id = str(db_post.id)

        self.is_active = db_post.is_active
        self.ad_name = db_post.ad_name
        self.ad_link = db_post.ad_link
        self.interval = db_post.interval
        self.last_user = db_post.last_user

        self._remind_user = db_post.remind_user
        self._last_posted = db_post.last_posted
        self._active_reminder = db_post.active_reminder
        self._channel = db_post.channel
    
    def __str__(self):
        return f"{self.ad_name}: every {self.interval}hr(s) for {getattr(self.remind_user,'display_name','Unknown')} in {getattr(self.channel,'name','Unknown Channel')}"
    
    @property
    def lock(self) -> asyncio.Lock:
        if self.id not in self._locks:
            self._locks[self.id] = asyncio.Lock()
        return self._locks[self.id]
    
    @property
    def remind_user(self) -> Optional[discord.User]:
        return bot_client.bot.get_user(self._remind_user)
    
    @property
    def last_posted(self) -> Optional[pendulum.DateTime]:
        if self._last_posted == 0:
            return None
        return pendulum.from_timestamp(self._last_posted)
    
    @property
    def next_reminder(self) -> Optional[pendulum.DateTime]:
        if self.active_reminder:
            return None
        if not self.last_posted:
            return None
        if not self.is_active:
            return None
        if bot_client.bot.user.id == 828838353977868368:
            return self.last_posted.add(minutes=self.interval)
        return self.last_posted.add(hours=self.interval)

    @property
    def active_reminder(self) -> int:
        if self._active_reminder == 0:
            return None
        return self._active_reminder    
    
    @property
    def channel(self) -> Optional[Union[discord.TextChannel,discord.Thread]]:
        return bot_client.bot.get_channel(self._channel)
    
    ##################################################
    ### CREATE / DELETE
    ##################################################
    @classmethod
    async def create(cls,channel:discord.TextChannel,user_to_remind:discord.Member,name:str,link:str,interval:int):
        def _save_to_db():
            new_post = db_RecruitingPost(
                is_active=True,
                ad_name=name,
                ad_link=link,
                guild=channel.guild.id,
                channel=channel.id,
                interval=interval,
                remind_user=user_to_remind.id,
                last_posted=0,
                last_user=0,
                active_reminder=0,
                logs=[]
                )
            new_post.save()
            return new_post
        
        ret_post = await bot_client.run_in_thread(_save_to_db)
        return cls(ret_post)

    async def delete(self):
        def _delete_from_db():
            db_RecruitingPost.objects.get(id=self.id).delete()
            
        async with self.lock:
            try:
                if self.active_reminder:
                    webhook = await get_bot_webhook(bot_client.bot,self.channel)
                    if isinstance(self.channel,discord.Thread):
                        await webhook.delete_message(
                            self.active_reminder,
                            thread=self.channel
                            )
                    else:
                        await webhook.delete_message(self.active_reminder)
                self._is_active = False
            except:
                pass
            await bot_client.run_in_thread(_delete_from_db)
    
    ##################################################
    ### DISCORD HELPERS
    ##################################################
    async def embed(self):
        embed = await clash_embed(
            context=bot_client.bot,
            message=f"**Recruiting Reminder: {self.ad_name}**"
                + f"\nLink to Ad: {self.ad_link}",
            show_author=False,
            )
        return embed
    
    async def send_reminder(self):
        def _update_active_reminder():
            db_RecruitingPost.objects(id=self.id).update_one(set__active_reminder=self._active_reminder)
            bot_client.coc_main_log.info(f"{self.ad_name} {self.id} updated active reminder to {self._active_reminder}.")

        now = pendulum.now()
        send = False
        async with self.lock:
            if self.last_posted is None:
                send = True
            if self.next_reminder and now > self.next_reminder:
                send = True      
            if not self.is_active:
                send = False
            if not send:
                return None

            if not self.channel:
                return await self.delete()
            
            try:
                post_embed = await self.embed()
                view = RecruitingPostPrompt(self.id)

                webhook = await get_bot_webhook(bot_client.bot,self.channel)
                if isinstance(self.channel,discord.Thread):
                    msg = await webhook.send(
                        wait=True,
                        username=bot_client.bot.user.name,
                        avatar_url=bot_client.bot.user.display_avatar.url,
                        content=getattr(self.remind_user,'mention',''),
                        embed=post_embed,
                        view=view,
                        thread=self.channel,
                        )
                else:
                    msg = await webhook.send(
                        wait=True,
                        username=bot_client.bot.user.name,
                        avatar_url=bot_client.bot.user.display_avatar.url,
                        content=getattr(self.remind_user,'mention',''),
                        embed=post_embed,
                        view=view,
                        )
                self._active_reminder = msg.id
                bot_client.coc_main_log.info(f"Recruiting Reminder sent for {self.ad_name}.")
        
            except asyncio.CancelledError:
                return None
            except Exception as exc:
                bot_client.coc_main_log.exception(f"Recruiting Reminder failed for {self.ad_name}.")
                return exc
            else:
                await bot_client.run_in_thread(_update_active_reminder)
                return self
    
    async def refresh_reminder(self):
        def _update_active_reminder():
            db_RecruitingPost.objects(id=self.id).update_one(set__active_reminder=self._active_reminder)
            bot_client.coc_main_log.info(f"{self.ad_name} {self.id} updated active reminder to {self._active_reminder}.")

        async with self.lock:
            if not self.is_active:
                return None
            if not self.active_reminder:
                return None
            
            if not self.channel:
                return await self.delete()
            
            post_embed = await self.embed()
            view = RecruitingPostPrompt(self.id)
            webhook = await get_bot_webhook(bot_client.bot,self.channel)
            if isinstance(self.channel,discord.Thread):
                msg = await webhook.edit_message(
                    message_id=self.active_reminder,
                    content=getattr(self.remind_user,'mention',''),
                    embed=post_embed,
                    view=view,
                    thread=self.channel
                    )
            else:
                msg = await webhook.edit_message(
                    message_id=self.active_reminder,
                    content=getattr(self.remind_user,'mention',''),
                    embed=post_embed,
                    view=view
                    )
            self._active_reminder = msg.id
            await bot_client.run_in_thread(_update_active_reminder)

class RecruitingPostPrompt(discord.ui.View):
    def __init__(self,post_id:str):
        self.post_id = post_id
        self.button = DiscordButton(
            function=self._post_confirmed,
            label="Confirm Completed",
            style=discord.ButtonStyle.blurple,
            emoji=EmojisUI.TASK_CHECK,
            row=0
            )
        super().__init__(timeout=None)
        self.add_item(self.button)
    
    async def _post_confirmed(self,interaction:discord.Interaction,button:DiscordButton):
        def _update_post_in_db():
            db_RecruitingPost.objects(id=self.post_id).update_one(
                set__last_posted=now.int_timestamp,
                set__last_user=interaction.user.id,
                set__active_reminder=0,
                )

        if not interaction.response.is_done():
            await interaction.response.defer()
        try:
            lock = RecruitingReminder._locks[self.post_id]
        except KeyError:
            RecruitingReminder._locks[self.post_id] = lock = asyncio.Lock()
        
        async with lock:
            post = await RecruitingReminder.get_by_id(self.post_id)
            now = pendulum.now()

            embed = await post.embed()
            embed.add_field(
                name="Posted By",
                value=f"{interaction.user.mention}"
                    + f"\nTimestamp: <t:{now.int_timestamp}:R>",
                inline=False
                )

            self.button.label = f"Completed!"
            self.button.style = discord.ButtonStyle.green
            self.button.disabled = True
            
            await interaction.edit_original_response(embed=embed,view=self)

            post._last_posted = now.int_timestamp
            post._active_reminder = 0
            post.last_user = interaction.user.id
            await bot_client.run_in_thread(_update_post_in_db)
            bot_client.coc_main_log.info(f"Recruiting Reminder {post.ad_name} completed by {interaction.user.name}.")
        self.stop()