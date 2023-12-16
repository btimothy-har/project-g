# db__player = {
#   '_id': string, #player tag
#   'discord_user': string,
#   'is_member': bool,
#   'home_clan': string,
#   'war_elo': int,
#   'first_seen': int,
#   'last_joined': int,
#   'last_removed': int,
#   'name': string,
#   'xp_level': int,
#   'townhall': int
#   }

# db__player_stats = {
#   '_id': { 'season': string, 'tag': string },
#   'season': string,
#   'tag': string,
#   'timestamp': int,
#   'name': string,
#   'town_hall': int,
#   'is_member': bool,
#   'home_clan': string,
#   'other_clans': [ string ],
#   'time_in_home_clan': int,
#   'last_seen': [ int ],
#   'attacks': { string: int },
#   'defenses': { string: int },
#   'donations_sent': { string: int },
#   'donations_rcvd': { string: int },
#   'loot_gold': { string: int },
#   'loot_elixir': { string: int },
#   'loot_darkelixir': { string: int },
#   'capitalcontribution': { string: int },
#   'clangames': { string: int }
#   }