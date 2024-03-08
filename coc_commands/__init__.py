import asyncio
import discord

from redbot.core.bot import Red
from .cog_clan_commands import Clans as clan_commands
from .cog_player_commands import Players as player_commands 
from .cog_player_commands import context_menu_user_profile, context_menu_clash_accounts, context_menu_change_nickname, context_menu_restore_roles, context_menu_sync_roles
from .cog_config_commands import ClashServerConfig as config_commands

try_limit = 60
sleep_time = 1

async def setup(bot:Red):    
    count = 0
    while True:
        count += 1
        coc_main = bot.get_cog("ClashOfClansMain")
        if getattr(coc_main.global_client,'_ready',False):
            break
        if count > try_limit:
            raise RuntimeError("ClashOfClansClient is not installed.")
        await asyncio.sleep(sleep_time)
    
    count = 0
    while True:
        count += 1
        coc_discord = bot.get_cog("ClashOfClansDiscord")
        if coc_discord:
            break
        if count > try_limit:
            raise RuntimeError("ClashOfClansDiscord is not installed.")
        await asyncio.sleep(sleep_time)

    
    commands_clan = clan_commands()
    await bot.add_cog(commands_clan)

    commands_player = player_commands()    
    await bot.add_cog(commands_player)
     
    commands_config = config_commands()
    await bot.add_cog(commands_config)
 
    bot.tree.add_command(context_menu_user_profile)
    bot.tree.add_command(context_menu_clash_accounts)
    bot.tree.add_command(context_menu_change_nickname)
    bot.tree.add_command(context_menu_restore_roles)
    bot.tree.add_command(context_menu_sync_roles)

async def teardown(bot:Red):
    bot.tree.remove_command("User Profile",type=discord.AppCommandType.user)
    bot.tree.remove_command("Clash Accounts",type=discord.AppCommandType.user)
    bot.tree.remove_command("Change Nickname",type=discord.AppCommandType.user)
    bot.tree.remove_command("Restore Roles",type=discord.AppCommandType.user)
    bot.tree.remove_command("Sync Roles",type=discord.AppCommandType.user)