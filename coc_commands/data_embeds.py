import discord
import asyncio
import re

from collections import Counter

from typing import *
from redbot.core import commands
from redbot.core.utils import AsyncIter

from coc_data.objects.players.player import aPlayer
from coc_data.objects.clans.clan import aClan
from coc_data.utilities.components import *
from coc_data.utilities.utils import *
from coc_data.constants.coc_emojis import *
from coc_data.constants.ui_emojis import *

async def clan_composition_embed(context:Union[commands.Context,discord.Interaction],clan:aClan):
    embed = await clash_embed(
        context=context,
        title=f"{clan.title}",
        message=f"**Clan Member Composition**",
        thumbnail=clan.badge,
        )            
    fetch_member_tasks = [asyncio.create_task(aPlayer.create(member.tag)) for member in clan.members]

    if clan.is_alliance_clan and clan.alliance_member_count > 0:
        clan_members = clan.alliance_members
        townhall_levels = [member.town_hall.level for member in clan_members]
        townhall_levels.sort(reverse=True)
        average_townhall = round(sum(townhall_levels)/len(townhall_levels),2)
        townhall_counts = Counter(townhall_levels)
        
        embed.add_field(
            name="**Registered Members**",
            value=f"Total: {len(clan_members)} {EmojisUI.MEMBERS}\n"
                + f"Average: {EmojisTownHall.get(int(average_townhall))} {average_townhall}\n\n"
                + "\n".join([
                    f"{EmojisTownHall.get(th)} `TH{th:02}`: {(count/len(clan_members))*100:.1f}% ({count})"
                    for th, count in townhall_counts.items()
                    ])
                + "\n\u200b",
            inline=False,
            )
    
    ingame_members = await asyncio.gather(*fetch_member_tasks)
    townhall_levels = [member.town_hall.level for member in ingame_members]
    townhall_levels.sort(reverse=True)
    average_townhall = round(sum(townhall_levels)/len(townhall_levels),2)
    townhall_counts = Counter(townhall_levels)

    embed.add_field(
        name="**In-Game Members**",
        value=f"Total: {len(ingame_members)} {EmojisUI.MEMBERS}\n"
            + f"Average: {EmojisTownHall.get(int(average_townhall))} {average_townhall}\n\n"
            + "\n".join([
                f"{EmojisTownHall.get(th)} `TH{th:02}`: {(count/len(ingame_members))*100:.1f}% ({count})"
                for th, count in townhall_counts.items()
                ])
            + "\n\u200b",
        inline=False,
        )
    return embed

