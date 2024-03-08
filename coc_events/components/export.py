import os
import pendulum
import xlsxwriter

from typing import *

from redbot.core.utils import AsyncIter
from coc_main.client.global_client import GlobalClient

from .event import Event, Participant

participant_headers = [
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
    ]

async def generate_event_export(event:Event) -> str:
    report_file = GlobalClient.bot.coc_report_path + '/' + f'Participants - {event.name}.xlsx'
    
    if os.path.exists(report_file):
        os.remove(report_file)

    workbook = xlsxwriter.Workbook(report_file)
    
    bold = workbook.add_format({'bold':True})
    master = workbook.add_worksheet("Master")

    row = 0
    col = 0
    for header in participant_headers:
        master.write(row,col,header,bold)
        col += 1
    
    participants = await event.get_all_participants()
    participants.sort(key=lambda p: p.town_hall_level,reverse=True)
    
    a_iter = AsyncIter(participants)
    async for player in a_iter:

        col = 0
        row += 1
        m_data = []
        m_data.append(player.tag)
        m_data.append(player.name)
        m_data.append(f"{player.home_clan.name} ({player.home_clan.tag})" if player.home_clan else "")
        m_data.append(getattr(GlobalClient.bot.get_user(player.participant_id),'display_name',' ') if player.participant_id else " ")
        m_data.append(str(player.participant_id) if player.participant_id else " ")
        m_data.append(player.town_hall.level)

        m_data.append(player.hero_strength)
        m_data.append(f"{round(player.hero_strength_pct)}%")

        m_data.append(player.troop_strength)
        m_data.append(f"{round(player.troop_strength_pct)}%")

        m_data.append(player.spell_strength)
        m_data.append(f"{round(player.spell_strength_pct)}%")

        for d in m_data:
            master.write(row,col,d)
            col += 1

    workbook.close()
    return report_file