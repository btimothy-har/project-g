import pendulum

from typing import *

from ...utilities.utils import *

class aSummaryWarStats():
    def __init__(self,war_log):
        
        self.timestamp = pendulum.now()        
        self.war_log = war_log
        self.wars_participated = len(self.war_log) if self.war_log else 0

        self.attack_count = 0
        self.offense_stars = 0
        self.offense_destruction = 0
        self.defense_count = 0
        self.defense_stars = 0
        self.defense_destruction = 0
        self.triples = 0
        self.unused_attacks = 0
        self.average_new_stars = 0
        self.average_attack_duration = 0
        self.hit_rate = {}
    
    @classmethod
    def for_player(cls,player_tag:str,war_log):
        instance = cls(war_log)

        instance.player_tag = player_tag
        instance.clan_tag = None

        if instance.wars_participated > 0:
            instance.attack_count = sum(
                [len(war.get_member(instance.player_tag).attacks)
                for war in war_log]
                )
            instance.offense_stars = sum(
                [sum([attack.stars for attack in war.get_member(instance.player_tag).attacks])
                for war in war_log]
                )
            instance.offense_destruction = sum(
                [sum([attack.destruction for attack in war.get_member(instance.player_tag).attacks])
                for war in war_log]
                )
            instance.defense_count = sum(
                [war.get_member(instance.player_tag).defense_count
                for war in war_log]
                )
            instance.defense_stars = sum(
                [getattr(war.get_member(instance.player_tag).best_opponent_attack,'stars',0)
                for war in war_log]
                )
            instance.defense_destruction = sum(
                [getattr(war.get_member(instance.player_tag).best_opponent_attack,'destruction',0)
                for war in war_log]
                )
            instance.triples = sum(
                [len([attack for attack in war.get_member(instance.player_tag).attacks if attack.is_triple])
                for war in war_log]
                )
            instance.unused_attacks = sum(
                [war.get_member(instance.player_tag).unused_attacks
                for war in war_log]
                )
            
            total_duration = 0
            duration_count = 0
            total_new_star = 0
            new_star_count = 0

            for war in war_log:
                for a in war.get_member(instance.player_tag).attacks:
                    if a.duration <= 180: 
                        total_duration += a.duration
                        duration_count += 1
                    total_new_star += a.new_stars
                    new_star_count += 1
            
                    th = f"{a.attacker.town_hall}v{a.defender.town_hall}"
                    if th not in instance.hit_rate:
                        instance.hit_rate[th] = {
                            'attacker':a.attacker.town_hall,
                            'defender':a.defender.town_hall,
                            'total':0,
                            'stars':0,
                            'destruction':0,
                            'triples':0
                            }
                    instance.hit_rate[th]['total'] += 1
                    instance.hit_rate[th]['stars'] += a.stars
                    instance.hit_rate[th]['destruction'] += a.destruction
                    instance.hit_rate[th]['triples'] += 1 if a.is_triple else 0
            
            if duration_count > 0:
                instance.average_attack_duration = total_duration / duration_count
            if new_star_count > 0:
                instance.average_new_stars = total_new_star / new_star_count        
        return instance

    @classmethod
    def for_clan(cls,clan_tag:str,war_log):
        instance = cls(war_log)

        instance.player_tag = None
        instance.clan_tag = clan_tag

        if instance.wars_participated > 0:
            instance.attack_count = sum(
                [war.get_clan(instance.clan_tag).attacks_used for war in war_log]
                )
            instance.offense_stars = sum(
                [war.get_clan(instance.clan_tag).stars for war in war_log]
                )
            instance.offense_destruction = sum(
                [war.get_clan(instance.clan_tag).destruction for war in war_log]
                )
            instance.defense_count = sum(
                [len(war.get_clan(instance.clan_tag).defenses)
                for war in war_log]
                )
            instance.defense_stars = sum(
                [war.get_opponent(instance.clan_tag).stars for war in war_log]
                )
            instance.defense_destruction = sum(
                [war.get_opponent(instance.clan_tag).destruction for war in war_log]
                )
            instance.triples = sum(
                [len([attack for attack in war.get_clan(instance.clan_tag).attacks if attack.is_triple])
                for war in war_log]
                )
            instance.unused_attacks = sum(
                [((war.attacks_per_member * war.team_size) - war.get_clan(instance.clan_tag).attacks_used)
                for war in war_log]
                )
            
            total_duration = 0
            duration_count = 0
            total_new_star = 0
            new_star_count = 0
            
            for war in war_log:
                for a in war.get_clan(instance.clan_tag).attacks:
                    if a.duration <= 180:
                        total_duration += a.duration
                        duration_count += 1                    
                    total_new_star += a.new_stars
                    new_star_count += 1

                    th = f"{a.attacker.town_hall}v{a.defender.town_hall}"
                    if th not in instance.hit_rate:
                        instance.hit_rate[th] = {
                            'attacker':a.attacker.town_hall,
                            'defender':a.defender.town_hall,
                            'total':0,
                            'stars':0,
                            'destruction':0,
                            'triples':0
                            }
                    instance.hit_rate[th]['total'] += 1
                    instance.hit_rate[th]['stars'] += a.stars
                    instance.hit_rate[th]['destruction'] += a.destruction
                    instance.hit_rate[th]['triples'] += 1 if a.is_triple else 0

            if duration_count > 0:
                instance.average_attack_duration = total_duration / duration_count
            if new_star_count > 0:
                instance.average_new_stars = total_new_star / new_star_count

        return instance

    @property
    def average_duration_str(self):
        d,h,m,s = s_convert_seconds_to_str(self.average_attack_duration)
        ret_str = ""
        if d > 0:
            ret_str += f"{int(d)}d "
        if h > 0:
            ret_str += f"{int(h)}h "
        if m > 0:
            ret_str += f"{int(m)}m "
        if s > 0:
            ret_str += f"{int(s)}s "
        if ret_str == "":
            ret_str = "0s"
        return ret_str.strip()