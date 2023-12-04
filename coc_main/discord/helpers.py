import discord

from typing import *
from redbot.core.utils import AsyncIter

from ..api_client import BotClashClient as client

from ..coc_objects.clans.clan import aClan
from ..coc_objects.players.player import aPlayer

from ..utils.constants.coc_emojis import EmojisClash, EmojisLeagues, EmojisCapitalHall
from ..utils.constants.ui_emojis import EmojisUI
from ..utils.components import clash_embed

bot_client = client()

async def guild_clan_panel_embed(clan:aClan,guild:Optional[discord.Guild]=None) -> discord.Embed:
    if guild:
        if guild.vanity_url:
            invite = await guild.vanity_invite()                        
        else:
            normal_invites = await guild.invites()
            if len(normal_invites) > 0:
                invite = normal_invites[0]
            else:
                invite = await guild.channels[0].create_invite()

    embed = await clash_embed(
        context=bot_client.bot,
        title=f"**{clan.title}**",
        message=f"{EmojisClash.CLAN} Level {clan.level}\u3000"
            + f"{EmojisUI.MEMBERS}" + (f" {clan.alliance_member_count}" if clan.is_alliance_clan else f" {clan.member_count}") + "\u3000"
            + f"{EmojisUI.GLOBE} {clan.location.name}\n"
            + (f"{EmojisClash.CLANWAR} W{clan.war_wins}/D{clan.war_ties}/L{clan.war_losses} (Streak: {clan.war_win_streak})\n" if clan.public_war_log else "")
            + f"{EmojisClash.WARLEAGUES}" + (f"{EmojisLeagues.get(clan.war_league.name)} {clan.war_league.name}\n" if clan.war_league else "Unranked\n")
            + f"{EmojisCapitalHall.get(clan.capital_hall)} CH {clan.capital_hall}\u3000"
            + f"{EmojisClash.CAPITALTROPHY} {clan.capital_points}\u3000"
            + (f"{EmojisLeagues.get(clan.capital_league.name)} {clan.capital_league}" if clan.capital_league else f"{EmojisLeagues.UNRANKED} Unranked") #+ "\n"
            + (f"\n\n**Join this Clan at: [{guild.name}]({str(invite)})**" if guild and invite else "")
            + f"\n\n{clan.description}"
            + f"\n\n**Recruiting**"
            + f"\nTownhalls: {clan.recruitment_level_emojis}"
            + (f"\n\n{clan.recruitment_info}" if len(clan.recruitment_info) > 0 else ""),
        thumbnail=clan.badge,
        show_author=False
        )
    return embed

async def guild_application_panel_embed(guild:discord.Guild,clans:List[aClan]) -> discord.Embed:

    if guild.id == 688449973553201335:
        embed = await clash_embed(
            context=bot_client.bot,
            title=f"**Welcome to the AriX Alliance!**",
            message=f"Our clans prioritize a social environment for members that are always ready to try new strategies and constantly improve themselves, "
                + f"to have good banter, win wars and get the support of a very active community. "
                + f"Our Clans try to mix the competitiveness of wars with a fun and enjoyable server to keep the game fun overall."
                + f"\n\nWe hope you'll enjoy your stay! <a:zzzpikachuhello:965872920725426176>"
                + f"\n\n**Server Link: https://discord.gg/arix **",
            thumbnail=str(guild.icon),
            show_author=False
            )
    else:
        embed = await clash_embed(
            context=bot_client.bot,
            title=f"**Apply to Join!**",
            message=f"Thinking of joining {guild.name}? Get started by picking one or more Clans to apply to."
                + f"\n\n**Tip:** For a smoother experience, link your Clash accounts with `$profile` before applying."
                + f"\n\u200b",
            thumbnail=str(guild.icon),
            show_author=False
            )
    async for c in AsyncIter(clans):
        embed.add_field(
            name=f"**{c.title}**",
            value=f"{c.summary_description}"
                + f"\nRecruiting: {c.recruitment_level_emojis}"
                + f"\n\u200b",
            inline=False
            )
    return embed

