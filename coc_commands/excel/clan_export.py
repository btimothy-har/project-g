import os
import xlsxwriter

from redbot.core.utils import AsyncIter

from coc_main.api_client import BotClashClient, aClashSeason
from coc_main.cog_coc_client import ClashOfClansClient, aClan, aClanWar, aRaidWeekend
from coc_main.coc_objects.events.war_summary import aClanWarSummary
from coc_main.coc_objects.events.raid_summary import aSummaryRaidStats

members_headers = [
    'Tag',
    'Name',
    'Linked To',
    'Home Clan',
    'Days in Home Clan',
    'Townhall',    
    'Attack Wins',
    'Defense Wins',
    'Donations Sent',
    'Donations Received',
    'Gold Looted',
    'Elixir Looted',
    'Dark Elixir Looted',
    'Capital Contribution',
    'Clan Games Points',
    'Clan Games Timer (Minutes)',
    'Wars Participated',
    'Total Attacks',
    'Missed Attacks',
    'Triples',
    'Offense Stars',
    'Offense Destruction',
    'Defense Stars',
    'Defense Destruction',
    'Raids Participated',
    'Raid Attacks',
    'Capital Gold Looted',
    'Raid Medals Earned',
    ]

clan_war_headers = [
    'Clan',
    'Tag',
    'Name',
    'Map Position',
    'Townhall',
    'Defense Count',
    'Order',
    'Defender',
    'Defender TH',
    'Stars',
    'New Stars',
    'Destruction',
    'New Destruction'
    ]

raid_headers = [
    'Tag',
    'Name',
    'Attack Count',
    'Capital Gold Looted',
    'Raid Medals',
    'District Name',
    'Raid Clan',
    'Stars',
    'Destruction',
    ]

bot_client = BotClashClient()

