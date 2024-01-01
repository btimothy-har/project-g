import asyncio
import coc
import discord
import os
import pendulum
import xlsxwriter

from typing import *
from discord.ext import tasks

from redbot.core import Config, commands, app_commands, bank
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.utils import AsyncIter,bounded_gather

from coc_main.api_client import BotClashClient, ClashOfClansError, InvalidAbbreviation
from coc_main.cog_coc_client import ClashOfClansClient, aClan, aClanWar, aRaidWeekend

from coc_main.coc_objects.players.player import aPlayer
from coc_main.coc_objects.events.clan_war import aWarPlayer
from coc_main.coc_objects.events.raid_weekend import aRaidMember

from coc_main.discord.member import aMember

from coc_main.tasks.player_tasks import PlayerLoop
from coc_main.tasks.war_tasks import ClanWarLoop
from coc_main.tasks.raid_tasks import ClanRaidLoop

from coc_main.utils.components import clash_embed, MenuPaginator, DiscordSelectMenu, DiscordModal, DiscordButton
from coc_main.utils.constants.coc_constants import WarResult, ClanWarType, HeroAvailability
from coc_main.utils.constants.ui_emojis import EmojisUI
from coc_main.utils.checks import is_admin, is_owner
from coc_main.utils.autocomplete import autocomplete_clans_coleader

from .objects.accounts import BankAccount, MasterAccount, ClanAccount
from .objects.inventory import UserInventory
from .objects.item import ShopItem
from .objects.redemption import RedemptionTicket
from .views.store_manager import AddItem
from .views.user_store import UserStore

from .checks import is_bank_admin, is_payday_server, is_coleader_or_bank_admin
from .autocomplete import global_accounts, autocomplete_eligible_accounts, autocomplete_store_items, autocomplete_store_items_restock, autocomplete_distribute_items, autocomplete_gift_items, autocomplete_redeem_items

from mee6rank.mee6rank import Mee6Rank

bot_client = BotClashClient()
non_member_multiplier = 0.2

