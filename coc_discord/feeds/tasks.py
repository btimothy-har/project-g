import asyncio
import coc

from typing import *
from redbot.core.utils import AsyncIter, bounded_gather

from coc_main.client.global_client import GlobalClient

from coc_main.coc_objects.clans.clan import aClan
from coc_main.coc_objects.events.clan_war import aClanWar
from coc_main.coc_objects.events.clan_war_leagues import WarLeagueGroup
from coc_main.coc_objects.events.raid_weekend import aRaidWeekend
from coc_main.discord.member import aMember
from coc_main.discord.clan_link import ClanGuildLink
 
from coc_main.utils.constants.coc_constants import WarState

from .donations import ClanDonationFeed
from .member_movement import ClanMemberFeed
from .reminders import EventReminder
from .raid_results import RaidResultsFeed

default_sleep = 60

############################################################
############################################################
#####
##### EVENT TASKS
#####
############################################################
############################################################
class FeedTasks():

    @staticmethod
    async def _setup_cwl_reminder(clan:aClan,league_group:WarLeagueGroup):        
        league_clan = league_group.get_clan(clan.tag)
        war_reminders = await EventReminder.war_reminders_for_clan(clan)

        if league_clan and league_clan.league_channel:
            war_league_reminder = [r for r in war_reminders if r.channel_id == league_clan.league_channel.id and 'cwl' in r.sub_type]
            if len(war_league_reminder) == 0:
                await EventReminder.create_war_reminder(
                    clan=clan,
                    channel=league_clan.league_channel,
                    war_types=['cwl'],
                    interval=[12,8,6,4,3,2,1],
                    )

    @staticmethod
    async def _setup_war_reminder(clan:aClan,current_war:aClanWar):
        async def send_reminder(reminder:EventReminder):
            if current_war.type in reminder.sub_type:
                reminder_clan = current_war.get_clan(clan.tag)
                remind_members = [m for m in reminder_clan.members if m.unused_attacks > 0]
                await reminder.send_reminder(current_war,*remind_members)
        
        if current_war.state == WarState.INWAR:
            war_reminders = await EventReminder.war_reminders_for_clan(clan)
            rem_iter = AsyncIter(war_reminders)
            await bounded_gather(*[send_reminder(reminder) async for reminder in rem_iter])
    
    @staticmethod
    async def _setup_raid_reminder(clan:aClan,current_raid:aRaidWeekend):

        async def send_reminder(reminder:EventReminder):    
            remind_members = [m for m in current_raid.members if m.attack_count < 6]
            await reminder.send_reminder(current_raid,*remind_members)
        
        raid_reminders = await EventReminder.raid_reminders_for_clan(clan)
        rem_iter = AsyncIter(raid_reminders)
        await bounded_gather(*[send_reminder(reminder) async for reminder in rem_iter])
    
    @staticmethod
    async def _raid_ended_feed(clan:aClan,raid:aRaidWeekend):
        await asyncio.sleep(240)
        if raid.attack_count > 0:
            new_clan = await GlobalClient.coc_client.get_clan(clan.tag)
            await RaidResultsFeed.start_feed(new_clan,raid)
        
    @coc.ClanEvents.total_clan_donations()
    async def on_clan_donation_change(old_clan:aClan,new_clan:aClan):
        await ClanDonationFeed.start_feed(new_clan,old_clan)    
    
    @coc.ClanEvents.member_join()
    async def on_clan_member_join_feed(member:coc.ClanMember,clan:aClan):
        await ClanMemberFeed.member_join(clan,member)

    @coc.ClanEvents.member_leave()
    async def on_clan_member_leave_feed(member:coc.ClanMember,clan:aClan):
        await ClanMemberFeed.member_leave(clan,member)
    
    @coc.ClanEvents.member_join()
    async def on_clan_member_join_role(member:coc.ClanMember,clan:aClan):
        player = await GlobalClient.coc_client.get_player(member.tag)

        if player.discord_user:
            clan_links = await ClanGuildLink.get_links_for_clan(clan.tag)

            if clan_links and len(clan_links) > 0:
                link_iter = AsyncIter(clan_links)
                async for link in link_iter:
                    if not link.guild:
                        continue
                    if not link.visitor_role:
                        continue
                    
                    discord_user = link.guild.get_member(player.discord_user)
                    if not discord_user:
                        continue

                    member = await aMember(discord_user.id,link.guild.id)

                    if clan.tag not in [c.tag for c in member.home_clans]:
                        await discord_user.add_roles(
                            link.visitor_role,
                            reason=f"Joined {clan.name}: {player.name} ({player.tag})"
                            )
    
    @coc.ClanEvents.member_leave()
    async def on_clan_member_leave_role(member:coc.ClanMember,clan:aClan):
        player = await GlobalClient.coc_client.get_player(member.tag)

        if player.discord_user:
            member = await aMember(player.discord_user)

            member_accounts = [p async for p in GlobalClient.coc_client.get_player(member.account_tags)]
            clan_links = await ClanGuildLink.get_links_for_clan(clan.tag)
            
            if clan_links and len(clan_links) > 0:
                link_iter = AsyncIter(clan_links)
                async for link in link_iter:
                    if not link.guild:
                        continue
                    if not link.visitor_role:
                        continue

                    discord_user = link.guild.get_member(player.discord_user)
                    if not discord_user:
                        continue
                    
                    all_clans = [a.clan for a in member_accounts if a.clan]
                    if clan.tag not in [c.tag for c in all_clans] and link.visitor_role in discord_user.roles:                    
                        await discord_user.remove_roles(
                            link.visitor_role,
                            reason=f"Left {clan.name}: {player.name} ({player.tag})"
                            )