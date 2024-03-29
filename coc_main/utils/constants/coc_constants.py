import re

from typing import *
from itertools import chain

from .coc_emojis import *

class ClanRanks:
    MEMBER = 1
    ELDER = 2
    ADMIN = 2
    COLEADER = 3
    LEADER = 4

    @classmethod
    def get_number(cls,rank:str) -> int:
        s_rank = re.sub('[^a-zA-Z]','',rank)
        return int(getattr(cls,s_rank.upper(),0))

    @classmethod
    def get_rank(cls,from_number:int):
        rank_dict = {
            '1': 'Member',
            '2': 'Elder',
            '3': 'Co-Leader',
            '4': 'Leader'
            }
        return rank_dict.get(str(from_number),None)

class CWLLeagueGroups:
    league_groups = {
        0: f"{EmojisLeagues.UNRANKED} **Admin Group**",
        1: f"{EmojisLeagues.CHAMPION_LEAGUE_I} **Group A**: Champion League I",
        2: f"{EmojisLeagues.MASTER_LEAGUE_II} **Group B**: Master League I",
        9: f"{EmojisLeagues.CRYSTAL_LEAGUE_II} **Group C**: Crystal League I",
        99: f"{EmojisLeagues.UNRANKED} **Group D**: Lazy CWL",
        }
    league_groups_no_emoji = {
        0: f"Admin Group",
        1: f"Group A (Champion League I)",
        2: f"Group B (Master League I)",
        9: f"Group C (Crystal League I)",
        99: f"Group D (Lazy CWL)",
        }
    league_groups_emoji = {
        0: f"{EmojisLeagues.UNRANKED}",
        1: f"{EmojisLeagues.CHAMPION_LEAGUE_I}",
        2: f"{EmojisLeagues.MASTER_LEAGUE_I}",
        9: f"{EmojisLeagues.CRYSTAL_LEAGUE_I}",
        99: f"{EmojisLeagues.UNRANKED}",
        }
    eligibility = {
        1: [16,15],
        2: [16,15,14,13],
        9: [16,15,14,13,12,11,10]
        }
    from_league_name_dict = {
        'Champion League I': 1,
        'Champion League II': 1,
        'Champion League III': 1,
        'Master League I': 2,
        'Master League II': 2,
        'Master League III': 2,
        }
    @classmethod
    def get_description(cls,num:int) -> str:
        return cls.league_groups.get(num,None)
    @classmethod
    def get_description_no_emoji(cls,num:int) -> str:
        return cls.league_groups_no_emoji.get(num,None)
    @classmethod
    def from_league_name(cls,league:str) -> int:
        return cls.from_league_name_dict.get(league,9)

class MultiplayerLeagues:
    multiplayer_leagues = [
        'Unranked',
        'Bronze League III',
        'Bronze League II',
        'Bronze League I',
        'Silver League III',
        'Silver League II',
        'Silver League I',
        'Gold League III',
        'Gold League II',
        'Gold League I',
        'Crystal League III',
        'Crystal League II',
        'Crystal League I',
        'Master League III',
        'Master League II',
        'Master League I',
        'Champion League III',
        'Champion League II',
        'Champion League I',
        'Titan League III',
        'Titan League II',
        'Titan League I',
        'Legend League'
        ]
    @classmethod
    def get_index(cls,league:str) -> int:
        try:
            return cls.multiplayer_leagues.index(league)
        except:
            return 0

    
class HeroAvailability:
    unlock_info = {
        1: [],
        2: [],
        3: [],
        4: [],
        5: [],
        6: [],
        7: ['Barbarian King'],
        8: [],
        9: ['Archer Queen'],
        10: [],
        11: ['Grand Warden'],
        12: [],
        13: ['Royal Champion'],
        14: [],
        15: [],
        16: []
        }

    @classmethod
    def return_all_unlocked(cls,input_th:int):
        return list(chain.from_iterable([hero for (th,hero) in cls.unlock_info.items() if th <= input_th]))
    @classmethod
    def is_unlocked(cls,hero_name:str,input_th:int):
        return hero_name in cls.return_all_unlocked(input_th)
    @classmethod
    def unlocked_at(cls,hero_name:str):
        for (th,hero) in cls.unlock_info.items():
            if hero_name in hero:
                return int(th)

