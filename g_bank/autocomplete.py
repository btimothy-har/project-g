from .checks import *

from coc_client.api_client import BotClashClient
from coc_data.objects.discord.member import aMember
from coc_data.exceptions import CacheNotReady

async def autocomplete_eligible_accounts(interaction:discord.Interaction,current:str):
    eligible_accounts = []
    if is_bank_admin(interaction):
        eligible_accounts.extend(['current','sweep','reserve'])

    client = BotClashClient()

    member = aMember(interaction.user.id)

    try:
        if is_bank_admin(interaction):
            eligible_clans = client.cog.get_alliance_clans()
        else:
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