async def clan_strength_embed(context:Union[commands.Context,discord.Interaction],clan:aClan):
    if clan.is_alliance_clan and clan.alliance_member_count > 0:
        showing_registered = True
        clan_members = clan.alliance_members
    else:
        showing_registered = False
        clan_members = await asyncio.gather(*[aPlayer.create(member.tag) for member in clan.members])
    
    townhall_levels = list(set([member.town_hall.level for member in clan_members]))
    townhall_levels.sort(reverse=True)
    average_th = round(sum([member.town_hall.level for member in clan_members])/len([member.town_hall.level for member in clan_members]),2)

    embed = await clash_embed(
        context=context,
        title=f"{clan.title}",
        message=f"**Clan Offensive Strength**\n"
            + f"**Average TH: {EmojisTownHall.get(round(average_th))} {average_th}**\n\n"
            + (f"*Showing registered members only.*\n" if showing_registered else "*Showing in-game members only.*\n")
            + (f"The {EmojisUI.LOGOUT} emoji denotes a registered member who is currently not in the clan.\n" if clan.is_alliance_clan and clan.alliance_member_count > 0 else "")
            + f"\n`{'BK':^2}{'':^2}{'AQ':^2}{'':^2}{'GW':^2}{'':^2}{'RC':^2}{'':^2}{'Troops':>7}{'':^2}{'Spells':>7}{'':^2}`",
        thumbnail=clan.badge,
        )

    async for th in AsyncIter(townhall_levels):
        th_members = [member for member in clan_members if member.town_hall.level == th]
        th_members.sort(key=lambda member:(member.hero_strength,member.troop_strength,member.spell_strength),reverse=True)
        chunked_members = list(chunks(th_members,10))

        for i, members_chunk in enumerate(chunked_members):
            embed.add_field(
                name=f"{EmojisTownHall.get(th)} **TH{th}**"
                    + (f" - ({i+1}/{len(chunked_members)})" if len(chunked_members) > 1 else ""),
                value="\n".join([
                    f"`{getattr(member.get_hero('Barbarian King'),'level',''):^2}{'':^2}"
                    + f"{getattr(member.get_hero('Archer Queen'),'level',''):^2}{'':^2}"
                    + f"{getattr(member.get_hero('Grand Warden'),'level',''):^2}{'':^2}"
                    + f"{getattr(member.get_hero('Royal Champion'),'level',''):^2}{'':^2}"
                    + f"{str(round((member.troop_strength / member.max_troop_strength)*100))+'%':>7}{'':^2}"
                    + (f"{str(round((member.spell_strength / member.max_spell_strength)*100))+'%':>7}" if member.max_spell_strength > 0 else f"{'':>7}")
                    + f"{'':^2}`\u3000{re.sub('[_*/]','',member.name)}"
                    + (f" {EmojisUI.LOGOUT}" if clan.is_alliance_clan and member.tag not in clan.members_dict else "")
                    for member in members_chunk
                    ]),
                inline=False,
                )
    return embed

async def clan_donations_embed(context:Union[commands.Context,discord.Interaction],clan:aClan):
    if clan.is_alliance_clan and clan.alliance_member_count > 0:
        clan_members = clan.alliance_members
        clan_members.sort(key=lambda member: member.current_season.donations_sent.alliance_only,reverse=True)

        stats_text = "\n".join([
            f"`{member.current_season.donations_sent.alliance_only:>6}{'':^2}"
            + f"{member.current_season.donations_rcvd.alliance_only:>6}{'':^2}`"
            + f"\u3000{EmojisTownHall.get(member.town_hall.level)} {re.sub('[_*/]','',member.name)}"
            for member in clan_members])

        embed = await clash_embed(
            context=context,
            title=f"{clan.title}: Donations",
            message=f"**Showing stats for: {clan.client.cog.current_season.description}**\n\n"
                + f"{EmojisClash.DONATIONSOUT} Total Sent: {sum(member.current_season.donations_sent.season_only_clan for member in clan_members):,}\u3000|\u3000"
                + f"{EmojisClash.DONATIONSRCVD} Total Received: {sum(member.current_season.donations_rcvd.season_only_clan for member in clan_members):,}\n\n"
                + f"`{'SENT':>6}{'':^2}{'RCVD':>6}{'':^2}`\n"
                + stats_text,
            thumbnail=clan.badge,
            )    
    else:
        clan_members = await asyncio.gather(*[aPlayer.create(member.tag) for member in clan.members])
        clan_members.sort(key=lambda member: member.donations,reverse=True)

        stats_text = "\n".join([
            f"`{member.donations:>6}{'':^2}"
            + f"{member.received:>6}{'':^2}`"
            + f"\u3000{EmojisTownHall.get(member.town_hall.level)} {re.sub('[_*/]','',member.name)}"
            for member in clan_members])

        embed = await clash_embed(
            context=context,
            title=f"{clan.title}: Donations",
            message=f"{EmojisClash.DONATIONSOUT} Total Sent: {sum(member.donations for member in clan_members):,}\u3000|\u3000"
                + f"{EmojisClash.DONATIONSRCVD} Total Received: {sum(member.received for member in clan_members):,}\n\n"
                + f"`{'SENT':>6}{'':^2}{'RCVD':>6}{'':^2}`\n"
                + stats_text,
            thumbnail=clan.badge,
            )
    return embed