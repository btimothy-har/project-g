from mongoengine import *

##################################################
#####
##### GUILD LINKS
#####
##################################################
class db_ClanGuildLink(Document):
    #ID using format {'guild':int,'tag':#123}
    link_id = DictField(primary_key=True,required=True)
    tag = StringField(required=True)
    guild_id = IntField(required=True)
    member_role = IntField(default=0)
    elder_role = IntField(default=0)
    coleader_role = IntField(default=0)

class db_GuildClanPanel(Document):
    #ID using format {'guild':int,'channel':123}
    panel_id = DictField(primary_key=True,required=True)    
    server_id = IntField(default=0,required=True)
    channel_id = IntField(default=0,required=True)
    message_id = IntField(default=0)
    long_message_ids = ListField(IntField(),default=[])

class db_GuildApplyPanel(Document):
    #ID using format {'guild':int,'channel':123}
    panel_id = DictField(primary_key=True,required=True)

    server_id = IntField(default=0,required=True)
    channel_id = IntField(default=0,required=True)
    message_id = IntField(default=0)

    #config
    select_clans = BooleanField(default=True)
    
    #tickettool link
    ticket_prefix = StringField(default="")
    listener_channel = IntField(default=0)

    #questions
    text_q1 = StringField(default="")
    placeholder_q1 = StringField(default="")
    text_q2 = StringField(default="")
    placeholder_q2 = StringField(default="")
    text_q3 = StringField(default="")
    placeholder_q3 = StringField(default="")
    text_q4 = StringField(default="")
    placeholder_q4 = StringField(default="")

class db_ClanApplication(Document):
    applicant_id = IntField(required=True)
    guild_id = IntField(required=True)
    created = IntField(required=True)
    tags = ListField(StringField(),default=[])
    clans = ListField(StringField(),default=[])

    answer_q1 = ListField(StringField(),default=[])
    answer_q2 = ListField(StringField(),default=[])
    answer_q3 = ListField(StringField(),default=[])
    answer_q4 = ListField(StringField(),default=[])

    ticket_channel = IntField(default=0)
    bot_prefix = StringField(default="")

class db_ClockConfig(Document):
    s_id = IntField(primary_key=True,required=True)
    use_channels = BooleanField(default=False)
    use_events = BooleanField(default=False)
    season_channel = IntField(default=0)
    season_event = IntField(default=0)    
    raids_channel = IntField(default=0)
    raids_event = IntField(default=0)
    clangames_channel = IntField(default=0)
    clangames_event = IntField(default=0)
    warleague_channel = IntField(default=0)
    warleague_event = IntField(default=0)

##################################################
#####
##### MEMBER OBJECT
#####
##################################################
class db_DiscordMember(Document):
    #ID using format {'guild':int,'user':int}
    member_id = DictField(primary_key=True,required=True)    
    user_id = IntField(required=True)
    guild_id = IntField(required=True)
    default_account = StringField(default="")
    roles = ListField(StringField(),default=[])
    last_role_save = IntField(default=0)
    last_role_sync = IntField(default=0)
    last_payday = IntField(default=0)

##################################################
#####
##### MEMBER OBJECT
#####
##################################################
class db_RecruitingPost(Document):
    is_active = BooleanField(default=False)
    ad_name = StringField(required=True)
    ad_link = StringField(required=True)
    guild = IntField(default=0)
    channel = IntField(default=0)
    interval = IntField(required=True)
    remind_user = IntField(default=0)
    last_posted = IntField(default=0)
    last_user = IntField(default=0)
    active_reminder = IntField(default=0)
    logs = ListField(DictField(),default=[])