import pendulum
import coc

from typing import *
from redbot.core.utils import AsyncIter


from coc_main.api_client import BotClashClient as client
from coc_main.cog_coc_client import ClashOfClansClient

from coc_main.coc_objects.clans.clan import aClan
from coc_main.discord.member import aMember
from coc_main.discord.feeds.donations import ClanDonationFeed
from coc_main.discord.feeds.member_movement import ClanMemberFeed
from coc_main.discord.clan_link import ClanGuildLink

bot_client = client()
default_sleep = 60

############################################################
############################################################
#####
##### DEFAULT CLAN TASKS
#####
############################################################
############################################################
class ClanTasks():

    @staticmethod
    def _get_client() -> ClashOfClansClient:
        return bot_client.bot.get_cog('ClashOfClansClient')

    @coc.ClanEvents.total_clan_donations()
    async def on_clan_donation_change(old_clan:aClan,new_clan:aClan):
        await ClanDonationFeed.start_feed(new_clan,old_clan)

    @coc.ClanEvents.member_count()
    @coc.ClanEvents.total_clan_donations()
    async def on_clan_activity(old_clan:aClan,new_clan:aClan):
        await new_clan._sync_cache(force=True)
    
    @coc.ClanEvents.member_join()
    async def on_clan_member_join_feed(member:coc.ClanMember,clan:aClan):
        await ClanMemberFeed.member_join(clan,member)

    @coc.ClanEvents.member_join()
    async def on_clan_member_join_capture(member:coc.ClanMember,clan:aClan):
        await bot_client.player_queue.put(member.tag)
    
    @coc.ClanEvents.member_leave()
    async def on_clan_member_leave_feed(member:coc.ClanMember,clan:aClan):
        await ClanMemberFeed.member_leave(clan,member)

    @coc.ClanEvents.member_leave()
    async def on_clan_member_leave_capture(member:coc.ClanMember,clan:aClan):
        await bot_client.player_queue.put(member.tag)
    
    @coc.ClanEvents.member_join()
    async def on_clan_member_join_role(member:coc.ClanMember,clan:aClan):
        n_player = await bot_client.coc.get_player(member.tag)

        if n_player.discord_user:
            clan_links = await ClanGuildLink.get_links_for_clan(clan.tag)

            if clan_links and len(clan_links) > 0:
                link_iter = AsyncIter(clan_links)
                async for link in link_iter:
                    if not link.guild:
                        continue
                    if not link.visitor_role:
                        continue
                    
                    discord_user = link.guild.get_member(n_player.discord_user)
                    if not discord_user:
                        continue

                    member = await aMember(discord_user.id,link.guild.id)
                    await member.load()

                    if clan.tag not in [c.tag for c in member.home_clans]:
                        await discord_user.add_roles(
                            link.visitor_role,
                            reason=f"Joined {clan.name}: {n_player.name} ({n_player.tag})"
                            )
    
    @coc.ClanEvents.member_leave()
    async def on_clan_member_leave_role(member:coc.ClanMember,clan:aClan):
        n_player = await bot_client.coc.get_player(member.tag)

        if n_player.discord_user:
            member = await aMember(n_player.discord_user)
            await member.load()

            member_accounts = [p async for p in bot_client.coc.get_players(member.account_tags)]
            clan_links = await ClanGuildLink.get_links_for_clan(clan.tag)
            
            if clan_links and len(clan_links) > 0:
                link_iter = AsyncIter(clan_links)
                async for link in link_iter:
                    if not link.guild:
                        continue
                    if not link.visitor_role:
                        continue

                    discord_user = link.guild.get_member(n_player.discord_user)
                    if not discord_user:
                        continue
                    
                    all_clans = [a.clan for a in member_accounts if a.clan]
                    if clan.tag not in [c.tag for c in all_clans] and link.visitor_role in discord_user.roles:                    
                        await discord_user.remove_roles(
                            link.visitor_role,
                            reason=f"Left {clan.name}: {n_player.name} ({n_player.tag})"
                            )