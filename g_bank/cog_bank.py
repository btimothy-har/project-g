import asyncio
import os
import discord
import pendulum

from typing import *

from redbot.core import Config, commands, app_commands, bank
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.utils import AsyncIter

from .objects.accounts import MasterAccount, ClanAccount
from .objects.inventory import UserInventory
from .objects.item import ShopItem
from .views.store_manager import StoreManager
from .views.user_store import UserStore

from .checks import is_bank_admin, is_bank_server, is_coleader_or_bank_admin
from .autocomplete import autocomplete_eligible_accounts, autocomplete_store_items, autocomplete_store_items_restock, autocomplete_distribute_items, autocomplete_gift_items

from mee6rank.mee6rank import Mee6Rank

from coc_main.api_client import BotClashClient, ClashOfClansError, InvalidAbbreviation
from coc_main.cog_coc_client import ClashOfClansClient, aPlayer, aClan, db_Player

from coc_main.coc_objects.events.clan_war import aWarPlayer
from coc_main.coc_objects.events.raid_weekend import aRaidMember

from coc_main.discord.member import aMember

from coc_main.utils.components import clash_embed, MenuPaginator
from coc_main.utils.constants.coc_constants import WarResult
from coc_main.utils.constants.ui_emojis import EmojisUI
from coc_main.utils.checks import is_admin
from coc_main.utils.autocomplete import autocomplete_clans_coleader

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
    __release__ = 4

    def __init__(self,bot:Red):
        self.bot = bot

        self.bot.coc_bank_path = f"{cog_data_path(self)}/reports"
        if not os.path.exists(self.bot.coc_bank_path):
            os.makedirs(self.bot.coc_bank_path)

        self.current_account = MasterAccount('current')
        self.sweep_account = MasterAccount('sweep')
        self.reserve_account = MasterAccount('reserve')
        self.eligible_boost_servers = [1132581106571550831,688449973553201335,680798075685699691]

        self.config = Config.get_conf(self,identifier=644530507505336330,force_registration=True)
        default_global = {
            "use_rewards":False,
            }
        self.config.register_global(**default_global)

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}.{self.__release__}"

    @property
    def client(self) -> ClashOfClansClient:
        return self.bot.get_cog("ClashOfClansClient")
    
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
    
    async def cog_load(self):
        try:
            self.use_rewards = await self.config.use_rewards()
        except:
            self.use_rewards = False
    
    ############################################################
    #####
    ##### ACCOUNT HELPERS
    #####
    ############################################################
    def get_clan_account(self,clan:aClan):
        if not clan.is_alliance_clan:
            raise ValueError("Clan must be an Alliance Clan.")
        return ClanAccount(clan.tag)

    ############################################################
    #####
    ##### REWARD DISTRIBUTION
    #####
    ############################################################
    async def month_end_sweep(self):
        async with self.current_account.lock:
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
        available_for_distribution = sweep_balance * 0.7
        async for clan in AsyncIter(alliance_clans):
            if not clan.bank_account:
                continue

            clan_balance = clan.balance
            if clan_balance > 0:
                await self.reserve_account.deposit(
                    amount=round(clan_balance * 0.1),
                    user_id=self.bot.user.id,
                    comment=f"EOS from {clan.tag} {clan.name}."
                    )
                await clan.bank_account.withdraw(
                    amount=round(clan_balance * 0.1),
                    user_id=self.bot.user.id,
                    comment=f"EOS to Reserve Account."
                    )                
            if available_for_distribution > 0:
                await clan.bank_account.deposit(
                    amount=round((available_for_distribution) / len(alliance_clans)),
                    user_id=self.bot.user.id,
                    comment=f"EOS from Sweep Account."
                    )
                await self.sweep_account.withdraw(
                    amount=round((available_for_distribution) / len(alliance_clans)),
                    user_id=self.bot.user.id,
                    comment=f"EOS to {clan.tag} {clan.name}."
                    )
                
        member_tags = [db.tag for db in db_Player.objects(is_member=True).only('tag')]
           
        await self.current_account.deposit(
            amount=round(len(member_tags) * 25000),
            user_id=self.bot.user.id,
            comment=f"EOS new funds: {len(member_tags)} members."
            )
    
    async def apply_bank_taxes(self):
        await bank.bank_prune(self.bot)
        all_accounts = await bank.get_leaderboard()

        async for id,account in AsyncIter(all_accounts):
            user = self.bot.get_user(id)
            if user.bot:
                await bank.set_balance(user,0)
                continue

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
    
    async def member_th_progress_reward(self,player:aPlayer,cached_value:int):
        if not self.use_rewards:
            return
        if not player.is_member:
            return
        member = self.bot.get_user(player.discord_user)
        if not member:
            return
        
        if player.hero_rushed_pct > 0:
            reward = 0
        elif player.town_hall.level <= 9:
            reward = 10000
        elif player.town_hall.level <= 13:
            reward = 15000
        else:
            reward = 20000
        
        await bank.deposit_credits(member,reward)
        await self.current_account.withdraw(
            amount = reward,
            user_id = self.bot.user.id,
            comment = f"Townhall Bonus for {player.name} ({player.tag}): TH{cached_value} to TH{player.town_hall.level}."
            )
    
    async def member_hero_upgrade_reward(self,player:aPlayer,levels:int):
        if not self.use_rewards:
            return
        if not player.is_member:
            return
        member = self.bot.get_user(player.discord_user)
        if not member:
            return
        
        reward = 1000 * levels
        await bank.deposit_credits(member,reward)
        await self.current_account.withdraw(
            amount = reward,
            user_id = self.bot.user.id,
            comment = f"Hero Bonus for {player.name} ({player.tag}): {levels} upgraded."
            )
    
    async def member_legend_rewards(self):
        if not self.use_rewards:
            return
        
        reward_per_trophy = 20
        member_tags = [db.tag for db in db_Player.objects(is_member=True).only('tag')]
        alliance_members = await asyncio.gather(*(self.client.fetch_player(tag) for tag in member_tags))
        
        async for player in AsyncIter(alliance_members):
            if not player.is_member:
                continue
            if not player.legend_statistics:
                continue
            if not player.legend_statistics.previous_season:
                continue

            member = self.bot.get_user(player.discord_user)
            if not member:
                continue
            reward = (player.legend_statistics.previous_season.trophies - 5000) * reward_per_trophy
            if reward > 0:
                await bank.deposit_credits(member,reward)
                await self.current_account.withdraw(
                    amount=reward,
                    user_id=self.bot.user.id,
                    comment=f"Legend Rewards for {player.name} {player.tag}."
                    )
    
    async def war_bank_rewards(self,player:aWarPlayer):
        if not self.use_rewards:
            return
        
        member = self.bot.get_user(player.discord_user)
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

        membership_multiplier = 1 if player.is_member else non_member_multiplier
        participation = 50
        performance = (50 * player.star_count) + (300 * len([a for a in player.attacks if a.is_triple]))
        result = 100 if player.clan.result == WarResult.WON else 0

        total_reward = round((participation + performance + result) * membership_multiplier)
        await bank.deposit_credits(member,total_reward)
        await self.current_account.withdraw(
            amount = total_reward,
            user_id = self.bot.user.id,
            comment = f"Clan War Reward for {player.name} ({player.tag})."
            )
    
    async def raid_bank_rewards(self,player:aRaidMember):
        if not self.use_rewards:
            return
        
        member = self.bot.get_user(player.discord_user)
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
        
        membership_multiplier = 1 if player.is_member else non_member_multiplier

        total_reward = round((20 * (sum([a.new_destruction for a in player.attacks]) // 5)) * membership_multiplier)
        await bank.deposit_credits(member,total_reward)
        await self.current_account.withdraw(
            amount = total_reward,
            user_id = self.bot.user.id,
            comment = f"Raid Weekend Reward for {player.name} ({player.tag})."
            )
    
    async def capital_contribution_rewards(self,player:aPlayer,value_increment:int):
        if not self.use_rewards:
            return
        member = self.bot.get_user(player.discord_user)
        if not member:
            return
        membership_multiplier = 1 if player.is_member else non_member_multiplier
        total_reward = round((10 * (value_increment // 1000)) * membership_multiplier)

        await bank.deposit_credits(member,total_reward)
        await self.current_account.withdraw(
            amount = total_reward,
            user_id = self.bot.user.id,
            comment = f"Capital Gold Bonus for {player.name} ({player.tag}): {value_increment}"
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
            embed = await clash_embed(
                context=context,
                message=f"**{clan.title}** has **{clan.balance:,} {currency}**.",
                timestamp=pendulum.now()
                )
            return embed       

        member = aMember(user.id,context.guild.id)

        embed = await clash_embed(
            context=context,
            message=f"You have **{await bank.get_balance(member.discord_member):,} {currency}** (Global Rank: #{await bank.get_leaderboard_position(member.discord_member)}).",
            timestamp=pendulum.now()
            )
        if context.guild.id == 1132581106571550831:
            embed.description += "\nNext payday: "
            embed.description += (f"<t:{member.last_payday.add(days=1).int_timestamp}:R>" if member.last_payday and member.last_payday.add(days=1) > pendulum.now() else "Now! Use `payday` to claim your credits!")
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
    @app_commands.autocomplete(select_clan=autocomplete_clans_coleader)
    @app_commands.describe(
        select_clan="Select a Clan to view balances for. Only usable by Clan Leaders and Co-Leaders.")
    async def app_command_bank_balance(self,interaction:discord.Interaction,select_clan:Optional[str]=None):
        
        await interaction.response.defer()

        if select_clan:
            clan = await self.client.fetch_clan(select_clan)
            embed = await self.helper_show_balance(interaction,clan)
        else:
            embed = await self.helper_show_balance(interaction)

        await interaction.edit_original_response(embed=embed)        
    
    ##################################################
    ### PAYDAY
    ##################################################
    async def helper_payday(self,context:Union[discord.Interaction,commands.Context]):
        currency = await bank.get_currency_name()
        user = context.guild.get_member(context.user.id) if isinstance(context,discord.Interaction) else context.author
        member = aMember(user.id,context.guild.id)

        is_booster = True if member.discord_member.premium_since else False

        last_payday = member.last_payday
        if last_payday:
            if last_payday.add(days=1) > pendulum.now():
                embed = await clash_embed(
                    context=context,
                    message=f"You can claim your next payday <t:{last_payday.add(days=1).int_timestamp}:R>.",
                    success=False,
                    timestamp=pendulum.now()
                    )        
                return embed        
        try:
            mee6user = await Mee6Rank._get_player(
                bot_client.bot.get_cog("Mee6Rank"),
                user,
                get_avatar=False
                )
        except:
            mee6user = None

        basic_payout = 50
        xp_bonus = 10 * (mee6user.level // 10 if mee6user else 0)
        boost_bonus = 1000 if is_booster else 0

        total_payout = basic_payout + xp_bonus + boost_bonus
        await bank.deposit_credits(user,total_payout)

        member.last_payday = pendulum.now().int_timestamp

        embed = await clash_embed(
            context=context,
            message=f"Here's some money, {user.mention}! You received:"
                + f"\n\nBase Payout: {basic_payout} {currency}"
                + f"\nXP Bonus: {xp_bonus:,} {currency}"
                + f"\nNitro Bonus: {boost_bonus:,} {currency}"
                + f"\n\nTotal: {total_payout:,} {currency}. You now have: {await bank.get_balance(user):,} {currency}.",
            success=True,
            timestamp=pendulum.now()
            )        
        return embed
    
    @commands.command(name="payday")
    @commands.guild_only()
    @commands.check(is_bank_server)
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
    @app_commands.check(is_bank_server)
    async def app_command_payday(self,interaction:discord.Interaction):

        await interaction.response.defer()        
        embed = await self.helper_payday(interaction)
        await interaction.followup.send(embed=embed)         
    
    ##################################################
    ### BANK / TOGGLEREWARDS
    ##################################################
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

        member_tags = [db.tag for db in db_Player.objects(is_member=True).only('tag')]

        embed = await clash_embed(
            context=context,
            title=f"**Guild Bank Accounts**",
            message=f"`{'Current':<10}` {self.current_account.balance:,} {currency}"
                + f"\n`{'Sweep':<10}` {self.sweep_account.balance:,} {currency}"
                + f"\n`{'Reserve':<10}` {self.reserve_account.balance:,} {currency}"
                + f"\n`{'Total':<10}` {total_balance:,} {currency}"
                + f"\n\nNew Monthly Balance (est.): {len(member_tags) * 25000:,}",
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
    @command_group_bank.command(name="leaderboard",aliases=['lb'])
    @commands.guild_only()
    async def command_bank_leaderboard(self,ctx:commands.Context):
        """
        Displays the Economy Leaderboard for this Server.
        """        
        pages = []
        leaderboard = await bank.get_leaderboard(guild=ctx.guild)
        now = pendulum.now()

        if len(leaderboard) == 0:
            return await ctx.reply("Oops! There doesn't seem to be any accounts in the Bank.")
        
        count = 0
        embed = None
        async for id,account in AsyncIter(leaderboard):
            count += 1
            if not embed:
                embed = await clash_embed(
                    context=ctx,
                    title=f"Bank Leaderboard: {ctx.guild.name}",
                    message=f"`{'':>3}{'':<3}{'WEALTH':>7}{'':<2}`",
                    timestamp=now
                    )
            member = ctx.guild.get_member(id)            
            embed.description += f"\n`{count:>3}{'':<3}{account['balance']:>7,}{'':<2}`\u3000{member.display_name}"
            if (count >= 10 and count % 10 == 0) or count == len(leaderboard):
                pages.append(embed)
                embed = None
        
        if len(pages) > 1:
            paginate = MenuPaginator(ctx,pages)
            await paginate.start()
        else:
            await ctx.reply(embed=pages[0])
    
    @app_command_group_bank.command(name="leaderboard",
        description="Displays the Economy Leaderboard for this Server.")
    async def app_command_bank_leaderboard(self,interaction:discord.Interaction):

        await interaction.response.defer()

        pages = []
        leaderboard = await bank.get_leaderboard(guild=interaction.guild)
        now = pendulum.now()

        if len(leaderboard) == 0:
            return await interaction.followup.send("Oops! There doesn't seem to be any accounts in the Bank.")
        
        count = 0
        embed = None
        async for id,account in AsyncIter(leaderboard):
            count += 1
            if not embed:
                embed = await clash_embed(
                    context=interaction,
                    title=f"Bank Leaderboard: {interaction.guild.name}",
                    message=f"`{'':>3}{'':<3}{'WEALTH':>7}{'':<2}`",
                    timestamp=now
                    )
            member = interaction.guild.get_member(id)            
            embed.description += f"\n`{count:>3}{'':<3}{account['balance']:>7,}{'':<2}`\u3000{member.display_name}"
            if (count >= 10 and count % 10 == 0) or count == len(leaderboard):
                pages.append(embed)
                embed = None
        
        if len(pages) > 1:
            paginate = MenuPaginator(interaction,pages)
            await paginate.start()
        else:
            await interaction.followup.send(embed=pages[0])
    
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

        if account_type_or_clan_abbreviation in ['current','sweep','reserve']:
            if not is_bank_admin(ctx):
                return await ctx.reply("You don't have permission to do this.")
            account = MasterAccount(account_type_or_clan_abbreviation)
        
        else:
            clan = await self.client.from_clan_abbreviation(account_type_or_clan_abbreviation)
            check_permissions = True if (is_bank_admin(ctx) or ctx.author.id == clan.leader or ctx.author.id in clan.coleaders) else False

            if not check_permissions:
                return await ctx.reply("You don't have permission to do this.")
            account = ClanAccount(clan.tag)
        
        embed = await clash_embed(
            context=ctx,
            message=f"{EmojisUI.LOADING} Please wait..."
            )
        msg = await ctx.reply(embed=embed)
        
        rpfile = await account.export() 
        if not rpfile:
            return await msg.edit("There were no transactions to report.")
           
        rept_embed = await clash_embed(
            context=ctx,
            title=f"Bank Transaction Report",
            message=f"Your report is available for download below.",
            success=True)
        await msg.edit(embed=rept_embed)
        await ctx.send(file=discord.File(rpfile))

    @app_command_group_bank.command(name="transactions",
        description="Export Bank Transactions to Excel.")
    @app_commands.check(is_coleader_or_bank_admin)
    @app_commands.autocomplete(select_account=autocomplete_eligible_accounts)
    @app_commands.describe(
        select_account="Select an Account to view.")
    async def app_command_bank_transactions(self,interaction:discord.Interaction,select_account:str):

        await interaction.response.defer()

        if select_account in ['current','sweep','reserve']:
            if not is_bank_admin(interaction):
                return await interaction.followup.send("You don't have permission to do this.")
            account = MasterAccount(select_account)
        
        else:
            try:
                clan = await self.client.fetch_clan(select_account)
            except InvalidAbbreviation as exc:
                return await interaction.followup.send(exc.message)
            check_permissions = True if (is_bank_admin(interaction) or interaction.user.id == clan.leader or interaction.user.id in clan.coleaders) else False

            if not check_permissions:
                return await interaction.followup.send("You don't have permission to do this.")
            account = ClanAccount(clan.tag)
        
        embed = await clash_embed(
            context=interaction,
            message=f"{EmojisUI.LOADING} Please wait..."
            )
        msg = await interaction.followup.send(embed=embed,wait=True)
        
        rpfile = await account.export() 
        if not rpfile:
            return await msg.edit("There were no transactions to report.")
           
        rept_embed = await clash_embed(
            context=interaction,
            title=f"Bank Transaction Report",
            message=f"Your report is available for download below.",
            success=True)
        await msg.edit(embed=rept_embed)
        await interaction.followup.send(file=discord.File(rpfile))
    
    ##################################################
    ### BALANCE
    ##################################################
    @command_group_bank.command(name="deposit")
    @commands.guild_only()
    @commands.check(is_bank_admin)
    async def subcommand_bank_deposit(self,ctx:commands.Context,account_type_or_clan_abbreviation:str,amount:int):
        """
        Deposit Amount to a Global or Clan Bank Account.
        """
        
        if account_type_or_clan_abbreviation in ['current']:
            await self.current_account.deposit(
                amount=amount,
                user_id=ctx.author.id,
                comment=f"Manual Deposit."
                )
        
        elif account_type_or_clan_abbreviation in ['sweep']:
            await self.sweep_account.deposit(
                amount=amount,
                user_id=ctx.author.id,
                comment=f"Manual Deposit."
                )
        
        elif account_type_or_clan_abbreviation in ['reserve']:
            await self.reserve_account.deposit(
                amount=amount,
                user_id=ctx.author.id,
                comment=f"Manual Deposit."
                )
            
        else:
            try:
                clan = await self.client.from_clan_abbreviation(account_type_or_clan_abbreviation)
            except InvalidAbbreviation as exc:
                return await ctx.reply(exc.message)
            else:
                await clan.bank_account.deposit(
                    amount=amount,
                    user_id=ctx.author.id,
                    comment=f"Manual Deposit."
                    )        
        await ctx.tick()
    
    @app_command_group_bank.command(name="deposit",
        description="[Bank Admin only] Deposit Amount to a Global or Clan Bank Account.")
    @app_commands.check(is_bank_admin)
    @app_commands.autocomplete(select_account=autocomplete_eligible_accounts)
    @app_commands.describe(
        select_account="Select an Account to deposit.",
        amount="The amount to deposit.")
    async def app_command_bank_deposit(self,interaction:discord.Interaction,select_account:str,amount:int):
        
        await interaction.response.defer(ephemeral=True)

        if select_account in ['current']:
            await self.current_account.deposit(
                amount=amount,
                user_id=interaction.user.id,
                comment=f"Manual Deposit."
                )
            return await interaction.followup.send(f"Deposited {amount:,} to Current Account.",ephemeral=True)
        
        elif select_account in ['sweep']:
            await self.sweep_account.deposit(
                amount=amount,
                user_id=interaction.user.id,
                comment=f"Manual Deposit."
                )
            return await interaction.followup.send(f"Deposited {amount:,} to Sweep Account.",ephemeral=True)
        
        elif select_account in ['reserve']:
            await self.reserve_account.deposit(
                amount=amount,
                user_id=interaction.user.id,
                comment=f"Manual Deposit."
                )
            return await interaction.followup.send(f"Deposited {amount:,} to Reserve Account.",ephemeral=True)
            
        else:
            try:
                clan = await self.client.fetch_clan(select_account)
            except InvalidAbbreviation as exc:
                return await interaction.followup.send(exc.message,ephemeral=True)
            else:
                await clan.bank_account.deposit(
                    amount=amount,
                    user_id=interaction.user.id,
                    comment=f"Manual Deposit."
                    )
                return await interaction.followup.send(f"Deposited {amount:,} to {clan.title}.",ephemeral=True)
                
    ##################################################
    ### WITHDRAW
    ##################################################    
    @command_group_bank.command(name="withdraw")
    @commands.guild_only()
    @commands.check(is_bank_admin)
    async def subcommand_bank_withdraw(self,ctx:commands.Context,account_type_or_clan_abbreviation:str,amount:int):
        """
        Withdraw Amount from a Global or Clan Bank Account.
        """
        
        if account_type_or_clan_abbreviation in ['current']:
            await self.current_account.withdraw(
                amount=amount,
                user_id=ctx.author.id,
                comment=f"Manual Withdrawal."
                )
        
        elif account_type_or_clan_abbreviation in ['sweep']:
            await self.sweep_account.withdraw(
                amount=amount,
                user_id=ctx.author.id,
                comment=f"Manual Withdrawal."
                )
        
        elif account_type_or_clan_abbreviation in ['reserve']:
            await self.reserve_account.withdraw(
                amount=amount,
                user_id=ctx.author.id,
                comment=f"Manual Withdrawal."
                )
            
        else:
            try:
                clan = await self.client.from_clan_abbreviation(account_type_or_clan_abbreviation)
            except InvalidAbbreviation as exc:
                return await ctx.reply(exc.message)
            else:
                await clan.bank_account.withdraw(
                    amount=amount,
                    user_id=ctx.author.id,
                    comment=f"Manual Withdrawal."
                    )            
        await ctx.tick()
    
    @app_command_group_bank.command(name="withdraw",
        description="[Bank Admin only] Withdraw Amount from a Global or Clan Bank Account.")
    @app_commands.check(is_bank_admin)
    @app_commands.autocomplete(select_account=autocomplete_eligible_accounts)
    @app_commands.describe(
        select_account="Select an Account to withdraw.",
        amount="The amount to withdraw.")
    async def app_command_bank_deposit(self,interaction:discord.Interaction,select_account:str,amount:int):
        
        await interaction.response.defer(ephemeral=True)

        if select_account in ['current']:
            await self.current_account.withdraw(
                amount=amount,
                user_id=interaction.user.id,
                comment=f"Manual Withdrawal."
                )
            return await interaction.followup.send(f"Withdrew {amount:,} from Current Account.",ephemeral=True)
        
        elif select_account in ['sweep']:
            await self.sweep_account.withdraw(
                amount=amount,
                user_id=interaction.user.id,
                comment=f"Manual Withdrawal."
                )
            return await interaction.followup.send(f"Withdrew {amount:,} from Sweep Account.",ephemeral=True)
        
        elif select_account in ['reserve']:
            await self.reserve_account.withdraw(
                amount=amount,
                user_id=interaction.user.id,
                comment=f"Manual Withdrawal."
                )
            return await interaction.followup.send(f"Withdrew {amount:,} from Reserve Account.",ephemeral=True)
            
        else:
            try:
                clan = await self.client.fetch_clan(select_account)
            except InvalidAbbreviation as exc:
                return await interaction.followup.send(exc.message,ephemeral=True)
            else:
                await clan.bank_account.withdraw(
                    amount=amount,
                    user_id=interaction.user.id,
                    comment=f"Manual Withdrawal."
                    )
                return await interaction.followup.send(f"Withdrew {amount:,} from {clan.title}.",ephemeral=True)
    
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
        if account_type_or_clan_abbreviation in ['current','sweep','reserve']:
            if not is_bank_admin(ctx):
                return await ctx.reply("You don't have permission to do this.")
            
            account = MasterAccount(account_type_or_clan_abbreviation)
            await account.withdraw(
                amount=amount,
                user_id=ctx.author.id,
                comment=f"Reward transfer to {user.name} {user.id}."
                )                 
        else:
            try:
                clan = await self.client.from_clan_abbreviation(account_type_or_clan_abbreviation)
            except InvalidAbbreviation as exc:
                return await ctx.reply(exc.message)
            
            check_permissions = True if (is_bank_admin(ctx) or ctx.author.id == clan.leader or ctx.author.id in clan.coleaders) else False
            if not check_permissions:
                return await ctx.reply("You don't have permission to do this.")
            
            account = ClanAccount(clan.tag)
            await account.withdraw(
                amount=amount,
                user_id=ctx.author.id,
                comment=f"Reward transfer to {user.name} {user.id}."
                )        
        await bank.deposit_credits(user,amount)
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

        if not user and not role:
            return await interaction.followup.send(f"You need to provide at least a User or a Role.")

        if select_account in ['current','sweep','reserve']:
            if not is_bank_admin(interaction):
                return await interaction.followup.send("You don't have permission to do this.",ephemeral=True)
            account = MasterAccount(select_account)
            
        else:
            clan = await self.client.fetch_clan(select_account)
            check_permissions = True if (is_bank_admin(interaction) or interaction.user.id == clan.leader or interaction.user.id in clan.coleaders) else False
            if not check_permissions:
                return await interaction.followup.send("You don't have permission to do this.",ephemeral=True)
            account = ClanAccount(clan.tag)
        
        count = 0
        if role:            
            iter_members = AsyncIter(role.members)
            async for member in iter_members:
                await account.withdraw(
                    amount=amount,
                    user_id=interaction.user.id,
                    comment=f"Reward transfer to {member.name} {member.id}."
                    )
                await bank.deposit_credits(member,amount)
                count += 1
        
        if user:
            await account.withdraw(
                amount=amount,
                user_id=interaction.user.id,
                comment=f"Reward transfer to {user.name} {user.id}."
                )
            await bank.deposit_credits(user,amount)
            count += 1
        
        if count == 1 and user:
            return await interaction.followup.send(f"Rewarded {user.mention} with {amount:,}.",ephemeral=True)
        else:
            return await interaction.followup.send(f"Distributed {amount:,} to {count} members.",ephemeral=True)
        
    ##################################################
    ### USER INVENTORY
    ##################################################
    @commands.command(name="inventory")
    @commands.guild_only()
    async def command_user_inventory(self,ctx:commands.Context):
        """
        Display your inventory.

        Your inventory, like your Bank Balances, are considered global and will contain items from different server stores.
        """

        inventory = UserInventory(ctx.author)
        embed = await inventory.get_embed(ctx)
        await ctx.reply(embed=embed)
    
    @app_commands.command(
        name="inventory",
        description="Display your inventory."
        )
    @app_commands.guild_only()
    async def app_command_user_inventory(self,interaction:discord.Interaction):
        
        await interaction.response.defer()

        inventory = UserInventory(interaction.user)
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

        await ctx.reply(f"For a better experience, use the Slash Command `/gift` to do this action.")
    
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
        
        item = ShopItem.get_by_id(item)

        inventory = UserInventory(interaction.user)
        gift = await inventory.gift_item(item,user)
        if not gift:
            return await interaction.followup.send(f"You don't have that item.",ephemeral=True)
        return await interaction.followup.send(f"Yay! You've gifted {user.mention} 1x **{gift.name}**.",ephemeral=True)

    ##################################################
    ### USER REDEEM
    ##################################################
    @commands.command(name="redeem")
    @commands.guild_only()
    async def command_item_redeem(self,ctx:commands.Context):
        """
        Redeems an item from your inventory!
        """

        inv = UserInventory(ctx.author)
        inv_check = len([i for i in inv.inventory if i.guild_id == ctx.guild.id]) > 0

        if not inv_check:
            return await ctx.reply("You don't have any items to redeem from this server.")
        
        # Assassins Guild
        if ctx.guild.id == 1132581106571550831:
            role = ctx.guild.get_role(1163325808941727764)
            await ctx.author.add_roles(role)
            return await ctx.reply(f"Please open a ticket in <#1148464443676700693> to redeem your item!")
        
        # ARIX
        if ctx.guild.id == 688449973553201335:
            role = ctx.guild.get_role(1163327086262485094)
            await ctx.author.add_roles(role)
            return await ctx.reply(f"Please open a ticket in <#798930079111053372> to redeem your item!")

    @app_commands.command(
        name="redeem",
        description="Redeems an item from your inventory!"
        )
    @app_commands.guild_only()
    async def app_command_redeem_user(self,interaction:discord.Interaction):        
        
        await interaction.response.defer()

        member = interaction.guild.get_member(interaction.user.id)

        inv = UserInventory(member)
        inv_check = len([i for i in inv.inventory if i.guild_id == interaction.guild.id]) > 0

        if not inv_check:
            return await interaction.followup.send("You don't have any items to redeem from this server.")
        
        # Assassins Guild
        if interaction.guild.id == 1132581106571550831:
            role = interaction.guild.get_role(1163325808941727764)
            await member.add_roles(role)
            return await interaction.followup.send(f"Please open a ticket in <#1148464443676700693> to redeem your item!")
        
        # ARIX
        if interaction.guild.id == 688449973553201335:
            role = interaction.guild.get_role(1163327086262485094)
            await member.add_roles(role)
            return await interaction.followup.send(f"Please open a ticket in <#798930079111053372> to redeem your item!")
    
    ##################################################
    ### STORE MANAGER
    ##################################################    
    @commands.command(name="shopmanager")
    @commands.admin()
    @commands.guild_only()
    async def command_user_store_manager(self,ctx:commands.Context):
        """
        Manage the Store for this Guild.
        """

        store = StoreManager(ctx)
        await store.start()
    
    @app_commands.command(
        name="shop-manager",
        description="Open the Shop Manager. Equivalent to [p]`shopmanager`."
        )
    @app_commands.guild_only()
    @app_commands.check(is_admin)
    async def app_command_store_manager(self,interaction:discord.Interaction):
        
        await interaction.response.defer()

        store = StoreManager(interaction)
        await store.start()
    
    ##################################################
    ### SHOP ITEM GROUP
    ##################################################    
    @commands.group(name="shopitem")
    @commands.admin()
    @commands.guild_only()
    async def command_group_shop_item(self,ctx:commands.Context):
        """
        Group Command to help manage Shop Items.
        """
        if not ctx.invoked_subcommand:
            pass
    
    app_command_group_shopitem = app_commands.Group(
        name="shop-item",
        description="Group for Shop Item commands. Equivalent to [p]shopitem.",
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

        await ctx.reply(f"For a better experience, use the Slash Command `/shop-item distribute` to do this action.")
    
    @app_command_group_shopitem.command(
        name="distribute",
        description="Administratively distribute an item to a specified user."
        )
    @app_commands.guild_only()
    @app_commands.check(is_admin)
    @app_commands.autocomplete(item=autocomplete_distribute_items)
    @app_commands.describe(
        item="Select an item to distribute. Only Basic items can be distributed.",
        user="Select a user to distribute to."
        )
    async def app_command_distribute_item(self,interaction:discord.Interaction,item:str,user:discord.Member):        
        await interaction.response.defer(ephemeral=True)

        if user.id == interaction.user.id:
            return await interaction.followup.send("You can't give items to yourself!",ephemeral=True)
        if user.bot:
            return await interaction.followup.send("You can't give items to bots!",ephemeral=True)
        
        item = ShopItem.get_by_id(item)

        inventory = UserInventory(user)
        await inventory.add_item_to_inventory(item)

        return await interaction.followup.send(f"1x **{item.name}** has been added to {user.mention}'s inventory.",ephemeral=True)

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

        await ctx.reply(f"For a better experience, use the Slash Command `/shop-item redeem` to do this action.")
    
    @app_command_group_shopitem.command(
        name="redeem",
        description="Redeems an item from a user's inventory."
        )
    @app_commands.guild_only()
    @app_commands.check(is_admin)
    @app_commands.autocomplete(item=autocomplete_distribute_items)
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
        
        item = ShopItem.get_by_id(item)
        inventory = UserInventory(user)

        if not inventory.has_item(item):
            return await interaction.followup.send(f"{user.mention} doesn't have that item.")

        await inventory.remove_item_from_inventory(item)
        await interaction.followup.send(f"1x **{item.name}** has been redeemed from {user.mention}'s inventory.")
    
    ##################################################
    ### SHOP ITEM / DELETE
    ################################################## 
    @command_group_shop_item.command(name="delete")   
    @commands.admin()
    @commands.guild_only()
    async def subcommand_shop_item_delete(self,ctx:commands.Context,item_id:str):
        """
        Delete a Shop Item.

        Uses the system ID to identify Shop Items. If you're not sure what this is, use the Slash Command.
        """
        item = ShopItem.get_by_id(item_id)
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
        item = ShopItem.get_by_id(item)
        if not item:
            return await interaction.followup.send("I couldn't find that item.",ephemeral=True)
        await item.delete()
        await interaction.followup.send("Item deleted.",ephemeral=True)
    
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
        item = ShopItem.get_by_id(item_id)
        if not item:
            return await ctx.reply("I couldn't find that item.")
        
        item.stock += amount
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
        item = ShopItem.get_by_id(item)
        if not item:
            return await interaction.followup.send("I couldn't find that item.",ephemeral=True)
        item.stock += amount
        await interaction.followup.send(f"Restocked {item} by {amount}. New stock: {item.stock}.",ephemeral=True)