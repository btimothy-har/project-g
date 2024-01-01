##################################################
#####
##### CLAN/DISCORD LINKS
#####
##################################################

# db__clan_guild_link = {
#     '_id': { 'guild': int, 'tag': string },
#     'tag': string,
#     'guild_id': int,
#     'member_role': int,
#     'elder_role': int,
#     'coleader_role': int
#     }

# db__clan_data_feed = {
#     '_id': ObjectId,
#     'tag': string,
#     'type': int,
#     'guild_id': int,
#     'channel_id': int
#     }

# db__clan_event_reminder = {
#     '_id': ObjectId,
#     'tag': string,
#     'type': int,
#     'sub_type': [ string ],
#     'guild_id': int,
#     'channel_id': int,
#     'reminder_interval': [ int ],
#     'interval_tracker': [ int ]
#     }

##################################################
#####
##### DISCORD PANELS
#####
##################################################
# db__guild_clan_panel = {
#     '_id': { 'guild': int, 'channel': int },
#     'server_id': int,
#     'channel_id': int,
#     'message_id': int,
#     'long_message_ids': [ int ]
#     }

# db__guild_apply_panel = {
#     '_id': { 'guild': int, 'channel': int },
#     'server_id': int,
#     'channel_id': int,
#     'message_id': int,
#     'select_clans': bool,
#     'ticket_prefix': string,
#     'listener_channel': int,
#     'text_q1': string,
#     'placeholder_q1': string,
#     'text_q2': string,
#     'placeholder_q2': string,
#     'text_q3': string,
#     'placeholder_q3': string,
#     'text_q4': string,
#     'placeholder_q4': string
#     }

# db__clan_application = {
#     '_id': ObjectId,
#     'applicant_id': int,
#     'guild_id': int,
#     'created': int,
#     'tags': [ string ],
#     'clans': [ string ],
#     'answer_q1': [ string ],
#     'answer_q2': [ string ],
#     'answer_q3': [ string ],
#     'answer_q4': [ string ],
#     'ticket_channel': int,
#     'bot_prefix': string
#     }

##################################################
#####
##### DISCORD CLOCKS
#####
##################################################

# db__clock_config = {
#     '_id': int,
#     'use_channels': bool,
#     'use_events': bool,
#     'season_channel': int,
#     'season_event': int,
#     'raids_channel': int,
#     'raids_event': int,
#     'clangames_channel': int,
#     'clangames_event': int,
#     'warleague_channel': int,
#     'warleague_event': int
#     }

##################################################
#####
##### MEMBER OBJECT
#####
##################################################

# db__discord_member = {
#     '_id': { 'guild': int, 'user': int },
#     'user_id': int,
#     'guild_id': int,
#     'default_account': string,
#     'reward_account': string,
#     'roles': [ string ],
#     'last_role_save': int,
#     'last_role_sync': int,
#     'last_payday': int
#     }

##################################################
#####
##### MEMBER OBJECT
#####
##################################################

# db__recruiting_post = {
#     '_id': ObjectId,
#     'is_active': bool,
#     'ad_name': string,
#     'ad_link': string,
#     'guild': int,
#     'channel': int,
#     'interval': int,
#     'remind_user': int,
#     'last_posted': int,
#     'last_user': int,
#     'active_reminder': int,
#     'logs': [ { 'user': int, 'time': int } ]
#     }