def account_recruiting_summary(account:aPlayer):
    text = ""
    text += f"### __**{account.name}**__"
    text += f"\n**[Open In-Game: {account.tag}]({account.share_link})**"
    text += f"\n\n<:Exp:825654249475932170> {account.exp_level}\u3000<:Clan:825654825509322752> {account.clan_description}"
    text += f"\n{account.town_hall.emote} {account.town_hall.description}\u3000{EmojisLeagues.get(account.league.name)} {account.trophies} (best: {account.best_trophies})"
    text += f"\n{account.hero_description}" if account.town_hall.level >= 7 else ""           
    text += f"\n\n{EmojisClash.BOOKFIGHTING} {account.troop_strength} / {account.max_troop_strength} *(rushed: {account.troop_rushed_pct}%)*\n"
    text += (f"{EmojisClash.BOOKSPELLS} {account.spell_strength} / {account.max_spell_strength} *(rushed: {account.spell_rushed_pct}%)*\n" if account.town_hall.level >= 5 else "")
    text += (f"{EmojisClash.BOOKHEROES} {account.hero_strength} / {account.max_hero_strength} *(rushed: {account.hero_rushed_pct}%)*\n" if account.town_hall.level >= 7 else "")
    return text

# async def account_recruiting_embed(account:aPlayer):
#     embed = await clash_embed(
#         context=BotClashClient().bot,
#         title=f"{account}",
#         message=f"{EmojisClash.EXP} {account.exp_level}\u3000{EmojisClash.CLAN} {account.clan_description}"
#             + (f"\n{account.discord_user_str}" if account.discord_user else "")
#             + f"\n\n{account.town_hall.emoji} {account.town_hall.description}\u3000{EmojisLeagues.get(getattr(account.league,'name',''))} {account.trophies} (best: {account.best_trophies})"
#             + f"\nWar Stars: {EmojisClash.STAR} {account.war_stars:,}"
#             + f"\nLeague Stars: {EmojisClash.WARLEAGUES} {getattr(account.get_achievement('War League Legend'),'value',0)}"
#             + f"\nCapital Gold Raided: {EmojisClash.CAPITALRAID} {numerize.numerize(getattr(account.get_achievement('Aggressive Capitalism'),'value',0),1)}"
#             + f"\n**[Player Link: {account.tag}]({account.share_link})**"
#             + f"\n\n"
#             + f"{EmojisClash.BOOKFIGHTING} {account.troop_strength} / {account.max_troop_strength} *(rushed: {account.troop_rushed_pct}%)*\n"
#             + (f"{EmojisClash.BOOKSPELLS} {account.spell_strength} / {account.max_spell_strength} *(rushed: {account.spell_rushed_pct}%)*\n" if account.town_hall.level >= 5 else "")
#             + (f"{EmojisClash.BOOKHEROES} {account.hero_strength} / {account.max_hero_strength} *(rushed: {account.hero_rushed_pct}%)*\n" if account.town_hall.level >= 7 else "")
#             + f"\n"
#             + f"An asterisk (*) below indicates rushed levels.",
#         show_author=False,
#         )
#     if len(account.heroes) > 0:
#         hero_list = []
#         for i, hero in enumerate(account.heroes):
#             hero_t = f"{hero.emoji}`{str(hero.level):>2}{'*' if hero.is_rushed else '':>1}/{str(hero.maxlevel_for_townhall):^3}` "
#             if i % 2 == 0:
#                 hero_list.append(hero_t)
#             else:
#                 hero_list[-1] += "\u200b" + hero_t
#         embed.add_field(
#             name=f"Heroes (rushed: {len([h for h in account.heroes if h.is_rushed])}/{len(account.heroes)})",
#             value="\n".join(hero_list)+"\n\u200b",
#             inline=False
#             )            
#     if len(account.pets) > 0:
#         pet_list = []
#         for i, pet in enumerate(account.pets):
#             pet_t = f"{pet.emoji}`{str(pet.level):>2}{'*' if pet.is_rushed else '':>1}/{str(pet.maxlevel_for_townhall):^3}` "
#             if i % 2 == 0:
#                 pet_list.append(pet_t)
#             else:
#                 pet_list[-1] += "\u200b" + pet_t
#         embed.add_field(
#             name=f"Hero Pets (rushed: {len([p for p in account.pets if p.is_rushed])}/{len(account.pets)})",
#             value="\n".join(pet_list)+"\n\u200b",
#             inline=False
#             )
#     if len(account.elixir_troops) > 0:
#         troop_list = []
#         for i, troop in enumerate(account.elixir_troops,start=1):
#             troop_t = f"{troop.emoji}`{str(troop.level):>2}{'*' if troop.is_rushed else '':>1}/{str(troop.maxlevel_for_townhall):^3}` "
#             if i % 3 == 1:
#                 troop_list.append(troop_t)
#             else:
#                 troop_list[-1] += "\u200b" + troop_t
#         embed.add_field(
#             name=f"Elixir Troops (rushed: {len([t for t in account.elixir_troops if t.is_rushed])}/{len(account.elixir_troops)})",
#             value="\n".join(troop_list)+"\n\u200b",
#             inline=False
#             )
#     if len(account.darkelixir_troops) > 0:
#         troop_list = []
#         for i, troop in enumerate(account.darkelixir_troops,start=1):
#             troop_t = f"{troop.emoji}`{str(troop.level):>2}{'*' if troop.is_rushed else '':>1}/{str(troop.maxlevel_for_townhall):^3}` "
#             if i % 3 == 1:
#                 troop_list.append(troop_t)
#             else:
#                 troop_list[-1] += "\u200b" + troop_t
#         embed.add_field(
#             name=f"Dark Elixir Troops (rushed: {len([t for t in account.darkelixir_troops if t.is_rushed])}/{len(account.darkelixir_troops)})",
#             value="\n".join(troop_list)+"\n\u200b",
#             inline=False
#             )
#     if len(account.siege_machines) > 0:
#         siege_list = []
#         for i, siege in enumerate(account.siege_machines,start=1):
#             siege_t = f"{siege.emoji}`{str(siege.level):>2}{'*' if siege.is_rushed else '':>1}/{str(siege.maxlevel_for_townhall):^3}` "
#             if i % 3 == 1:
#                 siege_list.append(siege_t)
#             else:
#                 siege_list[-1] += "\u200b" + siege_t
#         embed.add_field(
#             name=f"Siege Machines (rushed: {len([s for s in account.siege_machines if s.is_rushed])}/{len(account.siege_machines)})",
#             value="\n".join(siege_list)+"\n\u200b",
#             inline=False
#             )
#     if len(account.elixir_spells) > 0:
#         spell_list = []
#         for i, spell in enumerate(account.elixir_spells,start=1):
#             spell_t = f"{spell.emoji}`{str(spell.level):>2}{'*' if spell.is_rushed else '':>1}/{str(spell.maxlevel_for_townhall):^3}` "
#             if i % 3 == 1:
#                 spell_list.append(spell_t)
#             else:
#                 spell_list[-1] += "\u200b" + spell_t
#         embed.add_field(
#             name=f"Elixir Spells (rushed: {len([s for s in account.elixir_spells if s.is_rushed])}/{len(account.elixir_spells)})",
#             value="\n".join(spell_list)+"\n\u200b",
#             inline=False
#             )
#     if len(account.darkelixir_spells) > 0:
#         spell_list = []
#         for i, spell in enumerate(account.darkelixir_spells,start=1):
#             spell_t = f"{spell.emoji}`{str(spell.level):>2}{'*' if spell.is_rushed else '':>1}/{str(spell.maxlevel_for_townhall):^3}` "
#             if i % 3 == 1:
#                 spell_list.append(spell_t)
#             else:
#                 spell_list[-1] += "\u200b" + spell_t
#         embed.add_field(
#             name=f"Dark Elixir Spells (rushed: {len([s for s in account.darkelixir_spells if s.is_rushed])}/{len(account.darkelixir_spells)})",
#             value="\n".join(spell_list)+"\n\u200b",
#             inline=False
#             )
#     return embed