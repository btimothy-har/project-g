import discord

from typing import *
from redbot.core import commands 

from ...api_client import BotClashClient as client

from .clan_war import aClanWar
from .clan_war_leagues import WarLeagueGroup
from .war_summary import aClanWarSummary

from ...utils.components import clash_embed
from ...utils.constants.coc_constants import WarState
from ...utils.constants.coc_emojis import EmojisClash, EmojisLeagues, EmojisTownHall
from ...utils.constants.ui_emojis import EmojisUI

bot_client = client()

async def clan_war_embed(
    context:Union[commands.Context,discord.Interaction],
    clan_war:aClanWar):
        
    if clan_war.league_group_id:
        league_group = await WarLeagueGroup(group_id=clan_war.league_group_id)
    
    embed = await clash_embed(
        context=context,
        title=f"\u200E{clan_war.emoji} {clan_war.clan_1.clean_name}\u3000vs\u3000{clan_war.clan_2.clean_name}",
        message=(f"{EmojisLeagues.get(league_group.league)} {league_group.league} (Round {league_group.get_round_from_war(clan_war)})" if clan_war.league_group_id else "")
            + f"\n**War State: {WarState.readable_text(clan_war.state)} ({clan_war.team_size} vs {clan_war.team_size})**"
            + (f"\nWar Starts: <t:{clan_war.start_time.int_timestamp}:R>" if clan_war.state == WarState.PREPARATION else "")
            + (f"\nWar Ends: <t:{clan_war.end_time.int_timestamp}:R>" if clan_war.state == WarState.INWAR else "")
            + (f"\nWar Ended: <t:{clan_war.end_time.int_timestamp}:R>" if clan_war.state == WarState.WAR_ENDED else "")
            + "\n"
            + f"\n\u200E`{clan_war.clan_1.clean_name[:15]:^15}`{EmojisUI.SPACER}`{clan_war.clan_2.clean_name[:15]:^15}`"
            + f"\n\u200E`{clan_war.clan_1.tag[:15]:^15}`{EmojisUI.SPACER}`{clan_war.clan_2.tag[:15]:^15}`"
            + f"\n\u200E`{str(clan_war.clan_1.attacks_used)+' / '+str(clan_war.attacks_per_member * clan_war.team_size):^15}`{EmojisClash.ATTACK}`{str(clan_war.clan_2.attacks_used)+' / '+str(clan_war.attacks_per_member * clan_war.team_size):^15}`"
            + f"\n\u200E`{str(clan_war.clan_1.stars):^15}`{EmojisClash.STAR}`{str(clan_war.clan_2.stars):^15}`"
            + f"\n\u200E`{str(round(clan_war.clan_1.destruction,2))+'%':^15}`{EmojisClash.DESTRUCTION}`{str(round(clan_war.clan_2.destruction,2))+'%':^15}`"
        )
    embed.add_field(
        name="**War Lineup**",
        value=f"\u200E{clan_war.clan_1.clean_name} (Average: {clan_war.clan_1.average_townhall})"
            + f"\n"
            + '\u3000'.join(f"{EmojisTownHall.get(th)}`{ct:>2}`" for th,ct in clan_war.clan_1.lineup.items())
            + f"\n"
            + f"\u200E{clan_war.clan_2.clean_name} (Average: {clan_war.clan_2.average_townhall})"
            + f"\n"
            + '\u3000'.join(f"{EmojisTownHall.get(th)}`{ct:>2}`" for th,ct in clan_war.clan_2.lineup.items())
            + f"\n\u200b",
        inline=False
        )
    for clan in [clan_war.clan_1,clan_war.clan_2]:
        stats = aClanWarSummary.for_clan(clan_tag=clan.tag,war_log=[clan_war])
        embed.add_field(
            name=f"\u200E__**Stats: {clan.clean_name}**__",
            value=f"**Hit Rates**"
                + f"\n3-Stars: " + (f"{len([a for a in clan.attacks if a.stars == 3])} ({len([a for a in clan.attacks if a.stars == 3]) / clan.attacks_used * 100:.0f}%)" if clan.attacks_used > 0 else "0 (0%)")
                + f"\n2-Stars: " + (f"{len([a for a in clan.attacks if a.stars == 2])} ({len([a for a in clan.attacks if a.stars == 2]) / clan.attacks_used * 100:.0f}%)" if clan.attacks_used > 0 else "0 (0%)")
                + f"\n1-Stars: " + (f"{len([a for a in clan.attacks if a.stars == 1])} ({len([a for a in clan.attacks if a.stars == 1]) / clan.attacks_used * 100:.0f}%)" if clan.attacks_used > 0 else "0 (0%)")
                + f"\n\n**Averages**"
                + f"\nStars: " + (f"{round(stats.offense_stars / stats.attack_count,2)}" if stats.attack_count > 0 else "0") + f"\nNew Stars: {stats.average_new_stars}"
                + f"\nDuration: {stats.average_duration_str}"
                + f"\n\n**Unused Hits: {clan.unused_attacks}**"
                + ('\n' + ''.join(f"{EmojisTownHall.get(th)}`{ct:>2}`"+("\n" if i%3==0 else "") for i,(th,ct) in enumerate(clan.available_hits_by_townhall.items(),start=1)) if clan.unused_attacks > 0 else "")
                + "\n\u200b",
            inline=True
            )
    return embed