class ClanExcelExport():
    def __init__(self,clan:aClan,season:aClashSeason):
        self.clan = clan
        self.season = season
        self.file_path = bot_client.bot.coc_report_path + '/' + f"{clan.name} {season.description}.xlsx"
        self.workbook = None
    
    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    @classmethod
    async def generate_report(cls,clan:aClan,season:aClashSeason):
        export = cls(clan,season)

        if os.path.exists(export.file_path):
            os.remove(export.file_path)
        
        export.workbook = xlsxwriter.Workbook(export.file_path)
        await export.member_report()
        await export.war_report()
        await export.raids_report()
        export.workbook.close()
        return export.file_path
    
    async def member_report(self):
        bold = self.workbook.add_format({'bold': True})        
        members_worksheet = self.workbook.add_worksheet("Members")
        row = 0
        col = 0
        async for header in AsyncIter(members_headers):
            members_worksheet.write(row,col,header,bold)
            col += 1
        
        members = await bot_client.coc.get_members_by_season(self.clan,self.season)
        async for m in AsyncIter(members):
            col = 0
            row += 1

            stats = await m.get_season_stats(self.season)

            war_log = await aClanWar.for_player(m.tag,season=self.season)
            war_stats = aClanWarSummary.for_player(m.tag,war_log)

            raid_log = await aRaidWeekend.for_player(m.tag,season=self.season)
            raid_stats = aSummaryRaidStats.for_player(m.tag,raid_log)

            m_data = []
            m_data.append(stats.tag)
            m_data.append(stats.name)

            m_data.append(getattr(bot_client.bot.get_user(m.discord_user),'name',''))

            m_data.append(f"{getattr(stats.home_clan,'name','')} ({stats.home_clan_tag})")
            m_data.append(stats.time_in_home_clan / (24*60*60))
            m_data.append(stats.town_hall)        

            m_data.append(str(stats.attacks))
            m_data.append(str(stats.defenses))

            m_data.append(str(stats.donations_sent))
            m_data.append(str(stats.donations_rcvd))

            m_data.append(str(stats.loot_gold))
            m_data.append(str(stats.loot_elixir))
            m_data.append(str(stats.loot_darkelixir))
            m_data.append(str(stats.capitalcontribution))

            m_data.append(stats.clangames.score)
            m_data.append(stats.clangames.completion.in_minutes() if stats.clangames.completion else '')

            m_data.append(war_stats.wars_participated)
            m_data.append(war_stats.attack_count)
            m_data.append(war_stats.unused_attacks)

            m_data.append(war_stats.triples)
            m_data.append(war_stats.offense_stars)
            m_data.append(war_stats.offense_destruction)

            m_data.append(war_stats.defense_stars)
            m_data.append(war_stats.defense_destruction)

            m_data.append(raid_stats.raids_participated)

            m_data.append(raid_stats.raid_attacks)
            m_data.append(raid_stats.resources_looted)
            m_data.append(raid_stats.medals_earned)

            async for d in AsyncIter(m_data):
                members_worksheet.write(row,col,d)
                col += 1
    
    async def war_report(self):
        bold = self.workbook.add_format({'bold': True})
        
        clan_wars = await aClanWar.for_clan(clan_tag=self.clan.tag,season=self.season)
        async for war in AsyncIter(clan_wars):
            war_clan = war.get_clan(self.clan.tag)
            war_opponent = war.get_opponent(self.clan.tag)

            war_worksheet = self.workbook.add_worksheet(f'Clan War {war.preparation_start_time.format("DD MMM YYYY")}')

            #Row 1
            war_worksheet.write(0,0,'Clan',bold)
            war_worksheet.write(0,1,f"{war_clan.name} ({war_clan.tag})")
            war_worksheet.write(0,2,war_clan.stars)
            war_worksheet.write(0,3,f'{war_clan.destruction}%')
            #Row 2
            war_worksheet.write(1,0,'Opponent',bold)
            war_worksheet.write(1,1,f"{war_opponent.name} ({war_opponent.tag})")
            war_worksheet.write(1,2,war_opponent.stars)
            war_worksheet.write(1,3,f'{war_opponent.destruction}%')
            #Row 3
            war_worksheet.write(2,0,'War Type',bold)
            war_worksheet.write(2,1,war.type)
            #Row 4
            war_worksheet.write(3,0,'War Size',bold)
            war_worksheet.write(3,1,war.team_size)
            #Row 5
            war_worksheet.write(4,0,'Attacks per Member',bold)
            war_worksheet.write(4,1,war.attacks_per_member)
            #Row 6
            war_worksheet.write(5,0,'Preparation Start',bold)
            war_worksheet.write(5,1,war.preparation_start_time.format('DD MMM YYYY HH:mm:ss'))        
            #Row 7
            war_worksheet.write(6,0,'Start Time',bold)
            war_worksheet.write(6,1,war.start_time.format('DD MMM YYYY HH:mm:ss'))
            #Row 8
            war_worksheet.write(7,0,'End Time',bold)
            war_worksheet.write(7,1,war.end_time.format('DD MMM YYYY HH:mm:ss'))

            row = 9
            col = 0
            async for header in AsyncIter(clan_war_headers):
                war_worksheet.write(row,col,header,bold)
                col += 1
            
            async for w_clan in AsyncIter([war_clan,war_opponent]):
                async for member in AsyncIter(w_clan.members):
                    for i in range(0,war.attacks_per_member):
                        wm_data = []
                        wm_data.append(f"{w_clan.name} ({w_clan.tag})")
                        wm_data.append(member.tag)
                        wm_data.append(member.name)
                        wm_data.append(member.map_position)
                        wm_data.append(member.town_hall)
                        wm_data.append(member.defense_count)

                        try:
                            att = member.attacks[i]
                            wm_data.append(att.order)
                            wm_data.append(f"{att.defender.name} {att.defender_tag}")
                            wm_data.append(att.defender.town_hall)
                            wm_data.append(att.stars)
                            wm_data.append(att.new_stars)
                            wm_data.append(f"{att.destruction}%")
                            wm_data.append(f"{att.new_destruction}%")
                        except IndexError:
                            wm_data.append('')
                            wm_data.append('')
                            wm_data.append('')
                            wm_data.append('')
                            wm_data.append('')
                            wm_data.append('')
                            wm_data.append('')
                    
                        col = 0
                        row += 1
                        async for d in AsyncIter(wm_data):
                            war_worksheet.write(row,col,d)
                            col += 1

    async def raids_report(self):
        bold = self.workbook.add_format({'bold': True})
        
        raids = await aRaidWeekend.for_clan(clan_tag=self.clan.tag,season=self.season)
        async for raid in AsyncIter(raids):
            raid_worksheet = self.workbook.add_worksheet(f'Raid {raid.start_time.format("DD MMM YYYY")}')

            #Row 1
            raid_worksheet.write(0,0,'Raid Start',bold)
            raid_worksheet.write(0,1,raid.start_time.format('DD MMM YYYY'))

            #Row 2
            raid_worksheet.write(1,0,'Raid End',bold)
            raid_worksheet.write(1,1,raid.end_time.format('DD MMM YYYY'))

            #Row 3 Total Looy
            raid_worksheet.write(2,0,'Total Loot',bold)
            raid_worksheet.write(2,1,raid.total_loot)

            #Row 4 Total Medals
            raid_worksheet.write(3,0,'Max Medals',bold)
            raid_worksheet.write(3,1,(raid.offensive_reward * 6) + raid.defensive_reward)

            #Row 5 total participants
            raid_worksheet.write(4,0,'Total Participants',bold)
            raid_worksheet.write(4,1,len(raid.members))

            #row 6 total attacks
            raid_worksheet.write(5,0,'Total Attacks',bold)
            raid_worksheet.write(5,1,raid.attack_count)

            #row 7 offensive raids
            raid_worksheet.write(6,0,'Offensive Raids Completed',bold)
            raid_worksheet.write(6,1,raid.offense_raids_completed)

            #row 8 districts destroyed
            raid_worksheet.write(7,0,'Districts Destroyed',bold)
            raid_worksheet.write(7,1,raid.destroyed_district_count)

            #row 9 defensive raids
            raid_worksheet.write(8,0,'Defensive Raids Completed',bold)
            raid_worksheet.write(8,1,raid.defense_raids_completed)

            row = 10
            col = 0
            async for header in AsyncIter(raid_headers):
                raid_worksheet.write(row,col,header,bold)
                col += 1
            
            async for member in AsyncIter(raid.members):
                if len(member.attacks) == 0:
                    m_data = []
                    m_data.append(member.tag)
                    m_data.append(member.name)
                    m_data.append(member.attack_count)
                    m_data.append(member.capital_resources_looted)
                    m_data.append(member.medals_earned)
                    m_data.append('')
                    m_data.append('')
                    m_data.append('')
                    m_data.append('')

                    col = 0
                    row += 1
                    async for d in AsyncIter(m_data):
                        raid_worksheet.write(row,col,d)
                        col += 1
                
                else:
                    async for i in AsyncIter(range(0,len(member.attacks))):
                        m_data = []
                        m_data.append(member.tag)
                        m_data.append(member.name)
                        m_data.append(member.attack_count)
                        m_data.append(member.capital_resources_looted)
                        m_data.append(member.medals_earned)
                        m_data.append(member.attacks[i].district.name)
                        m_data.append(f'{member.attacks[i].district.clan.name} {member.attacks[i].district.clan.tag}')
                        m_data.append(member.attacks[i].stars)
                        m_data.append(member.attacks[i].destruction)

                        col = 0
                        row += 1
                        async for d in AsyncIter(m_data):
                            raid_worksheet.write(row,col,d)
                            col += 1