class TroopAvailability:
    unlock_info = {
        1: ['Barbarian','Archer','Giant'],
        2: ['Goblin'],
        3: ['Wall Breaker'],
        4: ['Balloon'],
        5: ['Wizard'],
        6: ['Healer'],
        7: ['Dragon','Minion','Hog Rider'],
        8: ['P.E.K.K.A','Valkyrie','Golem'],
        9: ['Baby Dragon','Witch','Lava Hound'],
        10: ['Miner','Bowler'],
        11: ['Electro Dragon','Ice Golem','Super Barbarian','Super Archer','Sneaky Goblin','Super Wall Breaker'],
        12: ['Yeti','Headhunter','Wall Wrecker','Battle Blimp','Stone Slammer','Super Giant','Rocket Balloon','Super Wizard','Super Dragon','Inferno Dragon','Super Minion','Super Valkyrie','Super Witch','Ice Hound','Super Bowler'],
        13: ['Dragon Rider','Apprentice Warden','Super Hog Rider','Super Miner','Siege Barracks','Log Launcher'],
        14: ['Electro Titan','Flame Flinger'],
        15: ['Battle Drill','Root Rider'],
        16: []
        }

    @classmethod
    def return_all_unlocked(cls,input_th:int):
        return list(chain.from_iterable([troop for (th,troop) in cls.unlock_info.items() if th <= input_th]))
    @classmethod
    def is_unlocked(cls,troop_name:str,input_th:int):
        return troop_name in cls.return_all_unlocked(input_th)
    @classmethod
    def unlocked_at(cls,troop_name:str):
        for (th,troops) in cls.unlock_info.items():
            if troop_name in troops:
                return int(th)

class SpellAvailability:
    unlock_info = {
        1: [],
        2: [],
        3: [],
        4: [],
        5: ['Lightning Spell'],
        6: ['Healing Spell'],
        7: ['Rage Spell'],
        8: ['Poison Spell', 'Earthquake Spell'],
        9: ['Jump Spell', 'Freeze Spell', 'Haste Spell', 'Skeleton Spell'],
        10: ['Clone Spell', 'Bat Spell'],
        11: ['Invisibility Spell'],
        12: ['Overgrowth Spell'],
        13: ['Recall Spell'],
        14: [],
        15: [],
        16: []
        }
    @classmethod
    def return_all_unlocked(cls,input_th:int):
        return list(chain.from_iterable([spell for (th,spell) in cls.unlock_info.items() if th <= input_th]))
    @classmethod
    def is_unlocked(cls,spell_name:str,input_th:int):
        return spell_name in cls.return_all_unlocked(input_th)
    @classmethod
    def unlocked_at(cls,spell_name:str):
        for (th,spells) in cls.unlock_info.items():
            if spell_name in spells:
                return int(th)

class PetAvailability:
    unlock_info = {
        1: [],
        2: [],
        3: [],
        4: [],
        5: [],
        6: [],
        7: [],
        8: [],
        9: [],
        10: [],
        11: [],
        12: [],
        13: [],
        14: ['L.A.S.S.I','Electro Owl','Mighty Yak','Unicorn'],
        15: ['Frosty','Diggy','Poison Lizard','Phoenix'],
        16: ['Spirit Fox']
        }
    @classmethod
    def return_all_unlocked(cls,input_th:int):
        #return [(th,pet) for th,pet in cls.unlock_info.items() if th <= input_th]
        return list(chain.from_iterable([pet for (th,pet) in cls.unlock_info.items() if th <= input_th]))
    @classmethod
    def is_unlocked(cls,pet_name:str,input_th:int):
        return pet_name in cls.return_all_unlocked(input_th)
    @classmethod
    def unlocked_at(cls,pet_name:str):
        for (th,pets) in cls.unlock_info.items():
            if pet_name in pets:
                return int(th)

class TroopCampSize:
    campsize_info = {
        "Barbarian": 1,
        "Archer": 1,
        "Giant": 5,
        "Goblin": 1,
        "Wall Breaker": 2,
        "Balloon": 5,
        "Wizard": 4,
        "Healer": 14,
        "Dragon": 20,
        "Minion": 2,
        "Hog Rider": 5,
        "P.E.K.K.A": 25,
        "Valkyrie": 8,
        "Golem": 30,
        "Baby Dragon": 10,
        "Witch": 12,
        "Lava Hound": 30,
        "Miner": 6,
        "Bowler": 6,
        "Electro Dragon": 30,
        "Ice Golem": 15,
        "Yeti": 18,
        "Headhunter": 6,
        "Dragon Rider": 25,
        "Electro Titan": 32,
        "Root Rider": 20,
        "Wall Wrecker": 1,
        "Battle Blimp": 1,
        "Stone Slammer": 1,
        "Siege Barracks": 1,
        "Log Launcher": 1,
        "Flame Flinger": 1,
        "Battle Drill": 1,
        "Lightning Spell": 1,
        "Healing Spell": 2,
        "Rage Spell": 2,
        "Poison Spell": 1,
        "Earthquake Spell": 1,
        "Jump Spell": 2,
        "Freeze Spell": 1,
        "Haste Spell": 1,
        "Skeleton Spell": 1,
        "Clone Spell": 3,
        "Bat Spell": 1,
        "Invisibility Spell": 1,
        "Recall Spell": 2,
        "Super Barbarian": 5,
        "Super Archer": 12,
        "Super Giant": 10,
        "Sneaky Goblin": 3,
        "Super Wall Breaker": 8,
        "Rocket Balloon": 8,
        "Super Wizard": 10,
        "Super Dragon": 40,
        "Inferno Dragon": 15,
        "Super Minion": 12,
        "Super Valkyrie": 20,
        "Super Witch": 40,
        "Ice Hound": 40,
        "Super Bowler": 30,
        "Super Miner": 24,
        }
    @classmethod
    def get(cls, name:str):
        return cls.campsize_info.get(name,0)

