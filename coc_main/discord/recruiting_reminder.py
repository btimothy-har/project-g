import asyncio
import discord
import pendulum

from typing import *
from mongoengine import *

from collections import defaultdict
from ..api_client import BotClashClient as client

from .mongo_discord import db_RecruitingPost

from ..utils.components import get_bot_webhook, clash_embed, DiscordButton
from ..utils.constants.ui_emojis import EmojisUI

bot_client = client()

class RecruitingReminder():
    _locks = defaultdict(asyncio.Lock)
    __slots__ = [
        '_id',
        'is_active',
        'ad_name',
        'ad_link',
        'guild_id',
        'channel_id',
        'remind_user_id',
        'interval',
        'last_user_id',
        'active_reminder_id',
        'last_posted',
        ]

    @classmethod
    async def get_by_id(cls,id:str) -> 'RecruitingReminder':
        query = await bot_client.coc_db.db__recruiting_post.find_one({'_id':id})
        if query:
            return cls(query)
        return None

    @classmethod
    async def get_for_guild(cls,guild_id:int) -> List['RecruitingReminder']:
        query_doc = {'is_active':True,'guild':guild_id}
        query = bot_client.coc_db.db__recruiting_post.find(query_doc)
        return [cls(post) async for post in query]

    @classmethod
    async def get_all_active(cls):
        query_doc = {'is_active':True}
        query = bot_client.coc_db.db__recruiting_post.find(query_doc)
        return [cls(post) async for post in query]
    
    def __init__(self,database:dict):
        self.id = database['_id']

        self.is_active = database.get('is_active',False)

        self.ad_name = database.get('ad_name',None)
        self.ad_link = database.get('ad_link',None)
        
        self.guild_id = database.get('guild',None)
        self.channel_id = database.get('channel',None)
        self.remind_user_id = database.get('remind_user',None)
        
        self.interval = database.get('interval',None)

        self.last_user_id = database.get('last_user',None)
        self.active_reminder_id = database.get('active_reminder',0)
        
        if database.get('last_posted',None):
            self.last_posted = pendulum.from_timestamp(database['last_posted'])
        else:
            self.last_posted = None
    
    def __str__(self):
        return f"{self.ad_name}: every {self.interval}hr(s) for {getattr(self.remind_user,'display_name','Unknown')} in {getattr(self.channel,'name','Unknown Channel')}"
    
    @property
    def lock(self) -> asyncio.Lock:
        return self._locks[self.id]

    @property
    def guild(self) -> Optional[discord.Guild]:
        return bot_client.bot.get_guild(self._guild)
    
    @property
    def channel(self) -> Optional[Union[discord.TextChannel,discord.Thread]]:
        return bot_client.bot.get_channel(self._channel)
    
    @property
    def remind_user(self) -> Optional[discord.User]:
        return self.guild.get_member(self.remind_user_id)
    
    @property
    def active_reminder(self) -> int:
        if self.active_reminder_id or self.active_reminder_id == 0:
            return None
        return self.active_reminder_id   
    
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
    
    ##################################################
    ### CREATE / DELETE
    ##################################################
    @classmethod
    async def create(cls,channel:discord.TextChannel,user_to_remind:discord.Member,name:str,link:str,interval:int):
        new_post = await bot_client.coc_db.db__recruiting_post.insert_one({
            'is_active':True,
            'ad_name':name,
            'ad_link':link,
            'guild':channel.guild.id,
            'channel':channel.id,
            'interval':interval,
            'remind_user':user_to_remind.id,
            'last_posted':0,
            'last_user':0,
            'active_reminder':0,
            'logs':[]
            })
        return await cls.get_by_id(new_post.inserted_id)

    async def update_active_reminder(self,reminder_id:int):
        async with self.lock:
            self.active_reminder_id = reminder_id
            await bot_client.coc_db.db__recruiting_post.update_one(
                {'_id':self.id},
                {'$set': 
                    {'active_reminder':self.active_reminder_id}
                },
                upsert=True
                )
            bot_client.coc_main_log.info(f"{self.ad_name} {self.id} updated active reminder to {self.active_reminder_id}.")
    
    async def completed(self,user:discord.User):
        async with self.lock:
            self.last_posted = pendulum.now()
            self.last_user_id = user.id
            self.active_reminder_id = 0
            await bot_client.coc_db.db__recruiting_post.update_one(
                {'_id':self.id},
                {'$set': 
                    {
                        'last_posted':self.last_posted.int_timestamp,
                        'last_user':self.last_user_id,
                        'active_reminder':self.active_reminder_id}
                })
            bot_client.coc_main_log.info(f"Recruiting Reminder {self.ad_name} completed by {user.name}.")

    async def delete(self):
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
                self.is_active = False
            except:
                pass
            await bot_client.coc_db.db__recruiting_post.delete_one({'_id':self.id})
    
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
                await self.update_active_reminder(msg.id)
                bot_client.coc_main_log.info(f"Recruiting Reminder sent for {self.ad_name}.")
        
            except asyncio.CancelledError:
                return None
            except Exception as exc:
                bot_client.coc_main_log.exception(f"Recruiting Reminder failed for {self.ad_name}.")
                return exc
            else:
                return self
    
    async def refresh_reminder(self):
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
            await self.update_active_reminder(msg.id)

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
        if not interaction.response.is_done():
            await interaction.response.defer()
        
        post = await RecruitingReminder.get_by_id(self.post_id)

        embed = await post.embed()
        embed.add_field(
            name="Posted By",
            value=f"{interaction.user.mention}"
                + f"\nTimestamp: <t:{pendulum.now().int_timestamp}:R>",
            inline=False
            )

        self.button.label = f"Completed!"
        self.button.style = discord.ButtonStyle.green
        self.button.disabled = True
        
        await interaction.edit_original_response(embed=embed,view=self)
        await post.completed(interaction.user)
            
        self.stop()