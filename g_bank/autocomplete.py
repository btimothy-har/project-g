import discord
import random

from redbot.core import app_commands

from coc_main.api_client import BotClashClient
from coc_main.cog_coc_client import ClashOfClansClient
from coc_main.discord.member import aMember

from .objects.inventory import UserInventory
from .objects.item import ShopItem

from .checks import is_bank_admin

bot_client = BotClashClient()
global_accounts = ["current","sweep","reserve"]

def get_client() -> ClashOfClansClient:
    return bot_client.bot.get_cog('ClashOfClansClient')

async def autocomplete_eligible_accounts(interaction:discord.Interaction,current:str):
    client = get_client()
    try:
        sel_accounts = []
        if is_bank_admin(interaction):
            if current:
                sel_accounts.extend([a for a in global_accounts if current.lower() in a])
            else:
                sel_accounts.extend(global_accounts)

        if is_bank_admin(interaction):
            clans = await bot_client.coc.get_alliance_clans()
        else:
            user = await aMember(interaction.user.id)
            clans = user.coleader_clans

        if current:
            eligible_clans = [c for c in clans if current.lower() in c.name.lower() or current.lower() in c.tag.lower() or current.lower() in c.abbreviation.lower()]
        else:
            eligible_clans = clans

        selection = []
        selection.extend([app_commands.Choice(
            name=c,
            value=c)
        for c in sel_accounts
        ])
        selection.extend([app_commands.Choice(
            name=f"{c.name} | {c.tag}",
            value=c.tag)
        for c in random.sample(list(eligible_clans),min(len(eligible_clans),3))
        ])
        return selection
    
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_eligible_accounts")

async def autocomplete_store_items(interaction:discord.Interaction,current:str):
    try:
        guild_items = await ShopItem.get_by_guild(interaction.guild.id)

        if not current:
            selection = guild_items
            return [app_commands.Choice(
                name=f"{item}",
                value=item.id)
            for item in random.sample(selection,min(len(selection),5))
            ]
        else:
            selection = [item for item in guild_items if current.lower() in item.name.lower() or current.lower() == item.id.lower()]
            return [app_commands.Choice(
                name=f"[{item.type.capitalize()} Item] {item.name} | Price: {item.price}",
                value=item.id)
            for item in random.sample(selection,min(len(selection),5))
            ]
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_store_items")

async def autocomplete_store_items_restock(interaction:discord.Interaction,current:str):
    try:
        items = await ShopItem.get_by_guild(interaction.guild.id)
        guild_items = [i for i in items if i._stock >= 0 and i.type != 'cash']

        if not current:
            selection = guild_items
            return [app_commands.Choice(
                name=f"[{item.type.capitalize()} Item] {item.name} | Price: {item.price} | Stock: {item.stock}",
                value=item.id)
            for item in random.sample(selection,min(len(selection),5))
            ]
        else:
            selection = [item for item in guild_items if current.lower() in item.name.lower() or current.lower() == item.id.lower()]
            return [app_commands.Choice(
                name=f"[{item.type.capitalize()} Item] {item.name} | Price: {item.price} | Stock: {item.stock}",
                value=item.id)
            for item in random.sample(selection,min(len(selection),5))
            ]
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_store_items_restock")

async def autocomplete_distribute_items(interaction:discord.Interaction,current:str):
    try:
        bank_cog = bot_client.bot.get_cog("Bank")

        items = await ShopItem.get_by_guild(interaction.guild.id)
        if interaction.user.id in interaction.client.owner_ids:
            guild_items = [i for i in items]
        elif interaction.user.id in bank_cog.bank_admins:
            guild_items = [i for i in items if i.type != 'cash']
        else:
            guild_items = [i for i in items if i.type != 'cash' and getattr(i.assigns_role,'id',None) not in [bank_cog._bank_pass_role,bank_cog._bank_penalty_role]]

        if not current:
            selection = guild_items
            return [app_commands.Choice(
                name=f"{item}",
                value=item.id)
            for item in random.sample(selection,min(len(selection),5))
            ]
        else:
            selection = [item for item in guild_items if current.lower() in item.name.lower() or current.lower() == item.id.lower()]
            return [app_commands.Choice(
                name=f"{item.type.capitalize()} {item.name} | Price: {item.price}",
                value=item.id)
            for item in random.sample(selection,min(len(selection),5))
            ]
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_distribute_items")

async def autocomplete_redeem_items(interaction:discord.Interaction,current:str):
    try:
        items = await ShopItem.get_by_guild(interaction.guild.id)        
        guild_items = [i for i in items if i.type == 'basic']

        if not current:
            selection = guild_items
            return [app_commands.Choice(
                name=f"{item}",
                value=item.id)
            for item in random.sample(selection,min(len(selection),5))
            ]
        else:
            selection = [item for item in guild_items if current.lower() in item.name.lower() or current.lower() == item.id.lower()]
            return [app_commands.Choice(
                name=f"{item.type.capitalize()} {item.name} | Price: {item.price}",
                value=item.id)
            for item in random.sample(selection,min(len(selection),5))
            ]
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_redeem_items")

async def autocomplete_gift_items(interaction:discord.Interaction,current:str):
    try:
        inv = await UserInventory(interaction.user)
        guild_items = [i for i in inv.items if i.guild_id == interaction.guild.id and not i._is_locked and i.is_user_accessible]

        if not current:
            selection = guild_items
            return [app_commands.Choice(
                name=f"{item.name} (Purchased: {item.timestamp.format('YYYY-MM-DD')})",
                value=str(item._inv_id))
            for item in random.sample(selection,min(len(selection),5))
            ]
        else:
            selection = [item for item in guild_items if current.lower() in item.name.lower()]
            return [app_commands.Choice(
                name=f"{item.name} (Purchased: {item.timestamp.format('YYYY-MM-DD')})",
                value=str(item._inv_id))
            for item in random.sample(selection,min(len(selection),5))
            ]
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_gift_items")