############################################################
############################################################
#####
##### CLIENT COG
#####
############################################################
############################################################
class Bank(commands.Cog):
    """
    Commands for the Guild Bank.  
    """

    __author__ = bot_client.author
    __version__ = bot_client.version
    __release__ = 5

    def __init__(self,bot:Red):
        self.bot = bot

        self.bot.coc_bank_path = f"{cog_data_path(self)}/reports"
        if not os.path.exists(self.bot.coc_bank_path):
            os.makedirs(self.bot.coc_bank_path)

        self.bank_admins = []
        self._bank_guild = 1132581106571550831 if bot.user.id == 1031240380487831664 else 680798075685699691

        self._log_channel = 0
        self._log_queue = asyncio.Queue()
        self._log_task_lock = asyncio.Lock()
        self._log_lock = asyncio.Lock()

        self._redm_log_channel = 1189491279449575525 if bot.user.id == 1031240380487831664 else 1189120831880700014
        self._bank_admin_role = 1189481989984751756 if bot.user.id == 1031240380487831664 else 1123175083272327178
        self._bank_pass_role = 0

        self._subscription_lock = asyncio.Lock()

        self.config = Config.get_conf(self,identifier=644530507505336330,force_registration=True)
        default_global = {
            "use_rewards":False,
            "log_channel":0,
            "bank_pass_role":0,
            "admins":[],
            }
        self.config.register_global(**default_global)

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}.{self.__release__}"
    
    async def cog_load(self):
        try:
            self.use_rewards = await self.config.use_rewards()
        except:
            self.use_rewards = False
        try:
            self._log_channel = await self.config.log_channel()
        except:
            self._log_channel = 0        
        try:
            self._bank_pass_role = await self.config.bank_pass_role()
        except:
            self._bank_pass_role = 0

        self.bank_admins = await self.config.admins()
        asyncio.create_task(self.start_cog())
    
    async def start_cog(self):
        while True:
            if getattr(bot_client,'_is_initialized',False):
                break
            await asyncio.sleep(1)

        self.current_account = await MasterAccount('current')
        self.sweep_account = await MasterAccount('sweep')
        self.reserve_account = await MasterAccount('reserve')
    
        PlayerLoop.add_player_event(self.member_th_progress_reward)
        PlayerLoop.add_player_event(self.member_hero_upgrade_reward)
        PlayerLoop.add_achievement_event(self.capital_contribution_rewards)        
        ClanWarLoop.add_war_end_event(self.clan_war_ended_rewards)
        ClanRaidLoop.add_raid_end_event(self.raid_weekend_ended_rewards)

        await self.bot.wait_until_red_ready()
        u_iter = AsyncIter(self.bank_admins)
        async for user_id in u_iter:
            guild_user = self.bank_guild.get_member(user_id)
            if not guild_user:
                continue
            admin_role = self.bank_guild.get_role(self._bank_admin_role)
            if admin_role and admin_role not in guild_user.roles:
                await guild_user.add_roles(admin_role)
        
        self.subscription_item_expiry.start()
        self.send_bank_logs_batch.start()
    
    async def cog_unload(self):
        self.subscription_item_expiry.cancel()
        self.send_bank_logs_batch.cancel()
        PlayerLoop.remove_player_event(self.member_th_progress_reward)
        PlayerLoop.remove_player_event(self.member_hero_upgrade_reward)
        PlayerLoop.remove_achievement_event(self.capital_contribution_rewards)
        ClanWarLoop.remove_war_end_event(self.clan_war_ended_rewards)
        ClanRaidLoop.remove_raid_end_event(self.raid_weekend_ended_rewards)
        ClanAccount._cache = {}
        MasterAccount._cache = {}

    @property
    def client(self) -> ClashOfClansClient:
        return self.bot.get_cog("ClashOfClansClient")
    
    @property
    def bank_guild(self) -> Optional[discord.Guild]:
        return self.bot.get_guild(self._bank_guild)

    @property
    def log_channel(self) -> Optional[discord.TextChannel]:
        return self.bot.get_channel(self._log_channel)
    
    @property
    def redemption_log_channel(self) -> discord.TextChannel:
        return self.bot.get_channel(self._redm_log_channel)
    
    @property
    def bank_pass_role(self) -> Optional[discord.Role]:
        return self.bank_guild.get_role(self._bank_pass_role) if self.bank_guild else None
    
    async def cog_command_error(self,ctx,error):
        if isinstance(getattr(error,'original',None),ClashOfClansError):
            embed = await clash_embed(
                context=ctx,
                message=f"{error.original.message}",
                success=False,
                timestamp=pendulum.now()
                )
            await ctx.send(embed=embed)
            return
        await self.bot.on_command_error(ctx,error,unhandled_by_cog=True)

    async def cog_app_command_error(self,interaction,error):
        if isinstance(getattr(error,'original',None),ClashOfClansError):
            embed = await clash_embed(
                context=interaction,
                message=f"{error.original.message}",
                success=False,
                timestamp=pendulum.now()
                )
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed,view=None)
            else:
                await interaction.response.send_message(embed=embed,view=None,ephemeral=True)
            return

    async def _send_log(self,user:discord.User,done_by:discord.User,amount:int,comment:str) -> discord.Embed:
        if amount == 0:
            return
        
        async with self._log_lock:
            await self._log_queue.put({
                'user_id': user.id,
                'done_by_id': done_by.id,
                'amount': amount,
                'comment': comment,
                'timestamp': pendulum.now().int_timestamp
                })
    
    async def redemption_terms_conditions(self):
        embed = await clash_embed(
            context=self.bot,
            title=f"**Redemption Terms & Conditions**",
            message=f"1. All redemptions cannot be reversed and are not exchangeable or refundable."
                + f"\n2. Redemptions **can** take up to 72 hours (3 days) to be fulfilled. Please be patient. Begging or pestering the staff will not expedite the process."
                + f"\n3. In the event where an item is commercially unavailable, we reserve the right to offer you equivalent alternatives." 
                + f"\n4. You are required to provide confirmation of item receipt. In the absence of valid confirmation, your redemption is assumed to be fulfilled."
                + f"\n5. We reserve the right to withhold any redemption without reason or explanation."
                + "\n\u200b",
            timestamp=pendulum.now()
            )
        return embed
    
    @commands.Cog.listener()
    async def on_assistant_cog_add(self,cog:commands.Cog):
        schemas = [
            {
                "name": "_assistant_get_member_balance",
                "description": "Gets a user's bank balance in the Guild Bank.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    },
                },
            {
                "name": "_assistant_get_store_redeemables",
                "description": "Returns all redeemable items in the Guild's Store, and their parameters.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    },
                },
            {
                "name": "_assistant_get_member_inventory",
                "description": "Gets a list of items in a user's inventory.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    },
                },
            {
                "name": "_assistant_redeem_nitro",
                "description": "Allows a user to redeem Discord Nitro if they have the associated item in their inventory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_id": {
                            "description": "The corresponding ID of the item to redeem. Use _assistant_get_member_inventory to get the ID. If a user has more than one eligible Nitro item, prompt the user which item they want to redeem. Item IDs are for internal use, so do not display IDs to the user.",
                            "type": "string",                            
                            },
                        },
                    "required": ["item_id"],
                    },
                },
            {
                "name": "_prompt_user_reward_account",
                "description": "Use this when you need to prompt a user to select one of their Clash of Clans Accounts to redeem an in-game item on. This filters to only accounts of Townhall Level 7 or higher.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "description": "The question or message to prompt the user with.",
                            "type": "string",
                            },
                        },
                    "required": ["message"],
                    },
                },            
            {
                "name": "_assistant_redeem_clashofclans",
                "description": "Allows a user to redeem a Gold Pass or Gems in Clash of Clans if they have the associated item in their inventory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_id": {
                            "description": "The corresponding ID of the item to redeem. Use _assistant_get_member_inventory to get the ID. If a user has more than one eligible item, prompt the user which item they want to redeem. Item IDs are for internal use, so do not display IDs to the user.",
                            "type": "string",
                            },
                        "redeem_tag": {
                            "description": "The Clash of Clans account to receive the Gold Pass or Gems on, identified by the Player Tag. If the user does not provide an account in their request, use _prompt_user_account to prompt them to select one of their linked Clash of Clans accounts. Only accounts of Townhall Level 7 or higher are eligible.",
                            "type": "string",
                            },
                        },
                    "required": ["item_id","redeem_tag"],
                    },
                }            
            ]
        await cog.register_functions(cog_name="Bank", schemas=schemas)
    
    async def _assistant_get_store_redeemables(self,guild:discord.Guild,*args,**kwargs) -> str:
        items = await ShopItem.get_by_guild(guild.id)

        redeemable_items = [i for i in items if i.type in ['cash'] and i.show_in_store]
        result_json = [i._assistant_json() for i in redeemable_items]
        
        return f"The following redeemable items are currently registered in {guild.name}'s Store: {result_json}."

    async def _assistant_get_member_balance(self,user:discord.Member,*args,**kwargs) -> str:
        bot_client.coc_main_log.info(f"Assistant: Bank: Get Member Balance: {user.id}")
        if not user:
            return "No user found."
        balance = await bank.get_balance(user)

        result_json = {
            'user': user.display_name,
            'balance': balance,
            'currency': await bank.get_currency_name(),
            }
        return f"Do not change the currency text, return it as provided in the result. {user.display_name}'s bank account: {result_json}."

    async def _assistant_get_member_inventory(self,user:discord.Member,*args,**kwargs) -> str:
        bot_client.coc_main_log.info(f"Assistant: Bank: Get Inventory: {user.id}")
        if not user:
            return "No user found."
        inventory = await UserInventory(user)
        return f"The user {user.name} (ID: {user.id}) has the following items in their inventory: {inventory._assistant_json()}."
    
    async def _assistant_redeem_nitro(self,guild:discord.Guild,channel:discord.TextChannel,user:discord.Member,item_id:str,*args,**kwargs) -> str:
        if not user:
            return "No user found."    
            
        if self.bot.user.id == 1031240380487831664 and getattr(guild,'id',0) != self.bank_guild.id:
            return f"To proceed with redemption, the user must start this conversation from The Assassins Guild server. They may join the Guild at this invite: https://discord.gg/hUSSsFneb2"
        
        item = await ShopItem.get_by_id(item_id)
        inventory = await UserInventory(user)
        if not inventory.has_item(item):
            return f"The user {user.name} (ID: {user.id}) does not have the item {item.name} in their inventory."

        embed = await self.redemption_terms_conditions()
        embed.add_field(
            name="**For Discord Nitro Redemptions**",
            value=f"1. Nitro redemptions are sent via Discord DMs. Keep your DMs open to receive your redemption."
                + f"\n2. You **must** accept the Discord Nitro gift before expiration. We are not obligated to re-send any expired gifts."
                + f"\n3. In the event you are unable to use your Nitro Gift due to subscription conflicts, your Gift will be stored as Credit in your Discord account."
                + f"\n4. Discord Terms & Conditions are applicable.",
            inline=False
            )
        view = AssistantConfirmation(user)
        message = await channel.send(
            content=f"{user.mention}, please review and accept the following Terms and Conditions before proceeding with your redemption.",
            embed=embed,
            view=view
            )
        wait = await view.wait()
        await message.delete()
        if wait:
            return f"{user.display_name} did not respond."
        if not view.confirmation:
            return f"{user.display_name} cancelled the redemption."

        ticket = await RedemptionTicket.create(
            self,
            user_id=user.id,
            item_id=item_id
            )
        return f"The redemption ticket for {user.display_name} has been created: {getattr(ticket.channel,'id','No channel')}. To link to the user to the channel, wrap the channel ID as follows: <#channel_id>."

    async def _prompt_user_reward_account(self,channel:discord.TextChannel,user:discord.Member,message:str,*args,**kwargs) -> str:
        member = aMember(user.id)
        await member.load()
        
        fetch_all_accounts = await self.client.fetch_many_players(*member.account_tags)
        fetch_all_accounts.sort(key=lambda a: a.town_hall.level,reverse=True)

        eligible_accounts = [a for a in fetch_all_accounts if a.town_hall.level >= 7]

        if len(eligible_accounts) == 0:
            return f"The user {user.name} (ID: {user.id}) does not have any eligible linked accounts."
        
        if len(eligible_accounts) == 1:
            return f"The user selected the account: {eligible_accounts[0].overview_json()}."
        
        else:
            view = ClashAccountSelector(user,eligible_accounts)
            embed = await clash_embed(context=self.bot,message=message,timestamp=pendulum.now())
            m = await channel.send(
                content=user.mention,
                embed=embed,
                view=view
                )
            wait = await view.wait()
            await m.delete()
            if wait or not view.selected_account:
                return f"The user did not respond or cancelled process."
            
            select_account = await self.client.fetch_player(view.selected_account)
            return f"The user selected the account: {select_account.overview_json()}."

    async def _assistant_redeem_clashofclans(self,guild:discord.Guild,channel:discord.TextChannel,user:discord.Member,item_id:str,redeem_tag:str,*args,**kwargs) -> str:
        try:
            if not user:
                return "No user found."
            
            if self.bot.user.id == 1031240380487831664 and getattr(guild,'id',0) != self.bank_guild.id:
                return f"To proceed with redemption, the user must start this conversation from The Assassins Guild server. They may join the Guild at this invite: https://discord.gg/hUSSsFneb2"
            
            item = await ShopItem.get_by_id(item_id)
            inventory = await UserInventory(user)
            if not inventory.has_item(item):
                return f"The user {user.name} (ID: {user.id}) does not have the item {item.name} in their inventory."
            
            redeem_account = await self.client.fetch_player(redeem_tag)
            if not redeem_account or redeem_account.town_hall.level < 7:
                return f"The account {redeem_tag} is not eligible for redemption. Accounts must be valid and of Townhall Level 7 or higher."
            
            embed = await self.redemption_terms_conditions()
            embed.add_field(
                name="**For Gold Pass or Gem Pack Redemptions**",
                value=f"1. We use **[Codashop](https://www.codashop.com)** to purchase redemptions. This is a 3rd party licensed by Supercell. If you are not comfortable with this, please do not proceed."
                    + f"\n2. Your Clash of Clans account must be linked to a valid Supercell ID."
                    + f"\n3. The receipt of purchase serves as confirmation of redemption, regardless of whether you have received the item in-game."
                    + f"\n4. The following Terms & Conditions are applicable: Supercell, Codashop, Discord.",
                inline=False
                )
            
            view = AssistantConfirmation(user)
            message = await channel.send(
                content=f"{user.mention}, please review and accept the following Terms and Conditions before proceeding with your redemption.",
                embed=embed,
                view=view
                )
            wait = await view.wait()
            await message.delete()
            if wait:
                return f"{user.display_name} did not respond."
            if not view.confirmation:
                return f"{user.display_name} cancelled the redemption."
            
            ticket = await RedemptionTicket.create(
                self,
                user_id=user.id,
                item_id=item_id,
                goldpass_tag=redeem_tag
                )
            return f"The redemption ticket for {user.display_name} on {redeem_account.name} has been created: {getattr(ticket.channel,'id','No channel')}. To link to the user to the channel, wrap the channel ID as follows: <#channel_id>."
        
        except Exception as e:
            bot_client.coc_main_log.exception(f"Assistant: Bank: Redeem Gold Pass")
            return f"An error occurred: {e}"
    
    @commands.Cog.listener("on_guild_channel_create")
    async def new_redemption_ticket_listener(self,channel:discord.TextChannel):
        redemption_id = None
        await asyncio.sleep(1)
        
        async for message in channel.history(limit=1,oldest_first=True):
            for embed in message.embeds:
                if embed.footer.text == "Redemption ID":                    
                    redemption_id = embed.description
                    break

        if not redemption_id:
            return        
        ticket = await RedemptionTicket.get_by_id(redemption_id)
        await ticket.update_channel(channel.id)
        embed = await ticket.get_embed()
        await channel.send(embed=embed)
    
    @commands.Cog.listener("on_message")
    async def redemption_ticket_claim_listener(self,message:discord.Message):
        if not message.guild:
            return        
        if message.guild.id != self.bank_guild.id:
            return        
        if message.author.id != 722196398635745312:
            return
        
        redemption_id = None
        async for m in message.channel.history(limit=1,oldest_first=True):
            for embed in m.embeds:
                if embed.footer.text == "Redemption ID":                    
                    redemption_id = embed.description
                    break
        if not redemption_id:
            return
        
        ticket = await RedemptionTicket.get_by_id(redemption_id)
        inventory = await UserInventory(message.guild.get_member(ticket.user_id))
        item = await ShopItem.get_by_id(ticket.item_id)
        
        if message.content.startswith("Redemption marked as fulfilled by"):
            if len(message.mentions) == 0:
                return await message.reply(f"Could not find a completing user. Please try again.")

            redemption_user = message.mentions[0].id                
            await ticket.complete_redemption(redemption_user)
            await inventory.remove_item_from_inventory(item)
        
        if message.content.startswith("Fulfillment reversed by"):
            await ticket.reverse_redemption()
            await inventory.add_item_to_inventory(item)

    ############################################################
    #####
    ##### REWARD DISTRIBUTION
    #####
    ############################################################
    async def month_end_sweep(self):
        async with self.current_account._master_lock:
            current_balance = self.current_account.balance
            if current_balance > 0:
                await self.sweep_account.deposit(
                    amount=current_balance * 0.9,
                    user_id=self.bot.user.id,
                    comment="EOS from Current Account."
                    )
                await self.reserve_account.deposit(
                    amount=current_balance * 0.1,
                    user_id=self.bot.user.id,
                    comment="EOS from Current Account."
                    )
                await self.current_account.admin_adjust(
                    amount=current_balance * -1,
                    user_id=self.bot.user.id,
                    comment="EOS to Sweep & Reserve Accounts."
                    )
        
        alliance_clans = await self.client.get_alliance_clans()
            
        sweep_balance = self.sweep_account.balance
        distribution_per_clan = (sweep_balance * 0.7) / len(alliance_clans)

        a_iter = AsyncIter(alliance_clans)
        async for clan in a_iter:
            clan_account = await ClanAccount(clan)
            clan_balance = clan_account.balance

            if clan_balance > 0:
                await clan_account.withdraw(
                    amount=round(clan_balance * 0.1),
                    user_id=self.bot.user.id,
                    comment=f"EOS to Reserve Account."
                    )                
                await self.reserve_account.deposit(
                    amount=round(clan_balance * 0.1),
                    user_id=self.bot.user.id,
                    comment=f"EOS from {clan.tag} {clan.name}."
                    )
                
            if distribution_per_clan > 0:
                distribution = round(distribution_per_clan * (clan.alliance_member_count / 50))

                await clan_account.deposit(
                    amount=distribution,
                    user_id=self.bot.user.id,
                    comment=f"EOS from Sweep Account."
                    )
                await self.sweep_account.withdraw(
                    amount=distribution,
                    user_id=self.bot.user.id,
                    comment=f"EOS to {clan.tag} {clan.name}."
                    )
        
        owner = self.bot.get_user(self.bot.owner_ids[0])
        owner_bal = await bank.get_balance(owner)

        if owner_bal > 0:
            await bank.withdraw_credits(owner,owner_bal)
            as_clan = await self.client.from_clan_abbreviation("AS")
            clan_account = await ClanAccount(as_clan)
            await clan_account.deposit(
                amount=owner_bal,
                user_id=self.bot.user.id,
                comment="EOS from Owner."
                )
                
        query_members = await bot_client.coc_db.db__player.find({'is_member':True}).to_list(length=None)
        await self.current_account.deposit(
            amount=round(len(query_members) * 25000),
            user_id=self.bot.user.id,
            comment=f"EOS new funds: {len(query_members)} members."
            )
    
    async def apply_bank_taxes(self):
        async def _user_tax(user_id:int):
            user = self.bot.get_user(user_id)
            if user.bot:
                current_balance = await bank.get_balance(user)
                await self.reserve_account.deposit(
                    amount=current_balance,
                    user_id=self.bot.user.id,
                    comment=f"Reset bot account."
                    )
                return await bank.set_balance(user,0)                

            current_balance = await bank.get_balance(user)
            additional_tax = 0
            if current_balance <= 10000:
                tax_pct = 0
            elif current_balance <= 25000:
                tax_pct = 0.01
            elif current_balance <= 50000:
                tax_pct = 0.03
            elif current_balance <= 100000:
                tax_pct = 0.08
            elif current_balance <= 200000:
                tax_pct = 0.15
            else:
                tax_pct = 0.25
                additional_tax = (current_balance - 200000) // 10000 * 0.01 * 10000

            total_tax = round((current_balance * tax_pct) + additional_tax)
            if total_tax > 0:
                await bank.withdraw_credits(user,total_tax)
                await self.reserve_account.deposit(
                    amount=total_tax,
                    user_id=self.bot.user.id,
                    comment=f"Taxes for {user.id}."
                    )                    
                await self._send_log(
                    user=user,
                    done_by=self.bot.user,
                    amount=total_tax * -1,
                    comment=f"End of Season Taxes."
                    )

        await bank.bank_prune(self.bot)
        all_accounts = await bank.get_leaderboard()
        await asyncio.gather(*(_user_tax(id) for id,account in all_accounts))    
    
    ############################################################
    #####
    ##### PLAYER PROGRESS REWARDS
    #####
    ############################################################
    async def _compute_multiplier(self,player:aPlayer) -> float:
        multi = 0.0
        if not player.discord_user:
            return 0
        member = aMember(player.discord_user)
        reward_tag = await member._get_reward_account_tag()
        
        guild_user = self.bank_guild.get_member(player.discord_user)
        
        if guild_user and self.bank_pass_role in guild_user.roles:
            if reward_tag == player.tag:
                multi = 1.5
            elif player.is_member:
                multi = 1.0
            else:
                multi = 0.4
        else:            
            if reward_tag == player.tag:
                multi = 1.0
            elif player.is_member:
                multi = 0.4
            else:
                multi = 0.2
        return multi
    
    async def member_th_progress_reward(self,old_player:aPlayer,new_player:aPlayer):
        if not self.use_rewards:
            return
        if not new_player.is_member:
            return
        member = self.bot.get_user(new_player.discord_user)
        if not member:
            return
        
        if old_player.town_hall.level == new_player.town_hall.level:
            return
        
        if new_player.hero_rushed_pct > 0:
            reward = 0
        elif new_player.town_hall.level <= 9:
            reward = 10000
        elif new_player.town_hall.level <= 13:
            reward = 15000
        else:
            reward = 20000
        
        if reward > 0:
            multi = await self._compute_multiplier(new_player)
            new_reward = round(reward * multi)

            await bank.deposit_credits(member,new_reward)
            await self.current_account.withdraw(
                amount = new_reward,
                user_id = self.bot.user.id,
                comment = f"Townhall Bonus (x{multi})for {new_player.name} ({new_player.tag}): TH{old_player.town_hall_level} to TH{new_player.town_hall.level}."
                )
            await self._send_log(
                user=member,
                done_by=self.bot.user,
                amount=new_reward,
                comment=f"Townhall Bonus (x{multi}) for {new_player.name} ({new_player.tag}): TH{old_player.town_hall_level} to TH{new_player.town_hall.level}."
                )
    
    async def member_hero_upgrade_reward(self,old_player:aPlayer,new_player:aPlayer):
        async def _hero_reward(hero:str):
            old_hero = old_player.get_hero(hero)
            new_hero = new_player.get_hero(hero)
            upgrades = range(getattr(old_hero,'level',0)+1,new_hero.level+1)
            async for u in AsyncIter(upgrades):
                if u > new_hero.min_level and new_rew > 0:
                    await bank.deposit_credits(member,new_rew)
                    await self.current_account.withdraw(
                        amount = new_rew,
                        user_id = self.bot.user.id,
                        comment = f"Hero Bonus (x{multi}) for {new_player.name} ({new_player.tag}): {new_hero.name} upgraded to {new_hero.level}."
                        )
                    await self._send_log(
                        user=member,
                        done_by=self.bot.user,
                        amount=new_rew,
                        comment=f"Hero Bonus (x{multi}) for {new_player.name} ({new_player.tag}): {new_hero.name} upgraded to {new_hero.level}."
                        )
                    
        if not self.use_rewards:
            return
        if not new_player.is_member:
            return
        member = self.bot.get_user(new_player.discord_user)
        if not member:
            return        
        if new_player.hero_strength == old_player.hero_strength:
            return
        
        rew = 1000
        multi = await self._compute_multiplier(new_player)
        new_rew = round(rew * multi)
        heroes = HeroAvailability.return_all_unlocked(new_player.town_hall.level)
        await asyncio.gather(*(_hero_reward(hero) for hero in heroes))
    
    async def capital_contribution_rewards(self,old_player:aPlayer,new_player:aPlayer,achievement:coc.Achievement):
        if achievement.name == "Most Valuable Clanmate":
            if not self.use_rewards:
                return
            member = self.bot.get_user(new_player.discord_user)
            if not member:
                return
            
            target_clan = new_player.clan if new_player.clan else old_player.clan

            if not target_clan:
                return
            if not target_clan.is_alliance_clan:
                return
            
            old_ach = old_player.get_achievement(achievement.name)
            new_ach = new_player.get_achievement(achievement.name)            
            increment = new_ach.value - old_ach.value

            event_start = pendulum.datetime(2023,12,22,7,0,0)
            event_end = pendulum.datetime(2023,12,25,7,0,0)

            default_multiplier = await self._compute_multiplier(new_player)
            if event_start <= pendulum.now() <= event_end:
                mult = 2 * default_multiplier if target_clan.tag == "#2L90QPRL9" else default_multiplier
            else:
                mult = default_multiplier
            
            total_reward = round((10 * (increment // 1000)) * mult)

            if total_reward > 0:                    
                await bank.deposit_credits(member,total_reward * mult)
                await self.current_account.withdraw(
                    amount = total_reward,
                    user_id = self.bot.user.id,
                    comment = f"Capital Gold Bonus (x{mult}) for {new_player.name} ({new_player.tag}): {increment}"
                    )
                await self._send_log(
                    user=member,
                    done_by=self.bot.user,
                    amount=total_reward,
                    comment=f"Capital Gold Bonus (x{mult}) for {new_player.name} ({new_player.tag}): Donated {increment:,} Gold to {target_clan.name}."
                    )
    
    ############################################################
    #####
    ##### WAR REWARDS
    #####
    ############################################################
    async def clan_war_ended_rewards(self,clan:aClan,war:aClanWar):

        async def war_bank_rewards(player:aWarPlayer):
            f_player = await self.client.fetch_player(player.tag)
            member = self.bot.get_user(f_player.discord_user)
            if not member:
                return
            
            if player.unused_attacks > 0:
                balance = await bank.get_balance(member)
                penalty = round(min(balance,max(100,0.05 * balance) * player.unused_attacks))
                await bank.withdraw_credits(member,penalty)
                await self.current_account.deposit(
                    amount = penalty,
                    user_id = self.bot.user.id,
                    comment = f"Clan War Penalty for {player.name} ({player.tag})."
                    )
                await self._send_log(
                    user=member,
                    done_by=self.bot.user,
                    amount=(penalty * -1),
                    comment=f"Clan War Penalty for {player.name} ({player.tag})."
                    )
            
            multiplier = await self._compute_multiplier(f_player)
            participation = 50
            performance = (50 * player.star_count) + (300 * len([a for a in player.attacks if a.is_triple]))
            result = 100 if player.clan.result == WarResult.WON else 0

            total_reward = round((participation + performance + result) * multiplier)
            if total_reward > 0:
                await bank.deposit_credits(member,total_reward)
                await self.current_account.withdraw(
                    amount = total_reward,
                    user_id = self.bot.user.id,
                    comment = f"Clan War Reward (x{multiplier}) for {player.name} ({player.tag})."
                    )
                await self._send_log(
                    user=member,
                    done_by=self.bot.user,
                    amount=total_reward,
                    comment=f"Clan War Reward (x{multiplier}) for {player.name} ({player.tag})."
                    )
        
        if not self.use_rewards:
            return
        
        if clan.is_alliance_clan and war.type == ClanWarType.RANDOM:
            war_clan = war.get_clan(clan.tag)
            if not war_clan:
                return
            
            a_iter = AsyncIter(war_clan.members)            
            tasks = [war_bank_rewards(player) async for player in a_iter]
            await bounded_gather(*tasks,return_exceptions=True,limit=1)
    
    async def raid_weekend_ended_rewards(self,clan:aClan,raid:aRaidWeekend):
        async def raid_bank_rewards(player:aRaidMember):
            f_player = await self.client.fetch_player(player.tag)
            member = self.bot.get_user(f_player.discord_user)
            if not member:
                return
            
            if player.attack_count < 6:
                unused_attacks = 6 - player.attack_count
                balance = await bank.get_balance(member)
                penalty = round(min(balance,max(50,0.02 * balance) * unused_attacks))
                await bank.withdraw_credits(member,penalty)
                await self.current_account.deposit(
                    amount = penalty,
                    user_id = self.bot.user.id,
                    comment = f"Raid Weekend Penalty for {player.name} ({player.tag})."
                    )
                await self._send_log(
                    user=member,
                    done_by=self.bot.user,
                    amount=(penalty * -1),
                    comment=f"Raid Weekend Penalty for {player.name} ({player.tag})."
                    )
            
            multiplier = await self._compute_multiplier(f_player)

            total_reward = round((20 * (sum([a.new_destruction for a in player.attacks]) // 5)) * multiplier)
            if total_reward > 0:
                await bank.deposit_credits(member,total_reward)
                await self.current_account.withdraw(
                    amount = total_reward,
                    user_id = self.bot.user.id,
                    comment = f"Raid Weekend Reward (x{multiplier}) for {player.name} ({player.tag})."
                    )
                await self._send_log(
                    user=member,
                    done_by=self.bot.user,
                    amount=total_reward,
                    comment=f"Raid Weekend Reward (x{multiplier}) for {player.name} ({player.tag})."
                    )

        if not self.use_rewards:
            return        
        if clan.is_alliance_clan:
            a_iter = AsyncIter(raid.members)
            tasks = [raid_bank_rewards(player) async for player in a_iter]
            await bounded_gather(*tasks,return_exceptions=True,limit=1)
    
    ############################################################
    #####
    ##### EOS REWARDS
    #####
    ############################################################
    async def member_legend_rewards(self):        
        async def _distribute_rewards(player:aPlayer):
            if not player.is_member:
                return
            if not player.legend_statistics:
                return
            if not player.legend_statistics.previous_season:
                return

            member = self.bot.get_user(player.discord_user)
            if not member:
                return
            
            multiplier = await self._compute_multiplier(player)
            
            trophies = player.legend_statistics.previous_season.trophies - 5000
            reward = round((trophies * reward_per_trophy) * multiplier)
            if reward > 0:
                await bank.deposit_credits(member,reward)
                await self.current_account.withdraw(
                    amount=reward,
                    user_id=self.bot.user.id,
                    comment=f"Legend Rewards (x{multiplier}) for {player.name} {player.tag}. Trophies: {trophies}."
                    )
                await self._send_log(
                    user=member,
                    done_by=self.bot.user,
                    amount=reward,
                    comment=f"Legend Rewards (x{multiplier}) for {player.name} {player.tag}. Trophies: {trophies:,}."
                    )
        
        if not self.use_rewards:
            return
        
        reward_per_trophy = 20
        query = bot_client.coc_db.db__player.find({'is_member':True},{'_id':1})

        member_tags = [q['_id'] async for q in query]
        members = await self.client.fetch_many_players(*member_tags)
        
        a_iter = AsyncIter(members)
        tasks = [_distribute_rewards(player) async for player in a_iter]
        await bounded_gather(*tasks,return_exceptions=True,limit=1)
    
    async def member_clan_games_rewards(self):
        async def _distribute_rewards(player:aPlayer):
            if not player.is_member:
                return          
            member = self.bot.get_user(player.discord_user)
            if not member:
                return

            player_season = await player.get_season_stats(bot_client.current_season)
            if player_season.clangames.clan_tag == player_season.home_clan_tag:

                multiplier = await self._compute_multiplier(player)
                reward = round((4000 * (player_season.clangames.score / 4000)) * multiplier)

                if reward > 0:
                    await bank.deposit_credits(member,reward)
                    await self.current_account.withdraw(
                        amount=reward,
                        user_id=self.bot.user.id,
                        comment=f"Clan Games Rewards (x{multiplier}) for {player.name} {player.tag}. Score: {player_season.clangames.score}."
                        )
                    await self._send_log(
                        user=member,
                        done_by=self.bot.user,
                        amount=reward,
                        comment=f"Clan Games Rewards (x{multiplier}) for {player.name} {player.tag}. Score: {player_season.clangames.score}."
                        )
        
        if not self.use_rewards:
            return
        
        query = bot_client.coc_db.db__player.find({'is_member':True},{'_id':1})
        member_tags = [q['_id'] async for q in query]
        members = await self.client.fetch_many_players(*member_tags)

        a_iter = AsyncIter(members)
        tasks = [_distribute_rewards(player) async for player in a_iter]
        await bounded_gather(*tasks,return_exceptions=True,limit=1)
    
    ############################################################
    ############################################################
    ##### SUBSCRIPTION EXPIRY
    ############################################################
    ############################################################
    @tasks.loop(seconds=1.0)
    async def send_bank_logs_batch(self):
        if self._log_task_lock.locked():
            return
        
        embeds = []
                
        async with self._log_task_lock, self._log_lock:
            if not self.log_channel:
                return
            
            currency = await bank.get_currency_name()
            while True:
                size = self._log_queue.qsize()
                if size == 0:
                    break
                
                log_entry = await self._log_queue.get()
                log_user = self.bot.get_user(log_entry['user_id'])
                done_by = self.bot.get_user(log_entry['done_by_id'])
            
                embed = await clash_embed(
                    context=self.bot,
                    message=f"`{log_user.id}`"
                        + f"**{log_user.mention}\u3000" + ("+" if log_entry['amount'] >= 0 else "-") + f"{abs(log_entry['amount']):,} {currency}**",
                    success=True if log_entry['amount'] >= 0 else False,
                    timestamp=pendulum.from_timestamp(log_entry['timestamp'])
                    )
                embed.add_field(name="**Reason**",value=log_entry['comment'],inline=True)
                embed.add_field(name="**By**",value=f"{done_by.mention}" + f"`{done_by.id}`",inline=True)
                embed.set_author(name=log_user.display_name,icon_url=log_user.display_avatar.url)
                embeds.append(embed)

                if len(embeds) > 10:
                    break
                    
            if len(embeds) > 0:
                await self.log_channel.send(embeds=embeds)

    @tasks.loop(seconds=1.0)
    async def subscription_item_expiry(self):
        if self._subscription_lock.locked():
            return
        
        async with self._subscription_lock:
            items = await ShopItem.get_subscription_items()

            i_iter = AsyncIter(items)
            async for item in i_iter:
                try:
                    if not item.guild:
                        continue

                    if item.type == 'role' and item.assigns_role and item.assigns_role.is_assignable():
                        async with item.lock:
                            if len(item.assigns_role.members) > 0:
                                all_role_items = await ShopItem.get_by_role_assigned(item.guild.id,item.assigns_role.id)

                                all_subscribed_users = []
                                item_iter = AsyncIter(all_role_items)
                                async for i in item_iter:
                                    all_subscribed_users.extend(list(i.subscription_log.keys()))
                                
                                m_iter = AsyncIter(item.assigns_role.members)
                                async for member in m_iter:
                                    if str(member.id) not in all_subscribed_users:
                                        await member.remove_roles(
                                            item.assigns_role,
                                            reason="User does not have a valid subscription."
                                            )
                                        
                    u_iter = AsyncIter(list(item.subscription_log.items()))
                    async for user_id,timestamp in u_iter:
                        try:
                            user = item.guild.get_member(int(user_id))
                            if not user:
                                continue

                            if item.type == 'role' and item.assigns_role.id not in [r.id for r in user.roles]:
                                await item.expire_item(user)

                            expiry_time = await item.compute_user_expiry(user.id)

                            if expiry_time and pendulum.now() >= expiry_time:
                                if item.type == 'role' and item.assigns_role and item.assigns_role.is_assignable():
                                    if item.assigns_role in user.roles:
                                        await user.remove_roles(
                                            item.assigns_role,
                                            reason="Role Item expired."
                                            )
                                else:
                                    inventory = await UserInventory(user)
                                    await inventory.remove_item_from_inventory(item)
                                
                                await item.expire_item(user)
                                try:
                                    await user.send(f"Your {item.name} has expired.")
                                except:
                                    pass
                        
                        except Exception as exc:
                            await self.bot.send_to_owners(f"An error while expiring Shop Items for User {user_id}. Check logs for details."
                                + f"```{exc}```")
                            bot_client.coc_main_log.exception(
                                f"Error expiring Shop Item {item.id} {item.name} for {user_id}."
                                )
                
                except Exception as exc:
                    await self.bot.send_to_owners(f"An error while expiring Shop Items. Check logs for details."
                        + f"```{exc}```")
                    bot_client.coc_main_log.exception(
                        f"Error expiring Shop Item {item.id} {item.name}."
                        )

    ############################################################
    ############################################################
    #####
    ##### COMMAND DIRECTORY
    ##### - balance
    ##### - payday
    ##### - bank
    ##### - bank / globalbal
    ##### - bank / togglerewards
    ##### - bank / leaderboard
    ##### - bank / transactions
    ##### - bank / deposit
    ##### - bank / withdraw
    ##### - bank / reward
    ##### - inventory
    ##### - store
    ##### - gift
    ##### - manage-store
    ##### - shop-items / distribute
    ##### - shop-items / redeem
    ##### - shop-items / delete
    ##### - shop-items / restock
    #####    
    ############################################################
    ############################################################    
    
    ##################################################
    ### PARENT COMMAND GROUPS
    ##################################################
    @commands.group(name="bank")
    @commands.guild_only()
    async def command_group_bank(self,ctx):
        """
        Group for Bank-related Commands.

        **This is a command group. To use the sub-commands below, follow the syntax: `$bank [sub-command]`.**
        """
        if not ctx.invoked_subcommand:
            pass

    app_command_group_bank = app_commands.Group(
        name="bank",
        description="Group for Bank Commands. Equivalent to [p]bank.",
        guild_only=True
        )
    
    ##################################################
    ### BALANCE
    ##################################################
    async def helper_show_balance(self,
        context:Union[discord.Interaction,commands.Context],
        clan:Optional[aClan]=None):

        currency = await bank.get_currency_name()
        user = context.user if isinstance(context,discord.Interaction) else context.author

        if clan:
            check_permissions = True if (is_bank_admin(context) or user.id == clan.leader or user.id in clan.coleaders) else False
            if not check_permissions:
                clan = None
        
        if clan:
            account = await ClanAccount(clan)
            embed = await clash_embed(
                context=context,
                message=f"**{clan.title}** has **{account.balance:,} {currency}**.",
                timestamp=pendulum.now()
                )
            return embed       

        member = await aMember(user.id,context.guild.id)
        reward_tag = await member._get_reward_account_tag()       
        reward_account = await self.client.fetch_player(reward_tag) if reward_tag else None
        primary_multiplier = (await self._compute_multiplier(reward_account) * 100)

        guild_member = self.bank_guild.get_member(user.id)
        pass_active = True if self.bank_pass_role and self.bank_pass_role in guild_member.roles else False

        embed = await clash_embed(
            context=context,
            message=f"You have **{await bank.get_balance(member.discord_member):,} {currency}** (Global Rank: #{await bank.get_leaderboard_position(member.discord_member)}).",
            timestamp=pendulum.now()
            )
        
        if context.guild.id == self.bank_guild.id:
            embed.description += "\nNext payday: "
            embed.description += (f"<t:{member.last_payday.add(days=1).int_timestamp}:R>" if member.last_payday and member.last_payday.add(days=1) > pendulum.now() else "Now! Use `payday` to claim your credits!")
        
        embed.description += "\n\u200b"
        
        embed.add_field(
            name="__Reward Multipliers__",
            value=(f"{EmojisUI.BOOST} Rewards Boosted with Bank Pass.\n\n") if pass_active else "*Boost your rewards with a Bank Pass! Get up to 50% more rewards.*\n"
                + (f"- **{reward_account.town_hall.emoji} {reward_account.name}**: " + (f"{int(primary_multiplier)}%\n" if pass_active else f"{int(primary_multiplier)}%\n") if reward_account else "")
                + f"- **Member Accounts**: " + ("100%\n" if pass_active else "40%\n")
                + f"- **Non-Member Accounts**: " + ("40%\n" if pass_active else "20%\n")
                + f"\nChange your primary account with `/bank primary`.",
            inline=True
            )
        return embed
    
    @commands.command(name="balance",aliases=['bal'])
    @commands.guild_only()
    async def command_bank_balance(self,ctx:commands.Context,clan_abbreviation:Optional[str]=None):
        """
        Display your current Bank Balance (or Clan's balance).

        Clan balances are only usable by Clan Leaders and Co-Leaders.
        """
        
        if clan_abbreviation:
            clan = await self.client.from_clan_abbreviation(clan_abbreviation)
            embed = await self.helper_show_balance(ctx,clan)
        else:
            embed = await self.helper_show_balance(ctx)

        await ctx.reply(embed=embed)
    
    @app_commands.command(name="balance",
        description="Display your current Bank Balance.")
    @app_commands.guild_only()
    @app_commands.autocomplete(clan=autocomplete_clans_coleader)
    @app_commands.describe(
        user="Select a User to view balances for. Only usable by Bank Admins.",
        clan="Select a Clan to view balances for. Only usable by Clan Leaders and Co-Leaders.")
    async def app_command_bank_balance(self,interaction:discord.Interaction,user:Optional[discord.Member]=None,clan:Optional[str]=None):        
        
        await interaction.response.defer(ephemeral=True)

        if clan:
            s_clan = await self.client.fetch_clan(clan)
            embed = await self.helper_show_balance(interaction,s_clan)

        elif user:
            if not is_bank_admin(interaction):
                return await interaction.followup.send("You do not have permission to view other users' balances.")
            
            member = await aMember(user.id,interaction.guild.id)
            embed = await clash_embed(
                context=interaction,
                message=f"{user.mention} has **{await bank.get_balance(member.discord_member):,} {await bank.get_currency_name()}** (Global Rank: #{await bank.get_leaderboard_position(member.discord_member)}).",
                timestamp=pendulum.now()
                )
        else:
            embed = await self.helper_show_balance(interaction)
        await interaction.edit_original_response(embed=embed)        
    
    ##################################################
    ### PAYDAY
    ##################################################
    async def helper_payday(self,context:Union[discord.Interaction,commands.Context]):
        currency = await bank.get_currency_name()
        user_id = context.user.id if isinstance(context,discord.Interaction) else context.author.id
        member = await aMember(user_id,1132581106571550831)

        is_booster = True if getattr(member.discord_member,'premium_since',None) else False

        if member.last_payday:
            if member.last_payday.add(days=1) > pendulum.now():
                embed = await clash_embed(
                    context=context,
                    message=f"You can claim your next payday <t:{member.last_payday.add(days=1).int_timestamp}:R>.",
                    success=False,
                    timestamp=pendulum.now()
                    )        
                return embed        
            
        try:
            mee6user = await Mee6Rank._get_player(
                bot_client.bot.get_cog("Mee6Rank"),
                member.discord_member,
                get_avatar=False
                )
        except:
            mee6user = None

        basic_payout = 50
        xp_bonus = 10 * (mee6user.level // 10 if mee6user else 0)
        boost_bonus = 1000 if is_booster else 0

        total_payout = basic_payout + xp_bonus + boost_bonus
        await bank.deposit_credits(member.discord_member,total_payout)
        await member.set_last_payday(pendulum.now())

        embed = await clash_embed(
            context=context,
            message=f"Here's some money, {member.mention}! You received:"
                + f"\n\nBase Payout: {basic_payout} {currency}"
                + f"\nXP Bonus: {xp_bonus:,} {currency}"
                + f"\nNitro Bonus: {boost_bonus:,} {currency}"
                + f"\n\nTotal: {total_payout:,} {currency}. You now have: {await bank.get_balance(member.discord_member):,} {currency}.",
            success=True,
            timestamp=pendulum.now()
            )        
        return embed

    @commands.command(name="debugitem")
    async def command_debug(self,ctx:commands.Context):
        items = await ShopItem.get_by_guild(ctx.guild.id)
        for item in items:
            await ctx.reply(f"{item.name} ({item.id}) {item.guild_id}")
    
    @commands.command(name="payday")
    @commands.guild_only()
    @commands.check(is_payday_server)
    async def command_payday(self,ctx:commands.Context):
        """
        Payday!

        Receive a set amount of money every 24 hours.
        """
        embed = await self.helper_payday(ctx)
        await ctx.reply(embed=embed)

    @app_commands.command(name="payday",
        description="Receive a set amount of money every 24 hours.")
    @app_commands.guild_only()
    @app_commands.check(is_payday_server)
    async def app_command_payday(self,interaction:discord.Interaction):

        await interaction.response.defer()        
        embed = await self.helper_payday(interaction)
        await interaction.followup.send(embed=embed)         
    
    ##################################################
    ### BANK / TOGGLEREWARDS
    ##################################################
    @command_group_bank.command(name="runtaxes")
    @commands.guild_only()
    @commands.is_owner()
    async def subcommand_bank_run_month_end_taxes(self,ctx:commands.Context):
        """
        Manually run the Month-End Tax Calculation.
        """
        msg = await ctx.reply("Running Month-End User Tax...")
        await self.apply_bank_taxes()
        await msg.edit(content="Month-End Tax Complete.")

    @command_group_bank.command(name="runsweep")
    @commands.guild_only()
    @commands.is_owner()
    async def subcommand_bank_run_month_end_sweep(self,ctx:commands.Context):
        """
        Manually run the Month-End Sweep.
        """
        msg = await ctx.reply("Running Month-End Sweep...")
        await self.month_end_sweep()
        await msg.edit(content="Month-End Sweep Complete.")

    @command_group_bank.command(name="togglerewards")
    @commands.guild_only()
    @commands.is_owner()
    async def subcommand_bank_toggle_rewards(self,ctx:commands.Context):
        """
        Enable or Disable Currency Rewards.
        """

        self.use_rewards = not self.use_rewards
        await self.config.use_rewards.set(self.use_rewards)
        await ctx.reply(f"Currency Rewards have been {'Enabled' if self.use_rewards else 'Disabled'}.")
    
    @command_group_bank.command(name="logchannel")
    @commands.guild_only()
    @commands.is_owner()
    async def subcommand_bank_set_log_channel(self,ctx:commands.Context,channel_id:int):
        """
        Enable or Disable Currency Rewards.
        """
        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            return await ctx.reply("Channel not found.")
        self._log_channel = channel.id
        await self.config.log_channel.set(self._log_channel)
        await ctx.reply(f"Log Channel has been set to {channel.mention}.")
    
    ##################################################
    ### BANK / ADMIN
    ##################################################
    @command_group_bank.group(name="admin")
    @commands.guild_only()
    @commands.is_owner()
    async def subcommand_bank_admin(self,ctx:commands.Context):
        """
        [Owner-only] Commands to manage Bank Administrators.
        """
        if not ctx.invoked_subcommand:
            pass
    
    ##################################################
    ### BANK / ADMIN / SET
    ##################################################
    @subcommand_bank_admin.command(name="set")
    @commands.guild_only()
    @commands.is_owner()
    async def subcommand_bank_admin_set(self,ctx:commands.Context,member:discord.Member):
        """
        [Owner-only] Add a Bank Admin.
        """        
        if member.id in self.bank_admins:
            return await ctx.reply(f"{member.mention} is already a Bank Admin.")
        
        self.bank_admins.append(member.id)
        await ctx.reply(f"{member.mention} is now a Bank Admin.")

        admin_role = self.bank_guild.get_role(self._bank_admin_role)
        if admin_role and admin_role not in member.roles:
            await member.add_roles(admin_role)

        await self.config.admins.set(self.bank_admins)
        await ctx.tick()
    
    ##################################################
    ### BANK / ADMIN / DELETE
    ##################################################
    @subcommand_bank_admin.command(name="delete")
    @commands.guild_only()
    @commands.is_owner()
    async def subcommand_bank_admin_delete(self,ctx:commands.Context,member:discord.Member):
        """
        [Owner-only] Deletes a Bank Admin.
        """
        
        if member.id not in self.bank_admins:
            return await ctx.reply(f"{member.mention} is not a Bank Admin.")            
        
        self.bank_admins.remove(member.id)
        await ctx.reply(f"{member.mention} is no longer a Bank Admin.")

        admin_role = self.bank_guild.get_role(self._bank_admin_role)
        if admin_role and admin_role in member.roles:
            await member.remove_roles(admin_role)

        await self.config.admins.set(self.bank_admins)
        await ctx.tick()
    
    ##################################################
    ### BANK / ADMIN / SHOW
    ##################################################
    @subcommand_bank_admin.command(name="show")
    @commands.guild_only()
    @commands.is_owner()
    async def subcommand_bank_admin_show(self,ctx:commands.Context,member:discord.Member):
        """
        [Owner only] Lists the current Bank Admins.
        """

        embed = await clash_embed(
            context=ctx,
            title=f"{self.bot.user.name} Bank Admins",
            message="\n".join([ctx.guild.get_member(id).display_name for id in self.bank_admins]),
            timestamp=pendulum.now()
            )
        await ctx.reply(embed=embed)
    
    ##################################################
    ### BANK / ADMIN / PASS ROLE
    ##################################################
    @command_group_bank.command(name="passrole")
    @commands.guild_only()
    @commands.is_owner()
    async def subcommand_set_pass_role(self,ctx:commands.Context,role:discord.Role):
        """
        [Owner-only] Sets a role to use as the Bank Pass Role.
        """   
        if role.guild.id != self.bank_guild.id:
            return await ctx.reply("Role must be from the Bank Server.")
             
        self._bank_pass_role = role.id
        await self.config.bank_pass_role.set(self.bank_pass_role.id)
        await ctx.reply(f"Bank Pass Role set to {role.name} `{role.id}`.")

    ##################################################
    ### BANK / GLOBALBAL
    ##################################################
    async def helper_global_account_balances(self,context:Union[discord.Interaction,commands.Context]):
        currency = await bank.get_currency_name()
        leaderboard = await bank.get_leaderboard()
        if len(leaderboard) == 0:
            total_balance = 0
        else:
            total_balance = sum([account['balance'] for id,account in leaderboard])

        members = await bot_client.coc_db.db__player.find({'is_member':True},{'_id':1}).to_list(length=None)

        embed = await clash_embed(
            context=context,
            title=f"**Guild Bank Accounts**",
            message=f"`{'Current':<10}` {self.current_account.balance:,} {currency}"
                + f"\n`{'Sweep':<10}` {self.sweep_account.balance:,} {currency}"
                + f"\n`{'Reserve':<10}` {self.reserve_account.balance:,} {currency}"
                + f"\n`{'Total':<10}` {total_balance:,} {currency}"
                + f"\n\nNew Monthly Balance (est.): {len(members) * 25000:,} {currency}",
            timestamp=pendulum.now()
            )
        return embed

    @command_group_bank.command(name="globalbal",aliases=['gbal'])
    @commands.guild_only()
    @commands.check(is_bank_admin)
    async def subcommand_bank_global_balances(self,ctx:commands.Context):
        """
        [Bank Admin only] Display Global Account Balances.
        """
        embed = await self.helper_global_account_balances(ctx)
        await ctx.send(embed=embed)

    @app_command_group_bank.command(name="global-balances",
        description="[Bank Admin only] Display Global Account Balances.")
    @app_commands.guild_only()
    @app_commands.check(is_bank_admin)
    async def app_command_global_balances(self,interaction:discord.Interaction):
        
        await interaction.response.defer()
        embed = await self.helper_global_account_balances(interaction)        
        await interaction.followup.send(embed=embed)

    ##################################################
    ### BANK / LEADERBOARD
    ##################################################
    async def _helper_leaderboard(self,ctx:Union[commands.Context,discord.Interaction]):        
        pages = []
        leaderboard = await bank.get_leaderboard(guild=ctx.guild)

        if len(leaderboard) == 0:
            return None
        
        count = 0
        embed = None
        async for id,account in AsyncIter(leaderboard):
            count += 1
            if not embed:
                embed = await clash_embed(
                    context=ctx,
                    title=f"Bank Leaderboard: {ctx.guild.name}",
                    message=f"`{'':>3}{'':<3}{'WEALTH':>7}{'':<2}`",
                    timestamp=pendulum.now()
                    )
            member = ctx.guild.get_member(id)
            embed.description += f"\n`{count:>3}{'':<3}{account['balance']:>7,}{'':<2}`\u3000{member.display_name}"
            if (count >= 10 and count % 10 == 0) or count == len(leaderboard):
                pages.append(embed)
                embed = None
        
        return pages

    @command_group_bank.command(name="leaderboard",aliases=['lb'])
    @commands.guild_only()
    async def command_bank_leaderboard(self,ctx:commands.Context):
        """
        Displays the Economy Leaderboard for this Server.
        """        

        leaderboard = await self._helper_leaderboard(ctx)
        if not leaderboard:
            return await ctx.reply("Oops! There doesn't seem to be any accounts in the Bank.")
        
        if len(leaderboard) > 1:
            paginate = MenuPaginator(ctx,leaderboard)
            await paginate.start()
        else:
            await ctx.reply(embed=leaderboard[0])
    
    @app_command_group_bank.command(name="leaderboard",
        description="Displays the Economy Leaderboard for this Server.")
    async def app_command_bank_leaderboard(self,interaction:discord.Interaction):

        await interaction.response.defer()
        leaderboard = await self._helper_leaderboard(interaction)
        if not leaderboard:
            return await interaction.followup.send("Oops! There doesn't seem to be any accounts in the Bank.")
        
        if len(leaderboard) > 1:
            paginate = MenuPaginator(interaction,leaderboard)
            await paginate.start()
        else:
            await interaction.followup.send(embed=leaderboard[0])
    
    ##################################################
    ### BANK / PRIMARY ACCOUNT
    ##################################################
    @command_group_bank.command(name="primary")
    @commands.guild_only()
    async def command_bank_set_primary_account(self,ctx:commands.Context):
        """
        Set the Primary Account for your Bank Rewards.
        """        
        
        member = aMember(ctx.author.id,self.bank_guild.id)
        await member.load()
        
        all_accounts = await self.client.fetch_many_players(*member.account_tags)
        eligible_accounts = [a for a in all_accounts if a.is_member and a.town_hall.level >= 7]
        eligible_accounts.sort(key=lambda a: (a.town_hall.level,a.exp_level),reverse=True)

        if len(eligible_accounts) == 0:
            return await ctx.reply("You don't have any eligible accounts to set as your primary account.")
        
        embed = await clash_embed(
            context=ctx,
            message=f"**Choose from one of your accounts below as your Primary Rewards Account.**"
                + f"\n\nThis account:"
                + f"\n- Must be a registered member account."
                + f"\n- Must be at least Town Hall 7."
                + f"\n- Will receive Bank Rewards at a higher rate."
                + f"\n\nIf not set, or your primary account becomes ineligible, your highest TH account will be used. You can only change your primary account once every 7 days.",
            timestamp=pendulum.now()
            )        
        view = ClashAccountSelector(ctx.author,eligible_accounts)

        msg = await ctx.reply(embed=embed,view=view)
        wait = await view.wait()
        if wait:
            await msg.edit(content=f"Did not receive a response.",embed=None,view=None)
        
        if not view.selected_account:
            return await msg.edit(content="You did not select an account.",embed=None,view=None)
        
        sel_account = await self.client.fetch_player(view.selected_account)
        
        chk, timestamp = await member.set_reward_account(sel_account.tag)
        if not chk:
            ts = pendulum.from_timestamp(timestamp)
            nts = ts.add(days=7)
            return await msg.edit(content=f"You can only change your primary account once every 7 days. You can next change on/after: <t:{nts.int_timestamp}:f> ",embed=None,view=None)
        
        return await msg.edit(f"Your primary account has been set to **{sel_account.town_hall.emoji} {sel_account.name} {sel_account.tag}**.",embed=None,view=None)
    
    @app_command_group_bank.command(name="primary",
        description="Set the Primary Account for your Bank Rewards.")
    async def app_command_bank_set_primary_account(self,interaction:discord.Interaction):

        await interaction.response.defer()

        member = aMember(interaction.user.id,self.bank_guild.id)
        await member.load()
        
        all_accounts = await self.client.fetch_many_players(*member.account_tags)
        eligible_accounts = [a for a in all_accounts if a.is_member and a.town_hall.level >= 7]
        eligible_accounts.sort(key=lambda a: (a.town_hall.level,a.exp_level),reverse=True)

        if len(eligible_accounts) == 0:
            return await interaction.followup.send("You don't have any eligible accounts to set as your primary account.")
        
        embed = await clash_embed(
            context=interaction,
            message=f"**Choose from one of your accounts below as your Primary Rewards Account.**"
                + f"\n\nThis account:"
                + f"\n- Must be a registered member account."
                + f"\n- Must be at least Town Hall 7."
                + f"\n- Will receive Bank Rewards at a higher rate."
                + f"\n\nIf not set, or your primary account becomes ineligible, your highest TH account will be used. You can only change your primary account once every 7 days.",
            timestamp=pendulum.now()
            )        
        view = ClashAccountSelector(interaction.user,eligible_accounts)

        await interaction.followup.send(embed=embed,view=view)
        wait = await view.wait()
        if wait or not view.selected_account:
            return await interaction.edit_original_response(content=f"Did not receive a response.",embed=None,view=None)
        
        sel_account = await self.client.fetch_player(view.selected_account)
        chk, timestamp = await member.set_reward_account(sel_account.tag)
        if not chk:
            ts = pendulum.from_timestamp(timestamp)
            nts = ts.add(days=7)
            return await interaction.edit_original_response(content=f"You can only change your primary account once every 7 days. You can next change on/after: <t:{nts.int_timestamp}:f> ",embed=None,view=None)
        
        return await interaction.edit_original_response(content=f"Your primary account has been set to **{sel_account.town_hall.emoji} {sel_account.name} {sel_account.tag}**.",embed=None,view=None)
    
    ##################################################
    ### BANK / TRANSACTIONS
    ##################################################
    @command_group_bank.command(name="transactions")
    @commands.guild_only()
    @commands.check(is_coleader_or_bank_admin)
    async def subcommand_transaction_report(self,ctx:commands.Context,account_type_or_clan_abbreviation:str):
        """
        Export Bank Transactions to Excel.

        Only Guild and Clan Accounts have tracked transactions. Only transactions in the last 3 months are reported.
        """

        if account_type_or_clan_abbreviation in global_accounts:
            if not is_bank_admin(ctx):
                return await ctx.reply("You don't have permission to do this.")
            account = await MasterAccount(account_type_or_clan_abbreviation)
        
        else:
            clan = await self.client.from_clan_abbreviation(account_type_or_clan_abbreviation)
            check_permissions = True if (is_bank_admin(ctx) or ctx.author.id == clan.leader or ctx.author.id in clan.coleaders) else False

            if not check_permissions:
                return await ctx.reply("You don't have permission to do this.")
            account = await ClanAccount(clan)
        
        embed = await clash_embed(
            context=ctx,
            message=f"{EmojisUI.LOADING} Please wait..."
            )
        msg = await ctx.reply(embed=embed)

        transactions = await account.query_transactions()
        if len(transactions) == 0:
            embed = await clash_embed(
                context=ctx,
                message=f"There were no transactions to report."
                )
            return await msg.edit(embed=embed)
        else:
            embed = await clash_embed(
                context=ctx,
                message=f"{EmojisUI.LOADING} Found {len(transactions):,} transactions. Reporting only the most recent 10,000."
                )
            await msg.edit(embed=embed)
        
        rpfile = await account.export(transactions)           
        await msg.edit(
            content=f"{ctx.author.mention} Your report is available for download below.",
            embed=None,
            attachments=[discord.File(rpfile)]
            )

    @app_command_group_bank.command(name="transactions",
        description="Export Bank Transactions to Excel.")
    @app_commands.check(is_coleader_or_bank_admin)
    @app_commands.autocomplete(select_account=autocomplete_eligible_accounts)
    @app_commands.describe(
        select_account="Select an Account to view.")
    async def app_command_transaction_report(self,interaction:discord.Interaction,select_account:str):

        await interaction.response.defer()

        if select_account in global_accounts:
            if not is_bank_admin(interaction):
                return await interaction.followup.send("You don't have permission to do this.")
            account = await MasterAccount(select_account)
        
        else:
            try:
                clan = await self.client.fetch_clan(select_account)
            except InvalidAbbreviation as exc:
                return await interaction.followup.send(exc.message)
            check_permissions = True if (is_bank_admin(interaction) or interaction.user.id == clan.leader or interaction.user.id in clan.coleaders) else False

            if not check_permissions:
                return await interaction.followup.send("You don't have permission to do this.")
            account = await ClanAccount(clan)
        
        embed = await clash_embed(
            context=interaction,
            message=f"{EmojisUI.LOADING} Please wait..."
            )
        msg = await interaction.followup.send(embed=embed,wait=True)

        transactions = await account.query_transactions()
        if len(transactions) == 0:
            embed = await clash_embed(
                context=interaction,
                message=f"There were no transactions to report."
                )
            return await msg.edit(embed=embed)
        else:
            embed = await clash_embed(
                context=interaction,
                message=f"{EmojisUI.LOADING} Found {len(transactions):,} transactions. Reporting only the most recent 10,000."
                )
            await msg.edit(embed=embed)
        
        rpfile = await account.export(transactions)
        
        await msg.edit(
            content=f"{interaction.user.mention} Your report is available for download below.",
            embed=None,
            attachments=[discord.File(rpfile)]
            )
    
    ##################################################
    ### BALANCE
    ##################################################
    @command_group_bank.command(name="deposit")
    @commands.guild_only()
    @commands.check(is_bank_admin)
    async def subcommand_bank_deposit(self,ctx:commands.Context,amount:int,account_type:str,account_id:Union[int,str]):
        """
        Deposit Amount to a Bank Account.

        Valid account_type: `user`, `clan`, or `global`
        """
        if account_type not in ['user','clan','global']:
            return await ctx.reply("Invalid account type. Valid types are `user`, `clan`, or `global`.")
        
        if account_type == 'global':
            if account_id not in global_accounts:
                return await ctx.reply("Invalid account. Valid accounts are `current`, `sweep`, or `reserve`.")
            
            account = await MasterAccount(account_id)
            await account.deposit(
                amount=amount,
                user_id=ctx.author.id,
                comment=f"Manual Deposit."
                )
            
        if account_type == 'clan':
            clan = await self.client.from_clan_abbreviation(account_id)

            account = await ClanAccount(clan)
            await account.deposit(
                amount=amount,
                user_id=ctx.author.id,
                comment=f"Manual Withdrawal."
                )
        
        if account_type == 'user':
            user = ctx.bot.get_user(account_id)
            if not user:
                return await ctx.reply("Invalid User.")
            await bank.deposit_credits(user,amount)
            
        await ctx.tick()
    
    @app_command_group_bank.command(name="deposit",
        description="[Bank Admin only] Deposit Amount to a Bank Account.")
    @app_commands.check(is_bank_admin)
    @app_commands.autocomplete(select_account=autocomplete_eligible_accounts)
    @app_commands.describe(
        amount="The amount to deposit.",
        select_account="Select an Account to deposit.",
        user="Select a User to deposit to.",
        )
    async def app_command_bank_deposit(self,interaction:discord.Interaction,amount:int,select_account:Optional[str],user:Optional[discord.Member]=None):

        await interaction.response.defer(ephemeral=True)
        currency = await bank.get_currency_name()

        if select_account:
            if select_account in global_accounts:
                account = await MasterAccount(select_account)
                await account.deposit(
                    amount=amount,
                    user_id=interaction.user.id,
                    comment=f"Manual Deposit."
                    )
                return await interaction.followup.send(f"Deposited {amount:,} {currency} to {select_account.capitalize()} account.",ephemeral=True)
            
            else:
                try:
                    clan = await self.client.fetch_clan(select_account)
                except InvalidAbbreviation as exc:
                    return await interaction.followup.send(exc.message,ephemeral=True)
                else:
                    account = await ClanAccount(clan)
                    await account.deposit(
                        amount=amount,
                        user_id=interaction.user.id,
                        comment=f"Manual Deposit."
                        )
                    return await interaction.followup.send(f"Deposited {amount:,} {currency} to {clan.title}.",ephemeral=True)
        
        if user:
            await bank.deposit_credits(user,amount)
            return await interaction.followup.send(f"Deposited {amount:,} {currency} to {user.display_name}.",ephemeral=True)
                
    ##################################################
    ### WITHDRAW
    ##################################################    
    @command_group_bank.command(name="withdraw")
    @commands.guild_only()
    @commands.check(is_bank_admin)
    async def subcommand_bank_withdraw(self,ctx:commands.Context,amount:int,account_type:str,account_id:Union[int,str]):
        """
        Withdraw Amount from a Bank Account.

        Valid account_type: `user`, `clan`, or `global`
        """

        if account_type not in ['user','clan','global']:
            return await ctx.reply("Invalid account type. Valid types are `user`, `clan`, or `global`.")
        
        if account_type == 'global':
            if account_id not in global_accounts:
                return await ctx.reply("Invalid account. Valid accounts are `current`, `sweep`, or `reserve`.")
            
            account = await MasterAccount(account_id)
            await account.withdraw(
                amount=amount,
                user_id=ctx.author.id,
                comment=f"Manual Withdrawal."
                )
            
        if account_type == 'clan':
            clan = await self.client.from_clan_abbreviation(account_id)

            account = await ClanAccount(clan)
            await account.withdraw(
                amount=amount,
                user_id=ctx.author.id,
                comment=f"Manual Withdrawal."
                )
        
        if account_type == 'user':
            user = ctx.bot.get_user(account_id)
            if not user:
                return await ctx.reply("Invalid User.")

            await bank.withdraw_credits(user,amount)
        await ctx.tick()
    
    @app_command_group_bank.command(name="withdraw",
        description="[Bank Admin only] Withdraw Amount from a Bank Account.")
    @app_commands.check(is_bank_admin)
    @app_commands.autocomplete(select_account=autocomplete_eligible_accounts)
    @app_commands.describe(
        amount="The amount to withdraw.",
        select_account="Select an Account to withdraw from.",
        user="Select a User to withdraw from.",
        )
    async def app_command_bank_withdraw(self,interaction:discord.Interaction,amount:int,select_account:Optional[str],user:Optional[discord.Member]=None):
        
        await interaction.response.defer(ephemeral=True)
        currency = await bank.get_currency_name()

        if select_account:
            if select_account in global_accounts:
                account = await MasterAccount(select_account)
                await account.withdraw(
                    amount=amount,
                    user_id=interaction.user.id,
                    comment=f"Manual Withdrawal."
                    )
                return await interaction.followup.send(f"Withdrew {amount:,} {currency} from {select_account.capitalize()} account.",ephemeral=True)
            
            else:
                clan = await self.client.fetch_clan(select_account)
            
                account = await ClanAccount(clan)
                await account.withdraw(
                    amount=amount,
                    user_id=interaction.user.id,
                    comment=f"Manual Withdrawal."
                    )
                return await interaction.followup.send(f"Withdrew {amount:,} {currency} from {clan.title}.",ephemeral=True)
        
        if user:
            await bank.withdraw_credits(user,amount)
            return await interaction.followup.send(f"Withdrew {amount:,} {currency} from {user.display_name}.",ephemeral=True)
    
    ##################################################
    ### REWARD
    ##################################################    
    @command_group_bank.command(name="distribute")
    @commands.guild_only()
    @commands.check(is_coleader_or_bank_admin)
    async def subcommand_bank_reward(self,ctx:commands.Context,account_type_or_clan_abbreviation:str,amount:int,user:discord.Member):
        """
        Distribute a set amount of money to a Discord User.

        Funds are withdrawn from Global or Clan Accounts.
        """

        if account_type_or_clan_abbreviation in global_accounts:
            if not is_bank_admin(ctx):
                return await ctx.reply("You don't have permission to do this.")
            
            account = await MasterAccount(account_type_or_clan_abbreviation)

        else:
            try:
                clan = await self.client.from_clan_abbreviation(account_type_or_clan_abbreviation)
            except InvalidAbbreviation as exc:
                return await ctx.reply(exc.message)
            
            check_permissions = True if (is_bank_admin(ctx) or ctx.author.id == clan.leader or ctx.author.id in clan.coleaders) else False
            if not check_permissions:
                return await ctx.reply("You don't have permission to do this.")
            
            account = await ClanAccount(clan)

        await account.withdraw(
            amount=amount,
            user_id=ctx.author.id,
            comment=f"Reward transfer to {user.name} {user.id}."
            )
        await bank.deposit_credits(user,amount)
        await self._send_log(
            user=user,
            done_by=ctx.author,
            amount=amount,
            comment=f"Reward distribution."
            )
        await ctx.tick()
    
    @app_command_group_bank.command(name="distribute",
        description="Distribute a set amount of money to a Discord User.")
    @app_commands.check(is_coleader_or_bank_admin)
    @app_commands.autocomplete(select_account=autocomplete_eligible_accounts)
    @app_commands.describe(
        select_account="Select an Account to withdraw the reward from.",
        amount="The amount to distribute.",
        user="Select a User to distribute to.",
        role="Select a Role to distribute to."
        )
    async def app_command_bank_reward(self,
        interaction:discord.Interaction,
        select_account:str,
        amount:int,
        user:Optional[discord.Member]=None,
        role:Optional[discord.Role]=None):
        
        await interaction.response.defer()

        async def _helper_reward_user(account:BankAccount,user:discord.Member):
            try:
                await account.withdraw(
                    amount=amount,
                    user_id=interaction.user.id,
                    comment=f"Reward transfer to {user.name} {user.id}."
                    )
                await bank.deposit_credits(user,amount)
                await self._send_log(
                    user=user,
                    done_by=interaction.user,
                    amount=amount,
                    comment=f"Reward distribution."
                    )
                return user
            except:
                return None
            
        currency = await bank.get_currency_name()

        if not user and not role:
            return await interaction.followup.send(f"You need to provide at least a User or a Role.")

        if select_account in global_accounts:
            if not is_bank_admin(interaction):
                return await interaction.followup.send("You don't have permission to do this.",ephemeral=True)
            account = await MasterAccount(select_account)
            
        else:
            clan = await self.client.fetch_clan(select_account)
            check_permissions = True if (is_bank_admin(interaction) or interaction.user.id == clan.leader or interaction.user.id in clan.coleaders) else False
            if not check_permissions:
                return await interaction.followup.send("You don't have permission to do this.",ephemeral=True)
            account = await ClanAccount(clan)

        count = 0
        if role:            
            distribution = await asyncio.gather(*(_helper_reward_user(account,member) for member in role.members))
            count += len([member for member in distribution if isinstance(member,discord.Member)])
        
        if user:
            await _helper_reward_user(account,user)
            count += 1
        
        if count == 1 and user:
            return await interaction.followup.send(f"Rewarded {user.mention} with {amount:,} {currency}.",ephemeral=True)
        else:
            return await interaction.followup.send(f"Distributed {amount:,} {currency} to {count} members (each).",ephemeral=True)
    
    @app_command_group_bank.command(name="distribute-all",
        description="Distribute a set amount of money to all Discord Users.")
    @app_commands.check(is_owner)
    @app_commands.autocomplete(select_account=autocomplete_eligible_accounts)
    @app_commands.describe(
        select_account="Select an Account to withdraw the reward from.",
        amount="The amount to distribute."
        )
    async def app_command_bank_reward_all(self,
        interaction:discord.Interaction,
        select_account:str,
        amount:int):
        
        await interaction.response.defer()

        async def _helper_reward_user(account:BankAccount,user:discord.Member):
            try:
                await account.withdraw(
                    amount=amount,
                    user_id=interaction.user.id,
                    comment=f"Reward transfer to {user.name} {user.id}."
                    )
                await bank.deposit_credits(user,amount)
                await self._send_log(
                    user=user,
                    done_by=interaction.user,
                    amount=amount,
                    comment=f"Reward distribution."
                    )
                return user
            except:
                return None
            
        currency = await bank.get_currency_name()

        if select_account in global_accounts:
            if not is_bank_admin(interaction):
                return await interaction.followup.send("You don't have permission to do this.",ephemeral=True)
            account = await MasterAccount(select_account)
            
        else:
            clan = await self.client.fetch_clan(select_account)
            check_permissions = True if (is_bank_admin(interaction) or interaction.user.id == clan.leader or interaction.user.id in clan.coleaders) else False
            if not check_permissions:
                return await interaction.followup.send("You don't have permission to do this.",ephemeral=True)
            account = await ClanAccount(clan)

        count = 0
        u_iter = AsyncIter(interaction.client.users)
        async for user in u_iter:
            if user.bot:
                continue
            await _helper_reward_user(account,user)
            count += 1
        
        return await interaction.followup.send(f"Distributed {amount:,} {currency} to {count} members (each).",ephemeral=True)
        
    ##################################################
    ### USER INVENTORY
    ##################################################
    @commands.command(name="inventory")
    @commands.guild_only()
    async def command_user_inventory(self,ctx:commands.Context,user:Optional[discord.Member]):
        """
        Display your inventory.

        Your inventory, like your Bank Balances, are considered global and will contain items from different server stores.
        """
        
        target = None
        if is_bank_admin(ctx) and user:
            target = user
        else:
            target = ctx.author

        inventory = await UserInventory(target)
        embed = await inventory.get_embed(ctx)
        await ctx.reply(embed=embed)
    
    @app_commands.command(
        name="inventory",
        description="Display your inventory."
        )
    @app_commands.guild_only()
    @app_commands.describe(
        member="Select a Member to view inventories for. Only usable by Bank Admins.")
    async def app_command_user_inventory(self,interaction:discord.Interaction,member:Optional[discord.Member]):
        
        await interaction.response.defer()

        target = None
        if is_bank_admin(interaction) and member:
            target = member
        else:
            target = interaction.guild.get_member(interaction.user.id)

        inventory = await UserInventory(target)
        embed = await inventory.get_embed(interaction)
        await interaction.followup.send(embed=embed)
    
    ##################################################
    ### USER STORE
    ##################################################
    @commands.command(name="shop",aliases=['store'])
    @commands.guild_only()
    async def command_user_store(self,ctx:commands.Context):
        """
        Open the Guild Shop.
        """
        store = UserStore(ctx)
        await store.start()
    
    @app_commands.command(
        name="shop",
        description="Open the Guild Shop."
        )
    @app_commands.guild_only()
    async def app_command_user_store(self,interaction:discord.Interaction):
        
        await interaction.response.defer()
        store = UserStore(interaction)
        await store.start()
    
    ##################################################
    ### USER GIFT
    ##################################################
    @commands.command(name="gift",aliases=['give'])
    @commands.guild_only()
    async def command_user_gift(self,ctx:commands.Context):
        """
        Gift a friend an item from your Inventory!

        You can only gift items from the current server.
        """

        await ctx.reply(f"Use the Slash Command `/gift` to do this action.")
    
    @app_commands.command(
        name="gift",
        description="Gift a friend an item from your Inventory!"
        )
    @app_commands.guild_only()
    @app_commands.autocomplete(item=autocomplete_gift_items)
    @app_commands.describe(
        item="Select an item to gift.",
        user="Select a user to gift to."
        )
    async def app_command_user_gift(self,interaction:discord.Interaction,item:str,user:discord.Member):        
        await interaction.response.defer(ephemeral=True)

        if user.id == interaction.user.id:
            return await interaction.followup.send("You can't gift yourself!",ephemeral=True)

        if user.bot:
            return await interaction.followup.send("You can't gift bots!",ephemeral=True)
        
        item = await ShopItem.get_by_id(item)

        inventory = await UserInventory(interaction.user)
        gift = await inventory.gift_item(item,user)
        if not gift:
            return await interaction.followup.send(f"You don't have that item.",ephemeral=True)
        return await interaction.followup.send(f"Yay! You've gifted {user.mention} 1x **{gift.name}**.",ephemeral=True)
    
    ##################################################
    ### SHOP ITEM GROUP
    ##################################################    
    @commands.group(name="shopmanage")
    @commands.admin()
    @commands.guild_only()
    async def command_group_shop_item(self,ctx:commands.Context):
        """
        Group Command to help manage Shop Items.
        """
        if not ctx.invoked_subcommand:
            pass
    
    app_command_group_shopitem = app_commands.Group(
        name="shop-manage",
        description="Group for Shop Item commands. Equivalent to [p]shopmanage.",
        guild_only=True
        )
    
    ##################################################
    ### SHOP ITEM / DISTRIBUTE
    ##################################################
    @command_group_shop_item.command(name="distribute")
    @commands.admin()
    @commands.guild_only()
    async def subcommand_item_distribute(self,ctx:commands.Context):
        """
        Administratively distribute an item to a specified user.

        This bypasses all checks and will distribute the item directly to the user's inventory.
        """

        await ctx.reply(f"For a better experience, use the Slash Command `/shop-manage distribute` to do this action.")
    
    @app_command_group_shopitem.command(
        name="distribute",
        description="Administratively distribute an item to a specified user."
        )
    @app_commands.guild_only()
    @app_commands.check(is_admin)
    @app_commands.autocomplete(item=autocomplete_distribute_items)
    @app_commands.describe(
        item="Select an item to distribute.",
        user="Select a user to distribute to."
        )
    async def app_command_distribute_item(self,interaction:discord.Interaction,item:str,user:discord.Member):        
        await interaction.response.defer(ephemeral=True)

        if user.id == interaction.user.id:
            return await interaction.followup.send("You can't give items to yourself!",ephemeral=True)
        if user.bot:
            return await interaction.followup.send("You can't give items to bots!",ephemeral=True)
        
        get_item = await ShopItem.get_by_id(item)

        inventory = await UserInventory(user)
        await inventory.purchase_item(get_item,True)

        return await interaction.followup.send(f"1x **{get_item.name}** has been distributed to {user.mention}.",ephemeral=True)

    @app_command_group_shopitem.command(
        name="distribute-all",
        description="Administratively distribute an item to all users."
        )
    @app_commands.check(is_owner)
    @app_commands.autocomplete(item=autocomplete_distribute_items)
    @app_commands.describe(
        item="Select an item to distribute. Only Basic items can be distributed."
        )
    async def app_command_distribute_all_item(self,interaction:discord.Interaction,item:str):
        await interaction.response.defer(ephemeral=True)
        count = 0
        u_iter = AsyncIter(interaction.client.users)
        async for user in u_iter:
            if user.bot:
                continue
            count += 1
            get_item = await ShopItem.get_by_id(item)
            inventory = await UserInventory(user)
            await inventory.purchase_item(get_item,True)

        return await interaction.followup.send(f"1x **{get_item.name}** has been added to {count} users.",ephemeral=True)

    ##################################################
    ### SHOP ITEM / REDEEM
    ##################################################
    @command_group_shop_item.command(name="redeem")
    @commands.admin()
    @commands.guild_only()
    async def subcommand_item_redeem(self,ctx:commands.Context):
        """
        Redeems an item from a user's inventory.

        Only usable if item exists in the user's inventory.
        """

        await ctx.reply(f"For a better experience, use the Slash Command `/shop-manage redeem` to do this action.")
    
    @app_command_group_shopitem.command(
        name="redeem",
        description="Redeems an item from a user's inventory."
        )
    @app_commands.guild_only()
    @app_commands.check(is_admin)
    @app_commands.autocomplete(item=autocomplete_redeem_items)
    @app_commands.describe(
        item="Select an item to redeem.",
        user="Select a user to redeem from."
        )
    async def app_command_redeem_item(self,interaction:discord.Interaction,item:str,user:discord.Member):        
        await interaction.response.defer()

        if user.id == interaction.user.id:
            return await interaction.followup.send("You can't redeem items for yourself!")
        if user.bot:
            return await interaction.followup.send("You can't redeem items for bots!")
        
        get_item = await ShopItem.get_by_id(item)
        inventory = await UserInventory(user)

        if not inventory.has_item(get_item):
            return await interaction.followup.send(f"{user.mention} doesn't have that item.")

        await inventory.remove_item_from_inventory(get_item)
        await interaction.followup.send(f"1x **{get_item.name}** has been redeemed from {user.mention}'s inventory.")

    ##################################################
    ### SHOP ITEM / OVERVIEW
    ################################################## 
    async def _shop_overview_embed(self,ctx:Union[commands.Context,discord.Interaction]):
        guild_items = await ShopItem.get_by_guild(ctx.guild.id)
        embed = await clash_embed(
            context=ctx,
            title=f"**Guild Store: {ctx.guild.name}**"
            )
        embed.add_field(
            name=f"**Overview**",
            value="```ini"
                + f"\n{'[Total Items]':<15} {len(guild_items):>3}"
                + f"\n{'[In Store]':<15} {len([i for i in guild_items if i.show_in_store]):>3}"
                + f"\n{'[Stock Out]':<15} {len([i for i in guild_items if i.stock == 0]):>3}"
                + "```",
            inline=True)
        embed.add_field(
            name=f"**Items by Type (In Store / Total)**",
            value="```ini"
                + f"\n{'[Basic]':<10} {len([i for i in guild_items if i.type == 'basic' and i.show_in_store]):^4}/{len([i for i in guild_items if i.type == 'basic']):^4}"
                + f"\n{'[Role]':<10} {len([i for i in guild_items if i.type == 'role' and i.show_in_store]):^4}/{len([i for i in guild_items if i.type == 'role']):^4}"
                + f"\n{'[Random]':<10} {len([i for i in guild_items if i.type == 'random' and i.show_in_store]):^4}/{len([i for i in guild_items if i.type == 'random']):^4}"
                + f"\n{'[Cash]':<10} {len([i for i in guild_items if i.type == 'cash' and i.show_in_store]):^4}/{len([i for i in guild_items if i.type == 'cash']):^4}"
                + "```",
            inline=True)
        if len([i for i in guild_items if i.stock == 0]) > 0:
            embed.add_field(
                name=f"**Needing Restock**",
                value=f"Use the `/shop-manage restock` command to restock items."
                    + "\n- "
                    + "\n- ".join([f"{str(i)}" for i in guild_items if i.stock == 0])
                    + "\n\u200b",
                inline=False)
        return embed
    
    @command_group_shop_item.command(name="status")   
    @commands.admin()
    @commands.guild_only()
    async def subcommand_shop_item_status(self,ctx:commands.Context):
        """
        Overview of the Guild Store.
        """
        embed = await self._shop_overview_embed(ctx)
        await ctx.reply(embed=embed)
    
    @app_command_group_shopitem.command(
        name="status",
        description="Overview of the Guild Store."
        )
    @app_commands.guild_only()
    @app_commands.check(is_admin)
    async def app_command_shop_overview(self,interaction:discord.Interaction):
        
        await interaction.response.defer()
        embed = await self._shop_overview_embed(interaction)
        await interaction.followup.send(embed=embed)

    ##################################################
    ### SHOP ITEM / EXPORT
    ################################################## 
    async def _shop_export(self,ctx:Union[commands.Context,discord.Interaction]):
        guild_items = await ShopItem.get_by_guild(ctx.guild.id)

        if len(guild_items) == 0:
            return None

        report_file = bot_client.bot.coc_bank_path + '/' + f"{ctx.guild.name}_ShopItems_{pendulum.now().format('YYYYMMDDHHmmss')}.xlsx"

        workbook = xlsxwriter.Workbook(report_file)
        worksheet = workbook.add_worksheet('Guild Items')

        headers = ['ID','Type','Name','Category','Description','Price','Stock','Show in Store','Requires Role','Is Exclusive','Add-only?']

        row = 0
        col = 0
        async for h in AsyncIter(headers):
            worksheet.write(row,col,h)
            col += 1

        async for t in AsyncIter(guild_items):
            col = 0
            row += 1

            m_data = []
            m_data.append(t.id)
            m_data.append(t.type.capitalize())
            m_data.append(t.name)
            m_data.append(t.category)
            m_data.append(t.description)
            m_data.append(t.price)
            m_data.append(t.stock)
            m_data.append(t.show_in_store)
            m_data.append(getattr(t.required_role,'name',''))
            m_data.append(t.exclusive_role)
            m_data.append(False if t.bidirectional_role else True)

            for d in m_data:
                worksheet.write(row,col,d)
                col += 1
        
        workbook.close()
        return report_file
    
    @command_group_shop_item.command(name="export")   
    @commands.admin()
    @commands.guild_only()
    async def subcommand_shop_item_export(self,ctx:commands.Context):
        """
        Export Shop Items for the Guild to Excel.
        """
        embed = await clash_embed(
            context=ctx,
            message=f"{EmojisUI.LOADING} Please wait..."
            )
        msg = await ctx.reply(embed=embed)
        
        rpfile = await self._shop_export(ctx)
        if not rpfile:
            embed = await clash_embed(
                context=ctx,
                message=f"There were no items to report."
                )
            await msg.edit(embed=embed)
            return

        await msg.edit(
            content=f"{ctx.author.mention} Your report is available for download below.",
            embed=None,
            attachments=[discord.File(rpfile)]
            )
    
    @app_command_group_shopitem.command(
        name="export",
        description="Export Shop Items for the Guild to Excel."
        )
    @app_commands.guild_only()
    @app_commands.check(is_admin)
    async def app_command_shop_item_export(self,interaction:discord.Interaction):
        
        await interaction.response.defer()
        embed = await clash_embed(
            context=interaction,
            message=f"{EmojisUI.LOADING} Please wait..."
            )
        msg = await interaction.followup.send(embed=embed,wait=True)
        
        rpfile = await self._shop_export(interaction)
        if not rpfile:
            embed = await clash_embed(
                context=interaction,
                message=f"There were no items to report."
                )
            await msg.edit(embed=embed)
            return

        await msg.edit(
            content=f"{interaction.user.mention} Your report is available for download below.",
            embed=None,
            attachments=[discord.File(rpfile)]
            )

    ##################################################
    ### SHOP ITEM / ADD
    ################################################## 
    @command_group_shop_item.command(name="add")   
    @commands.admin()
    @commands.guild_only()
    async def subcommand_shop_item_add(self,ctx:commands.Context):
        """
        Adds a Shop Item.

        Uses the system ID to identify Shop Items. You can get the system ID using `/shop-manage export`.
        """
        view = AddItem(ctx)
        await view.start()
    
    @app_command_group_shopitem.command(
        name="add",
        description="Adds a Shop Item."
        )
    @app_commands.guild_only()
    @app_commands.check(is_admin)
    async def app_command_add_item(self,interaction:discord.Interaction):
        
        await interaction.response.defer()
        view = AddItem(interaction)
        await view.start()
    
    ##################################################
    ### SHOP ITEM / DELETE
    ################################################## 
    @command_group_shop_item.command(name="delete")   
    @commands.admin()
    @commands.guild_only()
    async def subcommand_shop_item_delete(self,ctx:commands.Context,item_id:str):
        """
        Delete a Shop Item.

        Uses the system ID to identify Shop Items. You can get the system ID using `/shop-manage export`.
        """
        item = await ShopItem.get_by_id(item_id)
        if not item:
            return await ctx.reply("I couldn't find that item.")
        await item.delete()
        await ctx.tick()
    
    @app_command_group_shopitem.command(
        name="delete",
        description="Delete a Shop Item."
        )
    @app_commands.guild_only()
    @app_commands.check(is_admin)
    @app_commands.autocomplete(item=autocomplete_store_items)
    @app_commands.describe(
        item="Select a Shop Item to delete."
        )        
    async def app_command_delete_item(self,interaction:discord.Interaction,item:str):
        
        await interaction.response.defer(ephemeral=True)
        get_item = await ShopItem.get_by_id(item)
        if not item:
            return await interaction.followup.send("I couldn't find that item.",ephemeral=True)
        await get_item.delete()
        await interaction.followup.send(f"{get_item.name} deleted.",ephemeral=True)
    
    ##################################################
    ### SHOP ITEM / SHOW
    ##################################################
    async def build_change_description_modal(self,new_description:str=None,new_buy_msg:str=None):
        async def save_input(interaction:discord.Interaction,modal:DiscordModal):
            await interaction.response.defer()
            c_iter = AsyncIter(modal.children)
            async for item in c_iter:
                if item.label == "Description":
                    modal.new_description = item.value
                if item.label == "Buy Message":
                    modal.new_buy_message = item.value            
            modal.stop()
        
        modal = DiscordModal(
            function=save_input,
            title="Edit Shop Item",
            )
        if new_description:
            modal.add_field(
                label="Description",
                style=discord.TextStyle.short,
                placeholder="The new Decription to use for this item.",
                default=new_description,
                required=True,
                min_length=1
                )
        if new_buy_msg:
            modal.add_field(
                label="Buy Message",
                style=discord.TextStyle.long,
                placeholder="The new Buy Message to use for this item.",
                default=new_buy_msg,
                required=True,
                min_length=1
                )
        return modal

    @command_group_shop_item.command(name="edit")   
    @commands.admin()
    @commands.guild_only()
    async def subcommand_shop_edit_item(self,ctx:commands.Context):
        """
        Edits a Shop Item in the Store.

        The following parameters can be edited:
        - Show in Store
        - Category
        - Description
        - Required Role
        - Buy Message
        """
        await ctx.reply(f"Use the Slash Command `/shop-manage edit` to do this action.")
    
    @app_command_group_shopitem.command(
        name="edit",
        description="Edits a Shop Item in the Store. Not all parameters can be edited."
        )
    @app_commands.guild_only()
    @app_commands.check(is_admin)
    @app_commands.autocomplete(item=autocomplete_store_items)
    @app_commands.describe(
        item="Select a Shop Item to edit.",
        show_in_store="Change whether the item is shown in the store.",
        category="Change the category of the item.",
        description="Change the description of the item.",
        required_role="Change the required role to purchase the item.",
        buy_message="Change the message sent when the item is purchased. Only applicable for basic items."
        )
    @app_commands.choices(show_in_store=[
        app_commands.Choice(name="True",value=2),
        app_commands.Choice(name="False",value=1)
        ])
    async def app_command_edit_item(self,
        interaction:discord.Interaction,
        item:str,
        show_in_store:Optional[int]=0,
        category:Optional[str]=None,
        description:Optional[str]=None,
        required_role:Optional[discord.Role]=None,
        buy_message:Optional[str]=None,
        ):

        new_description = None
        new_buy_msg = None
                
        if description or buy_message:
            modal = await self.build_change_description_modal(
                new_description=description,
                new_buy_msg=buy_message
                )
            await interaction.response.send_modal(modal)

            wait = await modal.wait()
            if wait:
                await interaction.followup.send(f"Did not receive a response.",ephemeral=True)
            
            new_description = getattr(modal,'new_description',None)
            new_buy_msg = getattr(modal,'new_buy_message',None)

        else:            
            await interaction.response.defer(ephemeral=True)
        
        get_item = await ShopItem.get_by_id(item)
        if not item:
            return await interaction.followup.send("I couldn't find that item.",ephemeral=True)

        if show_in_store > 0:            
            if show_in_store == 2:
                await get_item.unhide()
                await interaction.followup.send(f"{get_item.name} is now enabled in the Guild Store.",ephemeral=True)
            else:
                await get_item.hide()
                await interaction.followup.send(f"{get_item.name} is now hidden in the Guild Store.",ephemeral=True)
        
        if category:            
            await get_item.edit(category=category)
            await interaction.followup.send(f"Updated {get_item.name} category to {category}.",ephemeral=True)
        
        if new_description:            
            await get_item.edit(description=new_description)
            await interaction.followup.send(f"Updated {get_item.name} description.",ephemeral=True)
        
        if new_buy_msg:
            await get_item.edit(buy_message=new_buy_msg)
            await interaction.followup.send(f"Updated {get_item.name} buy message.",ephemeral=True)
        
        if required_role:            
            await get_item.edit(required_role=required_role.id)
            await interaction.followup.send(f"Updated {get_item.name} required role to {required_role.mention}.",ephemeral=True)
    
    ##################################################
    ### SHOP ITEM / RESTOCK
    ################################################## 
    @command_group_shop_item.command(name="restock")   
    @commands.admin()
    @commands.guild_only()
    async def subcommand_shop_item_restock(self,ctx:commands.Context,item_id:str,amount:int):
        """
        Restocks a Shop Item.

        Adds the specified amount to the current stock. Only usable if item is not unlimited.

        Uses the system ID to identify Shop Items. If you're not sure what this is, use the Slash Command.
        """
        item = await ShopItem.get_by_id(item_id)
        if not item:
            return await ctx.reply("I couldn't find that item.")
        
        await item.restock(amount)
        await ctx.reply(f"Restocked {item} by {amount}. New stock: {item.stock}.")
    
    @app_command_group_shopitem.command(
        name="restock",
        description="Restocks a Shop Item."
        )
    @app_commands.guild_only()
    @app_commands.check(is_admin)
    @app_commands.autocomplete(item=autocomplete_store_items_restock)
    @app_commands.describe(
        item="Select a Shop Item to restock.",
        amount="The amount to restock."
        )        
    async def app_command_restock_item(self,interaction:discord.Interaction,item:str,amount:int):
        await interaction.response.defer(ephemeral=True)
        get_item = await ShopItem.get_by_id(item)
        if not get_item:
            return await interaction.followup.send("I couldn't find that item.",ephemeral=True)
        await get_item.restock(amount)
        await interaction.followup.send(f"Restocked {get_item} by {amount}. New stock: {get_item.stock}.",ephemeral=True)

class ClashAccountSelector(discord.ui.View):
    def __init__(self,user:discord.User,list_of_accounts:List[aPlayer]):
        
        self.user = user
        self.list_of_accounts = list_of_accounts
        self.selected_account = None

        select_options = [discord.SelectOption(
            label=f"{account.name} | {account.tag}",
            value=account.tag,
            description=f"{account.clan_description}",
            emoji=account.town_hall.emoji)
            for account in list_of_accounts]

        dropdown = DiscordSelectMenu(
            function=self.callback_select_account,
            options=select_options[:25],
            placeholder="Select an account...",
            min_values=1,
            max_values=1
            )

        super().__init__(timeout=90)
        self.add_item(dropdown)
    
    async def callback_select_account(self,interaction:discord.Interaction,menu:DiscordSelectMenu):
        await interaction.response.defer()
        self.selected_account = menu.values[0]
        await interaction.edit_original_response(view=None)
        self.stop()
    
    async def interaction_check(self,interaction:discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                content="This doesn't belong to you!", ephemeral=True
                )
            return False
        return True
    
    async def on_timeout(self):
        self.stop()

class AssistantConfirmation(discord.ui.View):
    def __init__(self,user:discord.User):

        self.confirmation = None
        self.user = user

        self.yes_button = DiscordButton(
            function=self.yes_callback,
            label="Yes, I accept.",
            emoji=EmojisUI.YES,
            style=discord.ButtonStyle.green,
            )
        self.no_button = DiscordButton(
            function=self.no_callback,
            label="No, I do not accept.",
            emoji=EmojisUI.NO,
            style=discord.ButtonStyle.grey,
            )

        super().__init__(timeout=120)

        self.add_item(self.yes_button)
        self.add_item(self.no_button)
    
    ##################################################
    ### OVERRIDE BUILT IN METHODS
    ##################################################
    async def interaction_check(self, interaction:discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                content="This doesn't belong to you!", ephemeral=True
                )
            return False
        return True

    async def on_timeout(self):
        self.clear_items()
        self.stop()
    
    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        self.stop()
    
    ##################################################
    ### CALLBACKS
    ##################################################
    async def yes_callback(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        self.confirmation = True
        await interaction.edit_original_response(view=None)
        self.stop()
    
    async def no_callback(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer()
        self.confirmation = False
        await interaction.edit_original_response(view=None)
        self.stop()