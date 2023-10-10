import discord

from typing import *
from mongoengine import *

from ..api_client import BotClashClient as client
from ..coc_objects.clans.clan import aClan

from .mongo_discord import db_GuildClanPanel
from ..utils.components import ClanLinkMenu

bot_client = client()

class GuildClanPanel():

    @classmethod
    def get_panel(cls,guild_id:int,channel_id:int):
        try:
            panel = db_GuildClanPanel.objects.get(
                server_id=guild_id,
                channel_id=channel_id
                )
        except DoesNotExist:
            return None
        return cls(panel)
    
    @classmethod
    def get_from_id(cls,panel_id:dict):
        try:
            panel = db_GuildClanPanel.objects.get(panel_id=panel_id)
        except DoesNotExist:
            return None
        return cls(panel)
    
    def __init__(self,database_entry:db_GuildClanPanel):        
        self.id = database_entry.panel_id
        self.guild_id = database_entry.server_id
        self.channel_id = database_entry.channel_id
        self.message_id = database_entry.message_id
        self.long_message_ids = database_entry.long_message_ids
        self.embeds = []
    
    def __str__(self):
        return f"Clan Panel (Channel: {getattr(self.channel,'name','Unknown Channel')})"
    
    @classmethod
    async def create(cls,guild_id:int,channel_id:int):
        panel_id = {'guild':guild_id,'channel':channel_id}
        try:
            panel = db_GuildClanPanel.objects.get(
                server_id=guild_id,
                channel_id=channel_id
                )
        except DoesNotExist:
            panel = db_GuildClanPanel(
                panel_id = panel_id,
                server_id = guild_id,
                channel_id = channel_id
                )
            panel.save()        
        return cls(panel)
    
    async def delete(self):
        db_GuildClanPanel.objects(panel_id=self.id).delete()
        async for m_id in self.long_message_ids:
            try:
                message = await self.channel.fetch_message(m_id)
            except discord.NotFound:
                pass
            else:
                await message.delete()
    
    def save(self):
        db_panel = db_GuildClanPanel(
            panel_id = self.id,
            server_id = self.guild_id,
            channel_id = self.channel_id,
            message_id = self.message_id,
            long_message_ids = self.long_message_ids
            )
        db_panel.save()
    
    @property
    def guild(self):
        return bot_client.bot.get_guild(self.guild_id)
    
    @property
    def channel(self):
        return self.guild.get_channel(self.channel_id)
    
    async def fetch_message(self):
        if self.channel:
            try:
                return await self.channel.fetch_message(self.message_id)
            except discord.NotFound:
                pass
        return None
    
    async def send_to_discord(self,embeds:list[discord.Embed]):        
        try:
            if not self.channel:
                self.delete()
                return

            message_ids_master = []
            existing_messages = len(self.long_message_ids)

            #iterate through embeds up to len existing messages
            for i,send_message in enumerate(embeds[:existing_messages]):
                link_button = ClanLinkMenu([send_message['clan']])
                try:
                    message = await self.channel.fetch_message(self.long_message_ids[i])
                except discord.NotFound:
                    message = await self.channel.send(
                        embed=send_message['embed'],
                        view=link_button
                        )
                    message_ids_master.append(message.id)
                else:
                    message = await message.edit(
                        embed=send_message['embed'],
                        view=link_button
                        )
                    message_ids_master.append(message.id)
            
            #iterate through remaining embeds
            for send_message in embeds[existing_messages:]:
                link_button = ClanLinkMenu([send_message['clan']])
                message = await self.channel.send(
                    embed=send_message['embed'],
                    view=link_button
                    )
                message_ids_master.append(message.id)
            
            #delete any remaining messages
            for message_id in self.long_message_ids[len(embeds):]:
                try:
                    message = await self.channel.fetch_message(message_id)
                except discord.NotFound:
                    pass
                else:
                    await message.delete()
            
            db_GuildClanPanel.objects(panel_id=self.id).update(
                set__message_id=message_ids_master[0],
                set__long_message_ids=message_ids_master
                )

        except Exception as exc:
            bot_client.coc_main_log.exception(
                f"Error sending Clan Panel to Discord: {self.guild.name} {getattr(self.channel,'name','Unknown Channel')}. {exc}"
                )