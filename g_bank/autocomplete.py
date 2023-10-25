import discord
import random

from mongoengine import *

from redbot.core import app_commands
from .objects.inventory import UserInventory
from .objects.item import ShopItem

from .checks import is_bank_admin

from coc_main.api_client import BotClashClient

from coc_main.coc_objects.clans.mongo_clan import db_Clan, db_AllianceClan

bot_client = BotClashClient()

async def autocomplete_eligible_accounts(interaction:discord.Interaction,current:str):
    try:
        sel_accounts = []
        if is_bank_admin(interaction):
            master_accounts = ['current','sweep','reserve','arix']
            if current:
                sel_accounts.extend([a for a in master_accounts if current.lower() in a])
            else:
                sel_accounts.extend(master_accounts)

        if is_bank_admin(interaction):
            eligible_clan_tags = [db.tag for db in db_AllianceClan.objects()]
        else:
            eligible_clan_tags = [db.tag for db in db_AllianceClan.objects(Q(coleaders__contains=interaction.user.id) | Q(leader=interaction.user.id))]

        if current:
            eligible_clans = db_Clan.objects(
                (Q(tag__in=eligible_clan_tags)) &
                (Q(tag__icontains=current) | Q(name__icontains=current) | Q(abbreviation=current.upper()))
                )
        else:
            eligible_clans = db_Clan.objects(Q(tag__in=eligible_clan_tags))

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
        guild_items = ShopItem.get_by_guild(interaction.guild.id)

        if not current:
            selection = guild_items
            return [app_commands.Choice(
                name=f"{item}",
                value=item.id)
            for item in random.sample(selection,min(len(selection),5))
            ]
        else:
            selection = [item for item in guild_items if current.lower() in item.name.lower()]
            return [app_commands.Choice(
                name=f"{item}",
                value=item.id)
            for item in random.sample(selection,min(len(selection),5))
            ]
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_store_items")

async def autocomplete_store_items_restock(interaction:discord.Interaction,current:str):
    try:
        guild_items = [i for i in ShopItem.get_by_guild(interaction.guild.id) if i._stock >= 0]

        if not current:
            selection = guild_items
            return [app_commands.Choice(
                name=f"{item}",
                value=item.id)
            for item in random.sample(selection,min(len(selection),5))
            ]
        else:
            selection = [item for item in guild_items if current.lower() in item.name.lower()]
            return [app_commands.Choice(
                name=f"{item}",
                value=item.id)
            for item in random.sample(selection,min(len(selection),5))
            ]
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_store_items_restock")

async def autocomplete_distribute_items(interaction:discord.Interaction,current:str):

    try:
        if interaction.user.id in interaction.client.owner_ids:
            guild_items = [i for i in ShopItem.get_by_guild(interaction.guild.id) if i.type in ['basic','cash']]
        else:
            guild_items = [i for i in ShopItem.get_by_guild(interaction.guild.id) if i.type == 'basic']

        if not current:
            selection = guild_items
            return [app_commands.Choice(
                name=f"{item}",
                value=item.id)
            for item in random.sample(selection,min(len(selection),5))
            ]
        else:
            selection = [item for item in guild_items if current.lower() in item.name.lower()]
            return [app_commands.Choice(
                name=f"{item}",
                value=item.id)
            for item in random.sample(selection,min(len(selection),5))
            ]
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_distribute_items")

async def autocomplete_gift_items(interaction:discord.Interaction,current:str):
    try:
        inv = UserInventory(interaction.user)
        guild_items = [i for i in inv.inventory if i.guild_id == interaction.guild.id]

        if not current:
            selection = guild_items
            return [app_commands.Choice(
                name=f"{item.name} (Qty: {item.quantity})",
                value=item.id)
            for item in random.sample(selection,min(len(selection),5))
            ]
        else:
            selection = [item for item in guild_items if current.lower() in item.name.lower()]
            return [app_commands.Choice(
                name=f"{item.name} (Qty: {item.quantity})",
                value=item.id)
            for item in random.sample(selection,min(len(selection),5))
            ]
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_gift_items")