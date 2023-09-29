import os
import urllib
import asyncio
import discord

import hashlib
import coc
import pendulum

from typing import *
from mongoengine import *

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from coc_client.api_client import BotClashClient

from ..clans.clan import aClan

from ..season.season import aClashSeason

from ...constants.coc_constants import *
from ...constants.coc_emojis import *
from ...exceptions import *

##################################################
#####
##### DATABASE
#####
##################################################
class db_RaidWeekend(Document):
    raid_id = StringField(primary_key=True,required=True)
    clan_tag = StringField(default="")
    clan_name = StringField(default="")
    clan_badge = StringField(default="")
    clan_level = IntField(default=0)
    starting_trophies = IntField(default=0)
    ending_trophies = IntField(default=0)
    is_alliance_raid = BooleanField(default=False)
    state = StringField(default="")
    start_time = IntField(default=0)
    end_time = IntField(default=0)
    total_loot = IntField(default=0)
    attack_count = IntField(default=0)
    destroyed_district_count = IntField(default=0)
    offensive_reward = IntField(default=0)
    defensive_reward = IntField(default=0)
    attack_log = ListField(DictField(),default=[])
    defense_log = ListField(DictField(),default=[])
    members = ListField(DictField(),default=[])
    last_save = IntField(default=0)

##################################################
#####
##### RAID WEEKEND
#####
##################################################
class aRaidWeekend():
    _cache = {}

    @classmethod
    def load_all(cls):
        query = db_RaidWeekend.objects().only('raid_id')
        ret_raids = [cls(raid_id=raid.raid_id) for raid in query]
        return sorted(ret_raids, key=lambda w:(w.start_time),reverse=True)

    @classmethod
    def for_player(cls,player_tag:str,season:aClashSeason):
        if season:
            query = db_RaidWeekend.objects(
                Q(members__tag=player_tag) &
                Q(start_time__gte=season.season_start.int_timestamp) &
                Q(start_time__lte=season.season_end.int_timestamp)
                ).only('raid_id')
        else:
            query = db_RaidWeekend.objects(
                Q(members__tag=player_tag)
                ).only('raid_id')
        
        ret_raids = [cls(raid_id=raid.raid_id) for raid in query]
        return sorted(ret_raids, key=lambda w:(w.start_time),reverse=True)

    @classmethod
    def for_clan(cls,clan_tag:str,season:aClashSeason):
        if season:
            query = db_RaidWeekend.objects(
                Q(clan_tag=clan_tag) &
                Q(start_time__gte=season.season_start.int_timestamp) &
                Q(start_time__lte=season.season_end.int_timestamp)
                ).only('raid_id')
        else:
            query = db_RaidWeekend.objects(
                Q(clan_tag=clan_tag)
                ).only('raid_id')
        
        ret_raids = [cls(raid_id=raid.raid_id) for raid in query]
        return sorted(ret_raids, key=lambda w:(w.start_time),reverse=True)

    def __new__(cls,raid_id:str):
        if raid_id not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[raid_id] = instance
        return cls._cache[raid_id]
    
    def __init__(self,raid_id:str):
        self.client = BotClashClient()
        self.raid_id = raid_id

        if self._is_new:
            self._found_in_db = False

            self.clan_tag = ""
            self.clan_name = ""
            self.clan_badge = ""
            self.clan_level = 0

            self.starting_trophies = 0
            self.ending_trophies = 0

            self.is_alliance_raid = False

            self.state = ""
            self.start_time = None
            self.end_time = None
            self.total_loot = 0
            self.attack_count = 0
            self.destroyed_district_count = 0

            self.offensive_reward = 0
            self.defensive_reward = 0

            self.attack_log = []
            self.defense_log = []
            
            self.members = []

            self._last_save = None

            try:
                raid_data = db_RaidWeekend.objects.get(raid_id=raid_id).to_mongo().to_dict()
            except DoesNotExist:
                pass
            else:
                self._found_in_db = True
                self.clan_tag = raid_data['clan_tag']
                self.clan_name = raid_data['clan_name']
                self.clan_badge = raid_data['clan_badge']
                self.clan_level = raid_data['clan_level']

                self.starting_trophies = raid_data['starting_trophies']
                self.ending_trophies = raid_data['ending_trophies']

                self.is_alliance_raid = raid_data['is_alliance_raid']

                self.state = raid_data['state']
                self.start_time = pendulum.from_timestamp(raid_data['start_time'])
                self.end_time = pendulum.from_timestamp(raid_data['end_time'])
                self.total_loot = raid_data['total_loot']
                self.attack_count = raid_data['attack_count']
                self.destroyed_district_count = raid_data['destroyed_district_count']

                self.offensive_reward = raid_data['offensive_reward']
                self.defensive_reward = raid_data['defensive_reward']

                self.attack_log = [aRaidClan(self,json=a) for a in raid_data['attack_log']]
                self.defense_log = [aRaidClan(self,json=a) for a in raid_data['defense_log']]
                
                self.members = [aRaidMember(self,json=m) for m in raid_data['members']]

                self._last_save = pendulum.from_timestamp(raid_data.get('last_save',0)) if raid_data.get('last_save',0) > 0 else None
    
    @classmethod
    async def create_from_api(cls,clan_tag:str,data:coc.RaidLogEntry):
        base_raid_id = clan_tag + str(pendulum.instance(data.start_time.time).int_timestamp)
        raid_id = hashlib.sha256(base_raid_id.encode()).hexdigest()

        raid_weekend = cls(raid_id=raid_id)

        clan = await aClan.create(clan_tag)
            
        raid_weekend.clan_tag = clan_tag
        raid_weekend.clan_name = clan.name
        raid_weekend.clan_badge = clan.badge
        raid_weekend.clan_level = clan.level

        raid_weekend.is_alliance_raid = clan.is_alliance_clan

        raid_weekend.state = data.state
        raid_weekend.start_time = pendulum.instance(data.start_time.time)
        raid_weekend.end_time = pendulum.instance(data.end_time.time)
        raid_weekend.total_loot = data.total_loot
        raid_weekend.attack_count = data.attack_count
        raid_weekend.destroyed_district_count = data.destroyed_district_count
        raid_weekend.offensive_reward = data.offensive_reward
        raid_weekend.defensive_reward = data.defensive_reward

        raid_weekend.attack_log = [aRaidClan(raid_weekend,data=attack) for attack in data.attack_log]
        raid_weekend.defense_log = [aRaidClan(raid_weekend,data=defe) for defe in data.defense_log]

        raid_weekend.members = [aRaidMember(raid_weekend,data=member) for member in data.members]

        if raid_weekend.do_i_save:
            raid_weekend.save_raid_to_db()
        
        return raid_weekend

    @property
    def do_i_save(self):
        if not self._found_in_db:
            return True
        if self.state == 'ongoing':
            if self._last_save is None:
                return True
            if self._last_save.diff().in_minutes() > 60:
                return True
        if self.end_time <= pendulum.now() <= self.end_time.add(hours=2):
            return True
        return False
    
    def save_raid_to_db(self):
        #self.bot.clash_state.data.add_to_cache(self)
        self._last_save = pendulum.now()
        db_raid = db_RaidWeekend(
            raid_id = self.raid_id,
            clan_tag = self.clan_tag,
            clan_name = self.clan_name,
            clan_badge = self.clan_badge,
            clan_level = self.clan_level,
            starting_trophies = self.starting_trophies,
            ending_trophies = self.ending_trophies,
            is_alliance_raid = self.is_alliance_raid,
            state = self.state,
            start_time = self.start_time.int_timestamp,
            end_time = self.end_time.int_timestamp,
            total_loot = self.total_loot,
            attack_count = self.attack_count,
            destroyed_district_count = self.destroyed_district_count,
            offensive_reward = self.offensive_reward,
            defensive_reward = self.defensive_reward,
            attack_log = [r.to_json() for r in self.attack_log],
            defense_log = [r.to_json() for r in self.defense_log],
            members = [m.to_json() for m in self.members],
            last_save = self._last_save.int_timestamp
            )
        db_raid.save()

    ##################################################
    ### DATA FORMATTERS
    ##################################################
    def __str__(self) -> str:
        return f"{self.clan_name} Capital Raid {self.start_time.format('DD MMM YYYY')}"
    
    def __eq__(self, __value: object) -> bool:
        return isinstance(__value, aRaidWeekend) and self.clan_tag == __value.clan_tag and self.start_time == __value.start_time
    
    def __hash__(self):
        return self.raid_id
    
    ##################################################
    ### DATA HELPERS
    ##################################################
    @property
    def offense_raids_completed(self):
        return len([a for a in self.attack_log if a.destroyed_district_count == a.district_count])
    
    @property
    def defense_raids_completed(self):
        return len([a for a in self.defense_log if a.destroyed_district_count == a.district_count])
    
    @property
    def clan(self):
        return self.client.cog.get_clan(self.clan_tag)
    
    def get_member(self,tag):
        find_member = [rm for rm in self.members if rm.tag == tag]
        if len(find_member) == 0:
            return None
        else:
            return find_member[0]
    
    ##################################################
    ### RAID IMAGE
    ##################################################
    async def get_results_image(self):
        base_path = str(Path(__file__).parent)
        font = base_path + '/ImgGen/SCmagic.ttf'
        background = Image.open(base_path + '/ImgGen/raidweek.png')
        arix_logo = Image.open(base_path + '/ImgGen/arix_logo_mid.PNG')

        clan_name = ImageFont.truetype(font, 30)
        total_medal_font = ImageFont.truetype(font, 60)
        trophy_font = ImageFont.truetype(font,45)
        boxes_font = ImageFont.truetype(font,30)
        split_medal_font = ImageFont.truetype(font, 25)

        draw = ImageDraw.Draw(background)
        stroke = 2

        if self.clan.abbreviation in ['AO9','PR','AS','PA','AX']:
            if self.clan.abbreviation == 'AO9':
                badge = Image.open(base_path + '/ImgGen/logo_ao9.png')
            elif self.clan.abbreviation == 'PR':
                badge = Image.open(base_path + '/ImgGen/logo_pr.png')
            elif self.clan.abbreviation == 'AS':
                badge = Image.open(base_path + '/ImgGen/logo_as.png')
            elif self.clan.abbreviation == 'PA':
                badge = Image.open(base_path + '/ImgGen/logo_pa.png')
            elif self.clan.abbreviation == 'AX':
                badge = Image.open(base_path + '/ImgGen/logo_ax.png')

            background.paste(badge, (115, 100), badge.convert("RGBA"))
            draw.text((500, 970), f"{self.clan_name}\n{self.start_time.format('DD MMMM YYYY')}", anchor="lm", fill=(255, 255, 255), stroke_width=stroke, stroke_fill=(0, 0, 0), font=clan_name)

        else:
            badge_data = self.clan_badge
            with urllib.request.urlopen(badge_data) as image_data:
                badge = Image.open(image_data)

            background.paste(badge, (125, 135), badge.convert("RGBA"))
            draw.text((225, 110), f"{self.clan_name}", anchor="mm", fill=(255,255,255), stroke_width=stroke, stroke_fill=(0, 0, 0),font=clan_name)
            draw.text((500, 970), f"{self.start_time.format('DD MMMM YYYY')}", anchor="lm", fill=(255, 255, 255), stroke_width=stroke, stroke_fill=(0, 0, 0), font=clan_name)

        # if clan.capital_league.name != 'Unranked':
        #     clan_league = await self.bot.coc_client.get_league_named(clan.capital_league.name)
        #     with urllib.request.urlopen(clan_league.icon.url) as image_data:
        #         league_badge = Image.open(image_data)
        #         league_badge = league_badge.resize((int(league_badge.width * 0.65), int(league_badge.height * 0.65)))
        #         background.paste(league_badge, (1120, 30), league_badge.convert("RGBA"))

        background.paste(arix_logo, (400, 920), arix_logo.convert("RGBA"))

        # trophy_delta = self.ending_trophies - self.starting_trophies
        # if trophy_delta >= 0:
        #     delta_str = f"+{trophy_delta}"
        # else:
        #     delta_str = f"-{trophy_delta}"

        draw.text((750, 250), f"{(self.offensive_reward * 6) + self.defensive_reward:,}", anchor="mm", fill=(255,255,255), stroke_width=4, stroke_fill=(0, 0, 0),font=total_medal_font)

        #draw.text((1155, 240), f"{self.ending_trophies:,}", anchor="lm", fill=(255,255,255), stroke_width=3, stroke_fill=(0, 0, 0),font=trophy_font)
        #draw.text((1155, 290), f"({delta_str})", anchor="lm", fill=(255,255,255), stroke_width=3, stroke_fill=(0, 0, 0),font=boxes_font)

        draw.text((155, 585), f"{self.total_loot:,}", anchor="lm", fill=(255,255,255), stroke_width=stroke, stroke_fill=(0, 0, 0),font=boxes_font)
        draw.text((870, 585), f"{self.offense_raids_completed}", anchor="lm", fill=(255,255,255), stroke_width=stroke, stroke_fill=(0, 0, 0),font=boxes_font)
        draw.text((1115, 585), f"{self.defense_raids_completed}", anchor="lm", fill=(255,255,255), stroke_width=stroke, stroke_fill=(0, 0, 0),font=boxes_font)

        draw.text((155, 817), f"{self.attack_count}", anchor="lm", fill=(255,255,255), stroke_width=stroke, stroke_fill=(0, 0, 0),font=boxes_font)
        draw.text((870, 817), f"{self.destroyed_district_count}", anchor="lm", fill=(255,255,255), stroke_width=stroke, stroke_fill=(0, 0, 0),font=boxes_font)

        draw.text((550, 370), f"{self.offensive_reward * 6}", anchor="lm", fill=(255, 255, 255), stroke_width=stroke,stroke_fill=(0, 0, 0), font=split_medal_font)
        draw.text((1245, 370), f"{self.defensive_reward}", anchor="lm", fill=(255, 255, 255), stroke_width=stroke, stroke_fill=(0, 0, 0), font=split_medal_font)

        def save_im(background):
            fpdir = self.bot.get_cog('ClashOfClans').resource_path + '/raid_results'
            if not os.path.exists(fpdir):
                os.makedirs(fpdir)

            fp = fpdir + f"{self.clan_name} - {self.start_time.format('DD MMM YYYY')}.png"
            background.save(fp, format="png", compress_level=1)
            file = discord.File(fp,filename="raid_image.png")
            return file

        file = await asyncio.to_thread(save_im,background)
        return file

    # @classmethod
    # async def get(cls,**kwargs):
    #     clan = kwargs.get('clan',None)
    #     raid_id = kwargs.get('raid_id',None)

    #     bot = BotClashState().bot

    #     raid_cache = None
    #     raid_weekend = None
    #     api_raid = None

    #     if raid_id:
    #         raid_cache = bot.clash_state.data.raids.get(raid_id)
    #         if raid_cache:
    #             return raid_cache
            
    #         raid_weekend = aRaidWeekend(raid_id=raid_id)
    #         if not raid_weekend._found_in_db:
    #             raise NoRaidFoundError(raid_id)
            
    #         bot.clash_state.data.add_to_cache(raid_weekend)
    #         return raid_weekend
        
    #     if clan:
    #         try:
    #             raidloggen = await bot.coc_client.get_raidlog(clan_tag=clan.tag,page=False,limit=1)
    #         except coc.PrivateWarLog:
    #             raidloggen = []
    #         except coc.NotFound as exc:
    #             raise InvalidTag(clan.tag) from exc
    #         except (coc.Maintenance,coc.GatewayError) as exc:
    #             raise ClashAPIError(exc) from exc

    #         if len(raidloggen) == 0:
    #             return None
    #         api_raid = raidloggen[0]

    #         if not api_raid:
    #             return None
            
    #         base_raid_id = clan.tag + str(pendulum.instance(api_raid.start_time.time).int_timestamp)
    #         raid_id = hashlib.sha256(base_raid_id.encode()).hexdigest()
    #         raid_weekend = aRaidWeekend(raid_id=raid_id)
    #         raid_weekend.update_from_api(api_raid,clan)
        
    #         bot.clash_state.data.add_to_cache(raid_weekend)
    #         return raid_weekend

