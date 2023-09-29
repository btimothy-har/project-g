import discord
import pendulum

from coc_client.api_client import BotClashClient

from ..objects.players.player import aPlayer
from ..objects.clans.clan import aClan
from ..objects.events.clan_war import aClanWar
from ..objects.events.raid_weekend import aRaidWeekend

from ..utilities.utils import *
from ..utilities.components import *

class MemberReminder():
    def __init__(self,member:discord.Member):
        self.member = member
        self.accounts = []
    
    def add_account(self,account:aPlayer):
        self.accounts.append(account)

class EventReminders():
    def __init__(self,channel_id:int):
        self.client = BotClashClient()
        self.bot = self.client.bot

        self.channel = self.bot.get_channel(channel_id)
        self.guild = getattr(self.channel,'guild',None)
        self.member_reminders = {}

    def __len__(self):
        return len(self.member_reminders)
    
    @property
    def reminder_text(self):
        for r_member in list(self.member_reminders.values()):
            account_str = [f"\n{a.title}" for a in r_member.accounts]
            reminder_text += f"{r_member.member.mention}" +', '.join(account_str) + '\n\n'
        return reminder_text
    
    async def add_account(self,player_tag:str):
        player = await aPlayer.create(player_tag)
        try:
            member = await self.bot.get_or_fetch_member(self.guild,player.discord_user)
        except (discord.Forbidden,discord.NotFound):
            member = None

        if not member:
            return
        
        if not self.member_reminders.get(member.id):
            self.member_reminders[member.id] = MemberReminder(member)        
        self.member_reminders[member.id].add_account(player)
    
    async def send_war_reminders(self,clan:aClan,clan_war:aClanWar):
        if len(self) == 0:
            return
        
        time_remaining = clan_war.end_time.int_timestamp - pendulum.now().int_timestamp
        rd, rh, rm, rs = s_convert_seconds_to_str(time_remaining)
        remain_str = ""
        if rd > 0:
            remain_str += f"{int(rd)}D "
        if rh > 0:
            remain_str += f"{int(rh)}H "
        remain_str += f"{int(rm)}M "
            
        reminder_text = f"You have **NOT** used all of your War Attacks. Clan War ends in **{remain_str}**(<t:{clan_war.end_time.int_timestamp}:f>)\n\n"
        reminder_text += self.reminder_text

        webhook = await get_bot_webhook(self.bot,self.channel)
        if isinstance(self.channel,discord.Thread):
            r_msg = await webhook.send(
                username=clan.name,
                avatar_url=clan.badge,
                content=reminder_text,
                thread=self.channel,
                wait=True
                )
        else:
            r_msg = await webhook.send(
                username=clan.name,
                avatar_url=clan.badge,
                content=reminder_text,
                wait=True
                )
        self.client.cog.coc_main_log.info(f"Clan {clan}: Sent War Reminders to {len(self)} players. Reminder ID: {r_msg.id}")
    
    async def send_raid_reminders(self,clan:aClan,raid_weekend:aRaidWeekend):
        if len(self) == 0:
            return

        time_remaining = raid_weekend.end_time.int_timestamp - pendulum.now().int_timestamp
        rd, rh, rm, rs = s_convert_seconds_to_str(time_remaining)
        remain_str = ""
        if rd > 0:
            remain_str += f"{int(rd)}D "
        if rh > 0:
            remain_str += f"{int(rh)}H "
        remain_str += f"{int(rm)}M "

        reminder_text = f"You started your Raid Weekend but **HAVE NOT** used all your Raid Attacks. Raid Weekend ends in **{remain_str}**(<t:{raid_weekend.end_time.int_timestamp}:f>).\n\n"
        reminder_text += self.reminder_text

        webhook = await get_bot_webhook(self.bot,self.channel)

        if isinstance(self.channel,discord.Thread):
            await webhook.send(
                username=clan.name,
                avatar_url=clan.badge,
                content=reminder_text,
                thread=self.channel
                )
        else:
            await webhook.send(
                username=clan.name,
                avatar_url=clan.badge,
                content=reminder_text,
                )
        self.client.cog.coc_main_log.info(f"Clan {clan}: Sent Raid Reminders to {len(self)} players.")