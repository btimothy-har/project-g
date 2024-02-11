import asyncio
import discord

from redbot.core.bot import Red
from .cog_clan_commands import Clans as clan_commands
from .cog_player_commands import Players as player_commands 
from .cog_player_commands import context_menu_user_profile, context_menu_clash_accounts, context_menu_change_nickname, context_menu_restore_roles, context_menu_sync_roles
from .cog_cwl_commands import ClanWarLeagues as cwl_commands
from .cog_config_commands import ClashServerConfig as config_commands

try_limit = 60
sleep_time = 1
version = 6

async def setup(bot:Red):
    if bot.user.id not in [828838353977868368,1176156235167449139,1031240380487831664,1204751022824886322]:
        raise RuntimeError("You are not allowed to install this cog.")
    
    count = 0
    while True:
        count += 1
        api_client = bot.get_cog("ClashOfClansClient")
        if api_client:
            break
        if count > try_limit:
            raise RuntimeError("ClashOfClansClient is not installed.")
        await asyncio.sleep(sleep_time)

    
    commands_clan = clan_commands(bot,version)
    await bot.add_cog(commands_clan)

    commands_player = player_commands(bot,version)    
    await bot.add_cog(commands_player)
  
    commands_cwl = cwl_commands(bot,version)
    await bot.add_cog(commands_cwl)
     
    commands_config = config_commands(bot,version)
    await bot.add_cog(commands_config)
 
    bot.tree.add_command(context_menu_user_profile)
    bot.tree.add_command(context_menu_clash_accounts)
    bot.tree.add_command(context_menu_change_nickname)
    bot.tree.add_command(context_menu_restore_roles)
    bot.tree.add_command(context_menu_sync_roles)

    bot.coc_commands_loaded = True

async def teardown(bot:Red):
    bot.tree.remove_command("User Profile",type=discord.AppCommandType.user)
    bot.tree.remove_command("Clash Accounts",type=discord.AppCommandType.user)
    bot.tree.remove_command("Change Nickname",type=discord.AppCommandType.user)
    bot.tree.remove_command("Restore Roles",type=discord.AppCommandType.user)
    bot.tree.remove_command("Sync Roles",type=discord.AppCommandType.user)