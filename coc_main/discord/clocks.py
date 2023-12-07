import discord
import pendulum
import requests

from typing import *
from redbot.core.utils import AsyncIter
from ..api_client import BotClashClient as client
from ..coc_objects.season.season import aClashSeason

bot_client = client()

class aGuildClocks():

    @classmethod
    async def get_for_guild(cls,guild_id:int):        
        database = await bot_client.coc_db.db__clock_config.find_one({'_id':guild_id})      
        if not database:
            return cls(guild_id,{})  
        return cls(guild_id,database)
        
    def __init__(self,guild_id:int,config:Optional[dict]=None):
        self.id = guild_id
        self.use_channels = config.get('use_channels',False) if config else False
        self.use_events = config.get('use_events',False) if config else False
        self._season_channel = config.get('season_channel',0) if config else 0
        self._raids_channel = config.get('raids_channel',0) if config else 0
        self._clangames_channel = config.get('clangames_channel',0) if config else 0
        self._warleague_channel = config.get('warleague_channel',0) if config else 0

    @property
    def guild(self):
        return bot_client.bot.get_guild(self.id)
    
    async def create_clock_channel(self):
        default_permissions = {
            self.guild.default_role: discord.PermissionOverwrite(
                connect=False,
                manage_channels=False,
                manage_permissions=False,
                manage_webhooks=False,
                create_instant_invite=False,
                send_messages=False)
            }
        clock_channel = await self.guild.create_voice_channel(
            name='🕐',
            overwrites=default_permissions
            )
        bot_client.coc_main_log.info(f"Guild {self.guild.name} {self.guild.id}: Created Clock Channel: {clock_channel.id}.")
        return clock_channel
    
    async def create_scheduled_event(self,
        name:str,
        start_time:pendulum.DateTime,
        end_time:pendulum.DateTime,
        image:str):

        def convert_image_to_bytes(url):
            response = requests.get(url,stream=True)
            response.raise_for_status()
            return response.content
        
        create_event = True
        
        async for event in AsyncIter(self.guild.scheduled_events):
            if event.name == name and event.start_time == start_time and event.end_time == end_time:
                create_event = False
                break        
        if not create_event:
            return event
        
        image_bytes = await bot_client.run_in_thread(convert_image_to_bytes,image)
        
        event = await self.guild.create_scheduled_event(
            name=name,
            start_time=start_time,
            end_time=end_time,
            privacy_level=discord.PrivacyLevel.guild_only,
            entity_type=discord.EntityType.external,
            image=image_bytes,
            location="In-Game"
            )
        bot_client.coc_main_log.info(f"Guild {self.guild.name} {self.guild.id}: Created Scheduled Event: {event.name} {event.id}.")
        return event    

    ##################################################
    ### CONFIGURATION
    ##################################################
    async def toggle_channels(self):
        if self.use_channels:
            self.use_channels = False
        else:
            self.use_channels = True
        await bot_client.coc_db.db__clock_config.update_one(
            {'_id':self.id},
            {'$set':{
                'use_channels':self.use_channels
                }
            },
            upsert=True)
    
    async def toggle_events(self):
        if self.use_events:
            self.use_events = False
        else:
            self.use_events = True
        await bot_client.coc_db.db__clock_config.update_one(
            {'_id':self.id},
            {'$set':{
                'use_events':self.use_events
                }
            },
            upsert=True)
    
    ##################################################
    ### SEASON CLOCKS
    ##################################################
    @property
    def season_channel(self) -> Optional[discord.VoiceChannel]:    
        channel = self.guild.get_channel(self._season_channel)
        if isinstance(channel,discord.VoiceChannel):
            return channel
        return None
    
    async def new_season_channel(self,channel_id:int):
        self._season_channel = channel_id        
        await bot_client.coc_db.db__clock_config.update_one(
            {'_id':self.id},
            {'$set':{
                'season_channel':self._season_channel
                }
            },
            upsert=True)

    async def update_season_channel(self):
        now = pendulum.now('UTC')
        
        if not self.season_channel:
            new_channel = await self.create_clock_channel()
            await new_channel.edit(position=0)
            await self.new_season_channel(new_channel.id)
    
        season_ch_name = f"📅 {bot_client.current_season.short_description} "
        time_to_end = bot_client.current_season.time_to_end(now)

        if time_to_end.days > 0:
            season_ch_name += f"({time_to_end.days}D left)"
        elif time_to_end.hours > 0:
            season_ch_name += f"({time_to_end.hours}H left)"        
        elif time_to_end.minutes > 0:
            season_ch_name += f"({time_to_end.minutes}M left)"

        if self.season_channel.name != season_ch_name:
            await self.season_channel.edit(name=season_ch_name)
            bot_client.coc_main_log.info(f"Guild {self.guild.name} {self.guild.id}: Season Channel updated to {season_ch_name}.")

    ##################################################
    ### RAID CLOCKS
    ##################################################
    @property
    def raids_channel(self) -> Optional[discord.VoiceChannel]:
        channel = self.guild.get_channel(self._raids_channel)
        if isinstance(channel,discord.VoiceChannel):
            return channel
        return None
    
    async def new_raids_channel(self,channel_id:int):
        self._raids_channel = channel_id
        await bot_client.coc_db.db__clock_config.update_one(
            {'_id':self.id},
            {'$set':{
                'raids_channel':self._raids_channel
                }
            },
            upsert=True)
    
    async def update_raidweekend_channel(self):
        now = pendulum.now('UTC')
        raid_start, raid_end = await aClashSeason.get_raid_weekend_dates(now)
        
        if not self.raids_channel:
            new_channel = await self.create_clock_channel()
            await new_channel.edit(position=1)
            await self.new_raids_channel(new_channel.id)

        raid_ch_name = None
        if now < raid_start < raid_end:
            raid_starts_in = now.diff(raid_start,False)

            if raid_starts_in.days > 0:
                raid_ch_name = f"🕐 Raids in {raid_starts_in.days}D {raid_starts_in.hours}H"
            elif raid_starts_in.hours > 0:
                raid_ch_name = f"🕐 Raids in {raid_starts_in.hours}H {raid_starts_in.minutes}M"
            elif raid_starts_in.minutes > 0:
                raid_ch_name = f"🕐 Raids in {raid_starts_in.minutes}M"
            else:
                raid_ch_name = f"🕐 Raids starting..."

        elif raid_start < now < raid_end:
            raid_ends_in = now.diff(raid_end,False)
            
            if raid_ends_in.days > 0:
                raid_ch_name = f"🟢 Raids end {raid_ends_in.days}D {raid_ends_in.hours}H"
            elif raid_ends_in.hours > 0:
                raid_ch_name = f"🟠 Raids end {raid_ends_in.hours}H {raid_ends_in.minutes}M"
            elif raid_ends_in.minutes > 0:
                raid_ch_name = f"🟠 Raids end {raid_ends_in.minutes}M"
            else:
                raid_ch_name = f"🔴 Raids ending..."

        elif raid_start < raid_end < now:
            raid_ch_name = f"🔴 Raids ended!"
        
        if raid_ch_name and self.raids_channel.name != raid_ch_name:
            await self.raids_channel.edit(name=raid_ch_name)
            bot_client.coc_main_log.info(f"Guild {self.guild.name} {self.guild.id}: Raids Channel updated to {raid_ch_name}.")

    async def update_raidweekend_event(self):
        now = pendulum.now('UTC')
        raid_start, raid_end = await aClashSeason.get_raid_weekend_dates(now)
        
        if raid_start.subtract(days=5) < now < raid_start:
            event = await self.create_scheduled_event(
                name="Raid Weekend",
                start_time=raid_start,
                end_time=raid_end,
                image="https://i.imgur.com/4n5xoLa.jpg"
                )                
            self.raids_event = event.id
    
    ##################################################
    ### CLAN GAMES CLOCKS
    ##################################################
    @property
    def clangames_channel(self) -> Optional[discord.VoiceChannel]:
        channel = self.guild.get_channel(self._clangames_channel)
        if isinstance(channel,discord.VoiceChannel):
            return channel
        return None

    async def new_clangames_channel(self,channel_id:int):
        self._clangames_channel = channel_id
        await bot_client.coc_db.db__clock_config.update_one(
            {'_id':self.id},
            {'$set':{
                'clangames_channel':self._clangames_channel
                }
            },
            upsert=True)
    
    async def update_clangames_channel(self):
        now = pendulum.now('UTC')
        season = aClashSeason.get_current_season()

        if season.clangames_start < season.clangames_end.add(hours=24) < now:
            clangames_season = season.next_season()
        else:
            clangames_season = season

        if not self.clangames_channel:
            new_channel = await self.create_clock_channel()
            await new_channel.edit(position=2)
            await self.new_clangames_channel(new_channel.id)

        cg_ch_name = None
        if now < clangames_season.clangames_start < clangames_season.clangames_end:
            cg_starts_in = now.diff(clangames_season.clangames_start,False)

            if cg_starts_in.days > 0:
                cg_ch_name = f"🕐 CG in {cg_starts_in.days}D {cg_starts_in.hours}H"
            elif cg_starts_in.hours > 0:
                cg_ch_name = f"🕐 CG in {cg_starts_in.hours}H {cg_starts_in.minutes}M"
            elif cg_starts_in.minutes > 0:
                cg_ch_name = f"🕐 CG in {cg_starts_in.minutes}M"
            else:
                cg_ch_name = f"🕐 CG starting..."

        elif clangames_season.clangames_start < now < clangames_season.clangames_end:
            cg_ends_in = now.diff(clangames_season.clangames_end,False)

            if cg_ends_in.days > 0:
                cg_ch_name = f"🟢 CG ends {cg_ends_in.days}D {cg_ends_in.hours}H"
            elif cg_ends_in.hours > 0:
                cg_ch_name = f"🟠 CG ends {cg_ends_in.hours}H {cg_ends_in.minutes}M"
            elif cg_ends_in.minutes > 0:
                cg_ch_name = f"🟠 CG ends {cg_ends_in.minutes}M"
            else:
                cg_ch_name = f"🔴 CG ending..."            

        elif clangames_season.clangames_start < clangames_season.clangames_end < now < clangames_season.clangames_end.add(hours=24):
            cg_ch_name = f"🔴 CG ended!"
        
        if cg_ch_name and self.clangames_channel.name != cg_ch_name:
            await self.clangames_channel.edit(name=cg_ch_name)
            bot_client.coc_main_log.info(f"Guild {self.guild.name} {self.guild.id}: Clan Games Channel updated to {cg_ch_name}.")           
    
    async def update_clangames_event(self):
        now = pendulum.now('UTC')
        season = aClashSeason.get_current_season()

        if season.clangames_start < season.clangames_end.add(hours=24) < now:
            clangames_season = season.next_season()
        else:
            clangames_season = season
        
        if clangames_season.clangames_start.subtract(days=14) < now < clangames_season.clangames_start:
            await self.create_scheduled_event(
                name=f"Clan Games - {clangames_season.short_description}",
                start_time=clangames_season.clangames_start,
                end_time=clangames_season.clangames_end,
                image="https://i.imgur.com/PwRPVYP.jpg"
                )
    
    ##################################################
    ### CLAN WAR LEAGUES CLOCKS
    ##################################################    
    @property
    def warleague_channel(self) -> Optional[discord.VoiceChannel]:
        channel = self.guild.get_channel(self._warleague_channel)
        if isinstance(channel,discord.VoiceChannel):
            return channel
        return None    
    
    async def new_league_channel(self,channel_id:int):
        self._warleague_channel = channel_id
        await bot_client.coc_db.db__clock_config.update_one(
            {'_id':self.id},
            {'$set':{
                'warleague_channel':self._warleague_channel
                }
            },
            upsert=True)
    
    async def update_warleagues_channel(self):
        now = pendulum.now('UTC')
        season = aClashSeason.get_current_season()

        if season.cwl_start < season.cwl_end.add(hours=24) < now:
            warleague_season = season.next_season()
        else:
            warleague_season = season

        if not self.warleague_channel:
            new_channel = await self.create_clock_channel()
            await new_channel.edit(position=3)
            await self.new_league_channel(new_channel.id)

        cwl_ch_name = None
        if now < warleague_season.cwl_start < warleague_season.cwl_end:
            time_to_cwl = now.diff(warleague_season.cwl_start,False)
            if time_to_cwl.days > 0:
                cwl_ch_name = f"🕐 CWL in {time_to_cwl.days}D {time_to_cwl.hours}H"
            elif time_to_cwl.hours > 0:
                cwl_ch_name = f"🕐 CWL in {time_to_cwl.hours}H {time_to_cwl.minutes}M"
            elif time_to_cwl.minutes > 0:
                cwl_ch_name = f"🕐 CWL in {time_to_cwl.minutes}M"
            else:
                cwl_ch_name = f"🕐 CWL starting..."

        elif warleague_season.cwl_start < now < warleague_season.cwl_end:
            cwl_ends_in = now.diff(warleague_season.cwl_end,False)

            if cwl_ends_in.days > 0:
                cwl_ch_name = f"🟢 CWL ends {cwl_ends_in.days}D {cwl_ends_in.hours}H"
            elif cwl_ends_in.hours > 0:
                cwl_ch_name = f"🟠 CWL ends {cwl_ends_in.hours}H {cwl_ends_in.minutes}M"
            elif cwl_ends_in.minutes > 0:
                cwl_ch_name = f"🟠 CWL ends {cwl_ends_in.minutes}M"
            else:
                cwl_ch_name = f"🔴 CWL ending..."
            
        if warleague_season.cwl_start < warleague_season.cwl_end < now < warleague_season.cwl_end.add(hours=24):
            cwl_ch_name = f"🔴 CWL ended"
        
        if cwl_ch_name and self.warleague_channel.name != cwl_ch_name:
            await self.warleague_channel.edit(name=cwl_ch_name)
            bot_client.coc_main_log.info(f"Guild {self.guild.name} {self.guild.id}: CWL Channel updated to {cwl_ch_name}.")
    
    async def update_warleagues_event(self):
        now = pendulum.now('UTC')
        season = aClashSeason.get_current_season()

        if season.cwl_start < season.cwl_end.add(hours=24) < now:
            warleague_season = season.next_season()
        else:
            warleague_season = season
        
        if warleague_season.cwl_start.subtract(days=14) < now < warleague_season.cwl_start:
           await self.create_scheduled_event(
                name=f"Clan War Leagues - {warleague_season.short_description}",
                start_time=warleague_season.cwl_start,
                end_time=warleague_season.cwl_end,
                image="https://i.imgur.com/NYmlLJz.jpg"
                )