class aRaidClan():
    def __init__(self,raid_entry,**kwargs):
        self.raid = raid_entry

        json = kwargs.get('json',None)
        game = kwargs.get('data',None)
        if json:
            self.tag = json['tag']
            self.name = json['name']
            self.badge = json.get('badge',None)
            self.level = json.get('level',0)
            self.attack_count = json['attack_count']
            self.district_count = json['district_count']
            self.destroyed_district_count = json['districts_destroyed']
            self.districts = [aRaidDistrict(self.raid,self,json=district) for district in json['districts']]
            self.attacks = [aRaidAttack(self.raid,self,json=attack) for attack in json.get('attacks',[])]

        if game:
            self.tag = game.tag
            self.name = game.name
            self.badge = game.badge.url
            self.level = game.level
            self.attack_count = game.attack_count
            self.district_count = game.district_count
            self.destroyed_district_count = game.destroyed_district_count
            self.districts = [aRaidDistrict(self.raid,self,data=district) for district in game.districts]
            self.attacks = [aRaidAttack(self.raid, self, data=attack) for district in game.districts for attack in district.attacks]
    
    def get_district(self,district_id):
        find_district = [rd for rd in self.districts if rd.id == district_id]
        if len(find_district) == 0:
            return None
        else:
            return find_district[0]

    def to_json(self):
        rcJson = {
            'tag': self.tag,
            'name': self.name,
            'badge': self.badge,
            'level': self.level,
            'attack_count': self.attack_count,
            'district_count': self.district_count,
            'districts_destroyed': self.destroyed_district_count,
            'districts': [d.to_json() for d in self.districts],
            'attacks': [a.to_json() for a in self.attacks]
            }
        return rcJson

