from .checks import *

from .objects.inventory import UserInventory
from .objects.item import ShopItem

from coc_client.api_client import BotClashClient
from coc_data.objects.discord.member import aMember
from coc_data.exceptions import CacheNotReady

bot_client = BotClashClient()

async def autocomplete_eligible_accounts(interaction:discord.Interaction,current:str):
    eligible_accounts = []
    if is_bank_admin(interaction):
        eligible_accounts.extend(['current','sweep','reserve'])

    

    try:
        if is_bank_admin(interaction):
            eligible_clans = bot_client.cog.get_alliance_clans()
        else:
            member = aMember(interaction.user.id)
            eligible_clans = member.coleader_clans
    except CacheNotReady:
        eligible_clans = []

    selection = []
    if not current:
        selection.extend([app_commands.Choice(
            name=c,
            value=c)
        for c in eligible_accounts
        ])
        selection.extend([app_commands.Choice(
            name=f"{c.abbreviation} {c.name} | {c.tag}",
            value=c.tag)
        for c in eligible_clans
        ])
    else:
        selection.extend([app_commands.Choice(
            name=c,
            value=c)
        for c in eligible_accounts if current.lower() in c.lower()
        ])
        selection.extend([app_commands.Choice(
            name=f"{c.abbreviation} {c.name} | {c.tag}",
            value=c.tag)
        for c in eligible_clans if current.lower() in c.name.lower() or current.lower() in c.tag.lower() or current.lower() in c.abbreviation.lower()
        ])
    return selection

async def autocomplete_store_items(interaction:discord.Interaction,current:str):
    guild_items = ShopItem.get_by_guild(interaction.guild.id)

    if not current:
        selection = guild_items[:5]
        return [app_commands.Choice(
            name=f"{item}",
            value=item.id)
        for item in selection
        ]
    else:
        selection = [item for item in guild_items if current.lower() in item.name.lower()]
        return [app_commands.Choice(
            name=f"{item}",
            value=item.id)
        for item in selection
        ]

async def autocomplete_store_items_restock(interaction:discord.Interaction,current:str):
    guild_items = [i for i in ShopItem.get_by_guild(interaction.guild.id) if i._stock >= 0]

    if not current:
        selection = guild_items[:5]
        return [app_commands.Choice(
            name=f"{item}",
            value=item.id)
        for item in selection
        ]
    else:
        selection = [item for item in guild_items if current.lower() in item.name.lower()]
        return [app_commands.Choice(
            name=f"{item}",
            value=item.id)
        for item in selection
        ]

async def autocomplete_distribute_items(interaction:discord.Interaction,current:str):

    if interaction.user.id in interaction.client.owner_ids:
        guild_items = [i for i in ShopItem.get_by_guild(interaction.guild.id) if i.type in ['basic','cash']]
    else:
        guild_items = [i for i in ShopItem.get_by_guild(interaction.guild.id) if i.type == 'basic']

    if not current:
        selection = guild_items[:5]
        return [app_commands.Choice(
            name=f"{item}",
            value=item.id)
        for item in selection
        ]
    else:
        selection = [item for item in guild_items if current.lower() in item.name.lower()]
        return [app_commands.Choice(
            name=f"{item}",
            value=item.id)
        for item in selection
        ]

async def autocomplete_gift_items(interaction:discord.Interaction,current:str):
    inv = UserInventory(interaction.user)

    guild_items = [i for i in inv.inventory if i.guild_id == interaction.guild.id]

    if not current:
        selection = guild_items[:5]
        return [app_commands.Choice(
            name=f"{item.name} (Qty: {item.quantity})",
            value=item.id)
        for item in selection
        ]
    else:
        selection = [item for item in guild_items if current.lower() in item.name.lower()]
        return [app_commands.Choice(
            name=f"{item.name} (Qty: {item.quantity})",
            value=item.id)
        for item in selection
        ]