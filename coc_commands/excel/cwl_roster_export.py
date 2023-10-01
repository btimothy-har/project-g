import os
import pendulum
import xlsxwriter

from redbot.core.utils import AsyncIter

from coc_client.api_client import BotClashClient

from coc_data.objects.clans.clan import aClan
from coc_data.objects.season.season import aClashSeason
from coc_data.objects.discord.member import aMember
from coc_data.objects.events.clan_war import aClanWar
from coc_data.objects.events.clan_war_leagues import WarLeagueClan, WarLeaguePlayer

from coc_data.constants.coc_constants import *

cwl_roster_headers = [
    'Tag',
    'Name',
    'Home Clan',
    'Discord User',
    'Discord ID',
    'Townhall',
    'Hero Strength',
    'Hero Completion',
    'Troop Strength',
    'Troop Completion',
    'Spell Strength',
    'Spell Completion',
    'CWL Group',
    'CWL Roster Clan',
    'Roster Finalized?'
    ]

async def generate_cwl_roster_export(season:aClashSeason):
    client = BotClashClient()
    
    report_file = client.bot.coc_report_path + '/' + f'{season.description} CWL Roster.xlsx'

    if pendulum.now() > season.cwl_end:
        if os.path.exists(report_file):
            return report_file
        else:
            return None
    
    if os.path.exists(report_file):
        os.remove(report_file)

    workbook = xlsxwriter.Workbook(report_file)
    
    bold = workbook.add_format({'bold':True})
    master = workbook.add_worksheet("Master")

    row = 0
    col = 0
    for header in cwl_roster_headers:
        master.write(row,col,header,bold)
        col += 1
    
    all_signups = WarLeaguePlayer.signups_by_season(season=season)
    async for m in AsyncIter(all_signups):
        col = 0
        row += 1
        m_data = []
        m_data.append(m.tag)
        m_data.append(m.name)
        m_data.append(f"{m.player.home_clan.name} ({m.player.home_clan.tag})" if m.player.home_clan else "")
        m_data.append(getattr(client.bot.get_user(m.discord_user),'display_name',' ') if m.discord_user else " ")
        m_data.append(str(m.discord_user) if m.discord_user else " ")
        m_data.append(m.town_hall)
        m_data.append(m.player.hero_strength)
        try:
            m_data.append(f"{round((m.player.hero_strength/m.player.max_hero_strength)*100,0)}%")
        except ZeroDivisionError:
            m_data.append("0%")
        m_data.append(m.player.troop_strength)
        try:
            m_data.append(f"{round((m.player.troop_strength/m.player.max_troop_strength)*100,0)}%")
        except ZeroDivisionError:
            m_data.append("0%")
        m_data.append(m.player.spell_strength)
        try:
            m_data.append(f"{round((m.player.spell_strength/m.player.max_spell_strength)*100,0)}%")
        except ZeroDivisionError:
            m_data.append("0%")
        m_data.append(CWLLeagueGroups.get_description_no_emoji(m.league_group))
        m_data.append(f"{m.roster_clan.name} {m.roster_clan.tag}" if m.roster_clan else "")
        m_data.append('Yes' if not getattr(m.roster_clan,'roster_open',True) else '')

        for d in m_data:
            master.write(row,col,d)
            col += 1
    
    participating_clans = WarLeagueClan.participating_by_season(season=season)    
    async for cwl_clan in AsyncIter(participating_clans):
        clan_ws = workbook.add_worksheet(cwl_clan.name)

        row = 0
        col = 0
        for header in cwl_roster_headers:
            clan_ws.write(row,col,header,bold)
            col += 1

        clan_roster = [s for s in all_signups if s.is_registered and s.roster_clan and s.roster_clan.tag == cwl_clan.tag]
        async for m in AsyncIter(clan_roster):
            col = 0
            row += 1
            m_data = []
            m_data.append(m.tag)
            m_data.append(m.name)
            m_data.append(f"{m.player.home_clan.name} ({m.player.home_clan.tag})" if m.player.home_clan else "")
            m_data.append(getattr(client.bot.get_user(m.discord_user),'display_name',' ') if m.discord_user else " ")
            m_data.append(str(m.discord_user) if m.discord_user else " ")
            m_data.append(m.town_hall)
            m_data.append(m.player.hero_strength)
            try:
                m_data.append(f"{round((m.player.hero_strength/m.player.max_hero_strength)*100,0)}%")
            except ZeroDivisionError:
                m_data.append("0%")
            m_data.append(m.player.troop_strength)
            try:
                m_data.append(f"{round((m.player.troop_strength/m.player.max_troop_strength)*100,0)}%")
            except ZeroDivisionError:
                m_data.append("0%")
            m_data.append(m.player.spell_strength)
            try:
                m_data.append(f"{round((m.player.spell_strength/m.player.max_spell_strength)*100,0)}%")
            except ZeroDivisionError:
                m_data.append("0%")
            m_data.append(CWLLeagueGroups.get_description_no_emoji(m.league_group))
            m_data.append(f"{m.roster_clan.name} {m.roster_clan.tag}" if m.roster_clan else "")
            m_data.append('Yes' if not getattr(m.roster_clan,'roster_open',True) else '')

            for d in m_data:
                clan_ws.write(row,col,d)
                col += 1
    
    workbook.close()
    return report_file