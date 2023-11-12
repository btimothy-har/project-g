from mongoengine import *

##################################################
#####
##### WAR LEAGUE GROUP
#####
##################################################
class db_ClanWar(Document):
    war_id = StringField(primary_key=True,required=True)
    type = StringField(default="")
    state = StringField(default="")
    war_tag = StringField(default="")
    league_group = StringField(default="")
    preparation_start_time = IntField(default=0)
    start_time = IntField(default=0)
    end_time = IntField(default=0)
    team_size = IntField(default=0)
    attacks_per_member = IntField(default=0)
    clans = ListField(DictField(),default=[])
    members = ListField(DictField(),default=[])
    attacks = ListField(DictField(),default=[])
    is_alliance_war = BooleanField(default=False)
    last_save = IntField(default=0)

##################################################
#####
##### CLAN WAR LEAGUES
#####
##################################################
class db_WarLeagueGroup(Document):
    group_id = StringField(primary_key=True,required=True)
    season = StringField(default="")
    state = StringField(default="")
    league = StringField(default="")
    number_of_rounds = IntField(default=0)
    rounds = ListField(ListField(StringField()),default=[])
    clans = ListField(StringField(),default=[])

class db_WarLeagueClan(Document):
    #ID using format {'season':'1-2023','tag':'#12345678'}
    cwl_id = DictField(primary_key=True,required=True)
    season = StringField(default="",required=True)
    tag = StringField(default="",required=True)
    name = StringField(default="")
    is_participating = BooleanField(default=False)
    roster_open = BooleanField(default=True)    
    league_group = StringField(default="") #hash
    master_roster = ListField(StringField(),default=[])
    
    #signup_open = BooleanField(default=False)

class db_WarLeaguePlayer(Document):
    #ID using format {'season':'1-2023','tag':'#12345678'}
    cwl_id = DictField(primary_key=True,required=True)
    season = StringField(default="",required=True)
    tag = StringField(default="",required=True)
    name = StringField(default="")
    registered = BooleanField(default=False)
    discord_user = IntField(default=0)
    roster_clan = StringField(default="")    
    league_clan = StringField(default="")
    league_group = IntField(default=0)
    townhall = IntField(default=0)

##################################################
#####
##### RAID WEEKEND
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