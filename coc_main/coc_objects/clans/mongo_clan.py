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

    meta = {
        'indexes': [
            'abbreviation'
            ]
        }

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