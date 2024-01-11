##################################################
#####
##### WAR LEAGUE GROUP
#####
##################################################
# db__clan_war = {
#     '_id': string,
#     'type': string,
#     'state': string,
#     'war_tag': string,
#     'league_group': string,
#     'preparation_start_time': int,
#     'start_time': int,
#     'end_time': int,
#     'team_size': int,
#     'attacks_per_member': int,
#     'clans': [ {} ],
#     'members': [ {} ],
#     'attacks': [ {} ],
#     'is_alliance_war': bool,
#     'last_save': int
#     }

##################################################
#####
##### CLAN WAR LEAGUES
#####
##################################################
# db__war_league_group = {
#     '_id': string,
#     'season': string,
#     'state': string,
#     'league': string,
#     'number_of_rounds': int,
#     'rounds': [ [ string, string ], [ string, string ] ],
#     'clans': [ string ]
#     }

# db__war_league_clan = {
#     '_id': { 'season': string, 'tag': string },
#     'season': string,
#     'tag': string,
#     'name': string,
#     'badge': string,
#     'is_participating': bool,
#     'league_channel': int,
#     'league_role': int,
#     'roster_open': bool,
#     'league_group': string,
#     'master_roster': [ string, string, string ]
#     }

# db__war_league_player = {
#     '_id': { 'season': string, 'tag': string },
#     'season': string,
#     'tag': string,
#     'name': string,
#     'registered': bool,
#     'discord_user': int,
#     'roster_clan': string,
#     'league_clan': string,
#     'league_group': int,
#     'townhall': int,
#     'elo_change': float,
#     }

##################################################
#####
##### RAID WEEKEND
#####
##################################################
# db__raid_weekend = {
#     '_id': string,
#     'clan_tag': string,
#     'clan_name': string,
#     'clan_badge': string,
#     'clan_level': int,
#     'starting_trophies': int,
#     'ending_trophies': int,
#     'is_alliance_raid': bool,
#     'state': string,
#     'start_time': int,
#     'end_time': int,
#     'total_loot': int,
#     'attack_count': int,
#     'destroyed_district_count': int,
#     'offensive_reward': int,
#     'defensive_reward': int,
#     'attack_log': [ {} ],
#     'defense_log': [ {} ],
#     'members': [ {} ],
#     'last_save': int
#     }