import discord
import pendulum

from ...api_client import BotClashClient as client
from ...cog_coc_client import ClashOfClansClient

from ...coc_objects.players.player import aPlayer
from ...coc_objects.clans.clan import aClan
from ...coc_objects.events.clan_war import aClanWar
from ...coc_objects.events.raid_weekend import aRaidWeekend

from ...utils.components import get_bot_webhook, s_convert_seconds_to_str

bot_client = client()

class MemberReminder():
    def __init__(self,member:discord.Member):
        self.member = member
        self.accounts = []
    
    def add_account(self,account:aPlayer):
        self.accounts.append(account)

class EventReminders():
    def __init__(self,channel_id:int):
        self.channel = bot_client.bot.get_channel(channel_id)
        self.guild = getattr(self.channel,'guild',None)
        self.member_reminders = {}

    def __len__(self):
        return len(self.member_reminders)
    
    @property
    def coc_client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    @property
    def reminder_text(self):
        reminder_text = ""
        for r_member in list(self.member_reminders.values()):
            account_str = [f"\n{a.title}" for a in r_member.accounts]
            reminder_text += f"{r_member.member.mention}" +', '.join(account_str) + '\n\n'
        return reminder_text
    
    async def add_account(self,player_tag:str):
        try:
            player = await self.coc_client.fetch_player(player_tag)
            try:
                member = await bot_client.bot.get_or_fetch_member(self.guild,player.discord_user)
            except (discord.Forbidden,discord.NotFound):
                member = None

            if not member:
                return
            
            if not self.member_reminders.get(member.id):
                self.member_reminders[member.id] = MemberReminder(member)        
            self.member_reminders[member.id].add_account(player)
        except:
            bot_client.coc_main_log.exception(f"Error adding account {player_tag} to reminder in {getattr(self.channel,'id','Unknown Channel')}.")
    
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

        webhook = await get_bot_webhook(bot_client.bot,self.channel)
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
        bot_client.coc_main_log.info(f"Clan {clan}: Sent War Reminders to {len(self)} players. Reminder ID: {r_msg.id}")
    
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

        webhook = await get_bot_webhook(bot_client.bot,self.channel)

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
        bot_client.coc_main_log.info(f"Clan {clan}: Sent Raid Reminders to {len(self)} players.")