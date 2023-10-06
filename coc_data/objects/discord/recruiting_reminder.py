import asyncio
import discord
import pendulum

from typing import *
from mongoengine import *

from coc_client.api_client import BotClashClient

from coc_data.utilities.components import *
from coc_data.utilities.utils import *
from coc_data.constants.coc_emojis import *
from coc_data.constants.ui_emojis import *

bot_client = BotClashClient()

class db_RecruitingPost(Document):
    is_active = BooleanField(default=False)
    ad_name = StringField(required=True)
    ad_link = StringField(required=True)
    guild = IntField(default=0)
    channel = IntField(default=0)
    interval = IntField(required=True)
    remind_user = IntField(default=0)
    last_posted = IntField(default=0)
    last_user = IntField(default=0)
    active_reminder = IntField(default=0)
    logs = ListField(DictField(),default=[])

class RecruitingReminder():
    _cache = {}

    @classmethod
    def get_by_guild(cls,guild_id:int):
        posts = db_RecruitingPost.objects(guild=guild_id).only("id")
        return [cls(post.id) for post in posts]

    @classmethod
    def get_all(cls):
        posts = db_RecruitingPost.objects(is_active=True).only("id")
        return [cls(post.id) for post in posts]

    def __new__(cls,post_id):
        if str(post_id) not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[str(post_id)] = instance
        return cls._cache[str(post_id)]
    
    def __init__(self,post_id):
        self.id = post_id
        
        if self._is_new:
            try:
                db = db_RecruitingPost.objects.get(id=self.id).to_mongo().to_dict()
            except DoesNotExist:
                raise Exception()
            
            self.lock = asyncio.Lock()

            self._is_active = db.get("is_active",False)
            self._ad_name = db.get("ad_name","")
            self._ad_link = db.get("ad_link","")
            self._interval = db.get("interval",0)
            self._remind_user = db.get("remind_user",0)
            self._last_posted = db.get("last_posted",0)
            self._last_user = db.get("last_user","")
            self._channel = db.get("channel",0)
            self._active_reminder = db.get("active_reminder",0)
            self._logs = db.get("logs",[])
        self._is_new = False
    
    def __str__(self):
        s = f"{self.ad_name}: every {self.interval}hr(s) for {getattr(self.remind_user,'name','Unknown')} in {getattr(self.channel,'name','Unknown Channel')}."
        # if self.next_reminder:
        #     if pendulum.now() > self.next_reminder:
        #         s += f"Next: *soon...*"
        #     else:
        #         s += f"Next: <t:{getattr(self.next_reminder,'int_timestamp',0)}:R>"
        return s
    
    ##################################################
    ### CREATE / DELETE
    ##################################################
    @classmethod
    async def create(cls,channel:discord.TextChannel,user_to_remind:discord.Member,name:str,link:str,interval:int):
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
        ret_post = new_post.save()
        return cls(str(ret_post.pk))

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
                self._is_active = False
            except:
                pass
            db_RecruitingPost.objects.get(id=self.id).delete()
        type(self)._cache.pop(self.id)
    
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
                view = RecruitingPostPrompt(self)

                webhook = await get_bot_webhook(bot_client.bot,self.channel)
                if isinstance(self.channel,discord.Thread):
                    self.active_reminder = await webhook.send(
                        wait=True,
                        username=bot_client.bot.user.name,
                        content=getattr(self.remind_user,'mention',''),
                        embed=post_embed,
                        view=view,
                        thread=self.channel,
                        )
                else:
                    self.active_reminder = await webhook.send(
                        wait=True,
                        username=bot_client.bot.user.name,
                        content=getattr(self.remind_user,'mention',''),
                        embed=post_embed,
                        view=view,
                        )
                bot_client.cog.coc_main_log.info(f"Recruiting Reminder sent for {self.ad_name}.")
        
            except asyncio.CancelledError:
                return None
            except Exception as exc:
                bot_client.cog.coc_main_log.exception(f"Recruiting Reminder failed for {self.ad_name}.")
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
            view = RecruitingPostPrompt(self)
            webhook = await get_bot_webhook(bot_client.bot,self.channel)
            if isinstance(self.channel,discord.Thread):
                self.active_reminder = await webhook.edit_message(
                    message_id=self.active_reminder,
                    content=getattr(self.remind_user,'mention',''),
                    embed=post_embed,
                    view=view,
                    thread=self.channel
                    )
            else:
                self.active_reminder = await webhook.edit_message(
                    message_id=self.active_reminder,
                    content=getattr(self.remind_user,'mention',''),
                    embed=post_embed,
                    view=view
                    )
    
    ##################################################
    ### CLASS PROPERTIES
    ##################################################
    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def ad_name(self) -> str:
        return self._ad_name
    @ad_name.setter
    def ad_name(self,value:str):
        self._ad_name = value
        db = db_RecruitingPost.objects.get(id=self.id)
        db.ad_name = value
        db.save()
    
    @property
    def ad_link(self) -> str:
        return self._ad_link
    @ad_link.setter
    def ad_link(self,value:str):
        self._ad_link = value
        db_RecruitingPost.objects(id=self.id).update_one(set__ad_link=value)

    @property
    def interval(self) -> int:
        return self._interval
    @interval.setter
    def interval(self,value:int):
        self._interval = value
        db_RecruitingPost.objects(id=self.id).update_one(set__interval=value)
    
    @property
    def remind_user(self) -> Optional[discord.User]:
        return bot_client.bot.get_user(self._remind_user)
    @remind_user.setter
    def remind_user(self,value:int):
        self._remind_user = value
        db_RecruitingPost.objects(id=self.id).update_one(set__remind_user=value)
    
    @property
    def last_posted(self) -> Optional[pendulum.DateTime]:
        if self._last_posted == 0:
            return None
        return pendulum.from_timestamp(self._last_posted)
    @last_posted.setter
    def last_posted(self,timestamp:pendulum.DateTime):
        self._last_posted = timestamp.int_timestamp
        db_RecruitingPost.objects(id=self.id).update_one(set__last_posted=timestamp.int_timestamp)
    
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
    def last_user(self) -> int:
        return self._last_user
    @last_user.setter
    def last_user(self,user_id:int):
        self._last_user = user_id
        db_RecruitingPost.objects(id=self.id).update_one(set__last_user=user_id)

    @property
    def channel(self) -> Optional[Union[discord.TextChannel,discord.Thread]]:
        return bot_client.bot.get_channel(self._channel)
    @channel.setter
    def channel(self,channel_id:int):
        channel = bot_client.bot.get_channel(channel_id)
        if isinstance(channel,(discord.TextChannel,discord.Thread)):
            self._channel = channel.id
        else:
            self._channel = 0
        db_RecruitingPost.objects(id=self.id).update_one(set__channel=self._channel)
    
    @property
    def active_reminder(self) -> int:
        if self._active_reminder == 0:
            return None
        return self._active_reminder
    @active_reminder.setter
    def active_reminder(self,message:Optional[discord.WebhookMessage]=None):
        if message is None:
            self._active_reminder = 0
        else:
            self._active_reminder = message.id
        db_RecruitingPost.objects(id=self.id).update_one(set__active_reminder=self._active_reminder)

    @property
    def logs(self) -> list:
        return self._logs
    @logs.setter
    def logs(self,new_log:discord.Interaction):
        new_log = {
            "user":new_log.user.id,
            "timestamp":new_log.created_at.timestamp(),
            }
        self._logs.append(new_log)
        db_RecruitingPost.objects(id=self.id).update_one(push__logs=new_log)

class RecruitingPostPrompt(discord.ui.View):
    def __init__(self,post:RecruitingReminder):
        self.post = post
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

        async with self.post.lock:
            now = pendulum.now()

            embed = await self.post.embed()
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

            self.post.last_posted = now
            self.post.last_user = interaction.user.id
            self.post.active_reminder = None
            self.post.logs = interaction

        self.stop()        