class aRaidDistrict():
    def __init__(self,raid_entry,raid_clan,**kwargs):
        self.raid = raid_entry
        self.clan = raid_clan

        json_data = kwargs.get('json',None)
        game_data = kwargs.get('data',None)

        if json_data:
            self.id = json_data['id']
            self.name = json_data['name']
            self.hall_level = json_data['hall_level']
            self.destruction = json_data['destruction']
            self.attack_count = json_data['attack_count']
            self.looted = json_data['resources_looted']
        if game_data:
            data = game_data
            self.id = data.id
            self.name = data.name

            self.hall_level = data.hall_level
            self.destruction = data.destruction
            self.attack_count = data.attack_count
            self.looted = data.looted
        
    @property
    def attacks(self):
        return [attack for attack in self.clan.attacks if self.id == attack.district_id]

    def to_json(self):
        districtJson = {
            'id': self.id,
            'name': self.name,
            'hall_level': self.hall_level,
            'destruction': self.destruction,
            'attack_count': self.attack_count,
            'resources_looted': self.looted
            }
        return districtJson

class aRaidAttack():
    def __init__(self,raid_entry,raid_clan,**kwargs):
        self.raid = raid_entry
        self.clan = raid_clan

        json_data = kwargs.get('json',None)
        game_data = kwargs.get('data',None)

        if json_data:
            self.clan_tag = json_data['raid_clan']
            self.district_id = json_data['district']
            self.attacker_tag = json_data['attacker_tag']
            self.attacker_name = json_data['attacker_name']
            self.stars = json_data.get('stars',0)
            self.destruction = json_data['destruction']
        if game_data:
            data = game_data
            self.clan_tag = data.raid_clan.tag
            self.district_id = data.district.id
            self.attacker_tag = data.attacker_tag
            self.attacker_name = data.attacker_name
            self.stars = data.stars
            self.destruction = data.destruction

        self._new_stars = None
        self._new_destruction = None
    
    @property
    def district(self):
        return self.clan.get_district(self.district_id)
    @property
    def attacker(self):
        return self.raid.get_member(self.attacker_tag)
    @property
    def new_stars(self):
        if self._new_stars is None or pendulum.now() < self.raid.end_time:
            self.compute_stats()
        return self._new_stars
    @property
    def new_destruction(self):
        if self._new_destruction is None or pendulum.now() < self.raid.end_time:
            self.compute_stats()
        return self._new_destruction

    def compute_stats(self):
        base_stars = 0
        base_destruction = 0
        all_attacks = sorted(self.district.attacks,key=lambda x: (x.stars,x.destruction))
        
        for attack in all_attacks:
            if attack == self:
                break

            if attack.stars > base_stars:
                base_stars = attack.stars
            if attack.destruction > base_destruction:
                base_destruction = attack.destruction
            
        self._new_stars = max(0,self.stars - base_stars)
        self._new_destruction = max(0,self.destruction - base_destruction)

    def to_json(self):
        attackJson = {
            'raid_clan': self.clan_tag,
            'district': self.district_id,
            'attacker_tag': self.attacker_tag,
            'attacker_name': self.attacker_name,
            'stars': self.stars,
            'destruction': self.destruction
            }
        return attackJson

