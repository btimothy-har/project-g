import os
import pendulum
import xlsxwriter

from typing import *

from redbot.core.utils import AsyncIter

from coc_main.client.global_client import GlobalClient
from coc_main.coc_objects.season.season import aClashSeason

from coc_main.utils.constants.coc_constants import CWLLeagueGroups

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
    report_file = GlobalClient.bot.coc_report_path + '/' + f'{season.description} CWL Roster.xlsx'

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
    
    all_signups = await GlobalClient.coc_client.get_league_players(season=season,registered=True)
    
    a_iter = AsyncIter(all_signups)
    async for league_player in a_iter:
        player = await GlobalClient.coc_client.get_player(league_player.tag)

        if league_player.roster_clan_tag:
            roster_clan = await GlobalClient.coc_client.get_league_clan(league_player.roster_clan_tag,season=season)
        else:
            roster_clan = None

        col = 0
        row += 1
        m_data = []
        m_data.append(player.tag)
        m_data.append(player.name)
        m_data.append(f"{player.home_clan.name} ({player.home_clan.tag})" if player.home_clan else "")
        m_data.append(getattr(GlobalClient.bot.get_user(league_player.discord_user),'display_name',' ') if league_player.discord_user else " ")
        m_data.append(str(league_player.discord_user) if league_player.discord_user else " ")
        m_data.append(player.town_hall.level)

        m_data.append(player.hero_strength)
        m_data.append(f"{round(player.hero_strength_pct)}%")

        m_data.append(player.troop_strength)
        m_data.append(f"{round(player.troop_strength_pct)}%")

        m_data.append(player.spell_strength)
        m_data.append(f"{round(player.spell_strength_pct)}%")
        
        m_data.append(CWLLeagueGroups.get_description_no_emoji(league_player.league_group))
        m_data.append(f"{roster_clan.name} ({roster_clan.tag})" if roster_clan else "")
        m_data.append('Yes' if not getattr(roster_clan,'roster_open',True) else '')

        for d in m_data:
            master.write(row,col,d)
            col += 1
    
    league_clans = await GlobalClient.coc_client.get_league_clans(season=season,participating=True)
    a_iter = AsyncIter(league_clans)
    async for league_clan in a_iter:        
        clan_ws = workbook.add_worksheet(league_clan.name)

        row = 0
        col = 0
        for header in cwl_roster_headers:
            clan_ws.write(row,col,header,bold)
            col += 1

        participant_a_iter = AsyncIter(league_clan.participants)
        async for league_player in participant_a_iter:
            player = await GlobalClient.coc_client.get_player(league_player.tag)

            col = 0
            row += 1
            m_data = []
            m_data.append(player.tag)
            m_data.append(player.name)
            m_data.append(f"{player.home_clan.name} ({player.home_clan.tag})" if player.home_clan else "")
            m_data.append(getattr(GlobalClient.bot.get_user(player.discord_user),'display_name',' ') if player.discord_user else " ")
            m_data.append(str(player.discord_user) if player.discord_user else " ")
            m_data.append(player.town_hall.level)
            
            m_data.append(player.hero_strength)
            m_data.append(f"{round(player.hero_strength_pct)}%")

            m_data.append(player.troop_strength)
            m_data.append(f"{round(player.troop_strength_pct)}%")

            m_data.append(player.spell_strength)
            m_data.append(f"{round(player.spell_strength_pct)}%")

            m_data.append(CWLLeagueGroups.get_description_no_emoji(league_player.league_group))
            m_data.append(f"{league_clan.name} ({league_clan.tag})")
            m_data.append('Yes' if not getattr(league_clan,'roster_open',True) else '')

            for d in m_data:
                clan_ws.write(row,col,d)
                col += 1
    
    workbook.close()
    return report_file