clan_castle_size = {
    1: [0,0,0],
    2: [10,0,0],
    3: [10,0,0],
    4: [15,0,0],
    5: [15,0,0],
    6: [20,0,0],
    7: [20,0,0],
    8: [25,1,0],
    9: [30,1,0],
    10: [35,1,1],
    11: [35,2,1],
    12: [40,2,1],
    13: [45,2,1],
    14: [45,3,1],
    15: [50,3,1],
    16: [50,3,1]
    }

activity_achievements = [
    'Conqueror', #attack wins
    'War Hero', #war stars
    'War League Legend', #war league stars
    'Most Valuable Clanmate', #clan cap contribution
    'Aggressive Capitalism', #clan cap loot
    'Friend in Need', #troop donations
    'Sharing is Caring', #spell donations
    'Siege Sharer', #siege donations
    'Games Champion', #clan games
    'Humiliator', #townhalls
    'Not So Easy This Time',
    'Union Buster',
    'Bust This!',
    'Wall Buster',
    'Mortar Mauler',
    'X-Bow Exterminator',
    'Firefighter',
    'Anti-Artillery',
    'Shattered and Scattered',
    'Counterspell',
    'Monolith Masher',
    'Un-Build It',
    'Nice and Tidy', #obstacles
    'Clan War Wealth', #clan castle gold
    'Gold Grab', #loot gold
    'Elixir Escapade', #loot elixir
    'Heroic Heist', #loot dark elixir
    'Superb Work', #boost troop
    ]

class WarState:
    NOTINWAR = 'notInWar'
    PREPARATION = 'preparation'
    INWAR = 'inWar'
    WAR_ENDED = 'warEnded'

    @classmethod
    def readable_text(cls,state:str):
        if state == cls.NOTINWAR:
            return 'Not in War'
        elif state == cls.PREPARATION:
            return 'Preparation'
        elif state == cls.INWAR:
            return 'In War'
        elif state == cls.WAR_ENDED:
            return 'War Ended'
        else:
            return 'Unknown'

class ClanWarType:
    RANDOM = 'random'
    FRIENDLY = 'friendly'
    CWL = 'cwl'

class WarResult:
    WINNING = 'winning'
    TIE = 'tie'
    LOSING = 'losing'
    WON = 'won'
    TIED = 'tied'
    LOST = 'lost'
    WINEMOJI = '<:Win:1223195290262306878>'
    TIEEMOJI = '<:Clan:825654825509322752>'
    LOSEEMOJI = '<:Lost:1223195313997873226>'

    _ongoing = {
        'winning':'winning',
        'tied':'tie',
        'losing':'losing',
        'won':'winning',
        'tie':'tie',
        'lost':'losing'
        }
    _ended = {
        'winning':'won',
        'tied':'tied',
        'losing':'lost',
        'won':'won',
        'tie':'tied',
        'lost':'lost'
        }
    _with_emoji = {
        'winning':'<:Win:1223195290262306878> Winning',
        'tied':'<:Clan:825654825509322752> Tied',
        'losing':'<:Lost:1223195313997873226> Losing',
        'won':'<:Win:1223195290262306878> Won',
        'tie':'<:Clan:825654825509322752> Tied',
        'lost':'<:Lost:1223195313997873226> Lost'
        }
    @classmethod
    def ongoing(cls,war_result:str,with_emoji:bool=False):
        if with_emoji:
            return cls._with_emoji.get(cls._ongoing.get(war_result.lower(),''),None)
        return cls._ongoing.get(war_result.lower(),'')
    @classmethod
    def ended(cls,war_result:str,with_emoji:bool=False):
        if with_emoji:
            return cls._with_emoji.get(cls._ended.get(war_result.lower(),''),None)
        return cls._ended.get(war_result.lower(),'')
    @classmethod
    def emoji(cls,war_result:str):
        return cls._with_emoji.get(war_result.lower(),'')