class aRaidMember():
    def __init__(self,raid_entry,**kwargs):
        self.raid = raid_entry

        json_data = kwargs.get('json',None)
        game_data = kwargs.get('data',None)

        if json_data:
            self.tag = json_data['tag']
            self.name = json_data['name']
            self.attack_count = json_data['attack_count']
            self.capital_resources_looted = json_data['resources_looted']
        if game_data:
            data = game_data
            self.tag = data.tag
            self.name = data.name
            self.attack_count = data.attack_count
            self.capital_resources_looted = data.capital_resources_looted

        self.medals_earned = (self.raid.offensive_reward * self.attack_count) + self.raid.defensive_reward
        self._attacks = None
    
    @property
    def attacks(self):
        if self._attacks is None or pendulum.now() < self.raid.end_time:
            self._attacks = []
            for offense_clan in self.raid.attack_log:
                self._attacks.extend([a for a in offense_clan.attacks if a.attacker_tag == self.tag])        
        return sorted(self._attacks, key=lambda x:(x.clan.tag,x.district_id,x.stars,x.destruction),reverse=True)

    def to_json(self):
        memberJson = {
            'tag': self.tag,
            'name': self.name,
            'attack_count': self.attack_count,
            'resources_looted': self.capital_resources_looted,
            }
        return memberJson

class aSummaryRaidStats():
    def __init__(self,player_tag:str,raid_log:list[aRaidWeekend]):
        def predicate_raid(raid):
            return raid.is_alliance_raid and raid.get_member(self.tag)
        
        self.timestamp = pendulum.now()
        self.raid_log = raid_log
        self.tag = player_tag

        self.raids_participated = len(
            [raid for raid in raid_log if predicate_raid(raid)]
            )
        self.raid_attacks = sum(
            [raid.get_member(self.tag).attack_count
            for raid in raid_log if predicate_raid(raid)]
            )
        self.resources_looted = sum(
            [raid.get_member(self.tag).capital_resources_looted
            for raid in raid_log if predicate_raid(raid)]
            )
        self.medals_earned = sum(
            [raid.get_member(self.tag).medals_earned
            for raid in raid_log if predicate_raid(raid)]
            )
        self.unused_attacks = (self.raids_participated * 6) - self.raid_attacks