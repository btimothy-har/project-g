from mongoengine import *

class db_Clan(Document):
    tag = StringField(primary_key=True,required=True)
    abbreviation = StringField(default="")
    emoji = StringField(default="")
    unicode_emoji = StringField(default="")

    name = StringField(default="")
    badge = StringField(default="")
    level = IntField(default=0)
    capital_hall = IntField(default=0)
    war_league = StringField(default="")

class db_AllianceClan(Document):
    tag = StringField(primary_key=True,required=True)
    description = StringField(default="")
    recruitment_level = ListField(IntField(),default=[])
    recruitment_info = StringField(default="")
    leader = IntField(default=0)
    coleaders = ListField(IntField(),default=[])
    elders = ListField(IntField(),default=[])
    
    #deprecated
    announcement_channel = IntField(default=0)
    member_role = IntField(default=0)
    home_guild = IntField(default=0)
    elder_role = IntField(default=0)
    coleader_role = IntField(default=0)

class db_WarLeagueClanSetup(Document):
    tag = StringField(primary_key=True,required=True)
    is_active = BooleanField(default=False)
    role = IntField(default=0)
    channel = IntField(default=0)

    #deprecated
    webhook = IntField(default=0)

class db_ClanDataFeed(Document):
    #1 - member feed
    #2 - donation feed
    #3 - raid weekend results
    #4 - capital contribution
    tag = StringField(required=True)
    type = IntField(required=True)
    guild_id = IntField(required=True)
    channel_id = IntField(required=True)

class db_ClanEventReminder(Document):
    #type 1 - war
    #type 2 - raid
    #subtype (only for war) - random, friendly, cwl
    tag = StringField(required=True)
    type = IntField(required=True)
    sub_type = ListField(StringField(),default=[])
    guild_id = IntField(required=True)
    channel_id = IntField(required=True)
    reminder_interval = ListField(IntField(),default=[])
    interval_tracker = ListField(IntField(),default=[])