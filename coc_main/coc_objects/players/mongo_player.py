from mongoengine import *

class db_Player(Document):
    tag = StringField(primary_key=True,required=True)
    discord_user = IntField(default=0)
    is_member = BooleanField(default=False)
    home_clan = StringField(default="")
    first_seen = IntField(default=0)
    last_joined = IntField(default=0)
    last_removed = IntField(default=0)

    name = StringField(default="")
    xp_level = IntField(default=0)
    townhall = IntField(default=0)

    meta = {
        'indexes': [
            'tag',
            '$tag',
            '#tag',
            'discord_user',
            'is_member',
            'home_clan'
            ],
        'index_background': True,
        'auto_create_index_on_save': True,
        }

class db_PlayerStats(Document):
    #ID using format {'season':'1-2023','tag':'#12345678'}
    stats_id = DictField(primary_key=True,required=True)
    season = StringField(required=True)
    tag = StringField(required=True)    
    timestamp = IntField(default=0)
    name = StringField(default="")
    town_hall = IntField(default=0)
    is_member = BooleanField(default=False)
    home_clan = StringField(default="")
    other_clans = ListField(StringField(),default=[])
    time_in_home_clan = IntField(default=0)        
    last_seen = ListField(IntField(),default=[])    
    attacks = DictField(default={})
    defenses = DictField(default={})
    donations_sent = DictField(default={})
    donations_rcvd = DictField(default={})
    loot_gold = DictField(default={})
    loot_elixir = DictField(default={})
    loot_darkelixir = DictField(default={})
    capitalcontribution = DictField(default={})
    clangames = DictField(default={})

    meta = {
        'indexes': [
            'stats_id',
            ('tag','season'),
            'is_member',
            'home_clan'
            ],
        'index_background': True,
        'auto_create_index_on_save': True,
        }