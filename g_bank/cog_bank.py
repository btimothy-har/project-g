import os
import discord
import pendulum
import asyncio

from redbot.core import Config, commands, app_commands, bank
from redbot.core.data_manager import cog_data_path
from redbot.core.utils import AsyncIter

from mee6rank.mee6rank import Mee6Rank

from coc_data.objects.players.player import aPlayer
from coc_data.objects.clans.clan import aClan
from coc_data.objects.events.clan_war import aWarPlayer
from coc_data.objects.events.raid_weekend import aRaidMember
from coc_data.constants.coc_constants import *

from coc_data.utilities.utils import *
from coc_data.utilities.components import *
from coc_data.exceptions import *

from coc_commands.helpers.autocomplete import *

from coc_commands.helpers.components import *

from .objects.accounts import MasterAccount, ClanAccount
from .components import *
from .checks import *
from .autocomplete import *

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

    __author__ = "bakkutteh"
    __version__ = "1.0.1"

    def __init__(self,bot):
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
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"

    @property
    def client(self):
        return self.bot.get_cog("ClashOfClansClient").client
    
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
        
        while True:
            try:
                alliance_clans = self.client.cog.get_alliance_clans()
            except CacheNotReady:
                await asyncio.sleep(5)
                continue
            else:
                break
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
                                  
        while True:
            try:
                alliance_members = self.client.cog.get_members_by_season()
            except CacheNotReady:
                await asyncio.sleep(5)
                continue
            else:
                break
        await self.current_account.deposit(
            amount=round(len(alliance_members) * 25000),
            user_id=self.bot.user.id,
            comment=f"EOS new funds: {len(alliance_members)} members."
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
            comment = f"Townhall Bonus for {player.name} ({player.tag}): TH{cached_value} to TH{player.town_hall}."
            )
    
    async def member_hero_upgrade_reward(self,player:aPlayer,cached_value:int):
        if not self.use_rewards:
            return
        if not player.is_member:
            return
        member = self.bot.get_user(player.discord_user)
        if not member:
            return
        
        reward = 1000 * (player.hero_strength - cached_value)
        await bank.deposit_credits(member,reward)
        await self.current_account.withdraw(
            amount = reward,
            user_id = self.bot.user.id,
            comment = f"Hero Bonus for {player.name} ({player.tag}): {cached_value} to {player.hero_strength}"
            )
    
    async def member_legend_rewards(self):
        if not self.use_rewards:
            return
        
        reward_per_trophy = 20

        while True:
            try:
                alliance_members = self.client.cog.get_members_by_season()
            except CacheNotReady:
                await asyncio.sleep(5)
                continue
            else:
                break
        
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
        
        p = await aPlayer.create(player.tag)
        member = self.bot.get_user(p.discord_user)
        if not member:
            return
        
        if player.unused_attacks > 0:
            balance = await bank.get_balance(member)
            penalty = round(min(balance,max(100,0.05 * balance) * player.unused_attacks))
            await bank.withdraw_credits(member,penalty)
            await self.current_account.deposit(
                amount = penalty,
                user_id = self.bot.user.id,
                comment = f"Clan War Penalty for {p.name} ({p.tag})."
                )

        membership_multiplier = 1 if p.is_member else non_member_multiplier
        participation = 50
        performance = (50 * player.star_count) + (300 * len([a for a in player.attacks if a.is_triple]))
        result = 100 if player.clan.result == WarResult.WON else 0

        total_reward = round((participation + performance + result) * membership_multiplier)
        await bank.deposit_credits(member,total_reward)
        await self.current_account.withdraw(
            amount = total_reward,
            user_id = self.bot.user.id,
            comment = f"Clan War Reward for {p.name} ({p.tag})."
            )
    
    async def raid_bank_rewards(self,player:aRaidMember):
        if not self.use_rewards:
            return
        
        p = await aPlayer.create(player.tag)
        member = self.bot.get_user(p.discord_user)
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
                comment = f"Raid Weekend Penalty for {p.name} ({p.tag})."
                )
        
        membership_multiplier = 1 if p.is_member else non_member_multiplier

        total_reward = round((20 * (sum([a.new_destruction for a in player.attacks]) // 5)) * membership_multiplier)
        await bank.deposit_credits(member,total_reward)
        await self.current_account.withdraw(
            amount = total_reward,
            user_id = self.bot.user.id,
            comment = f"Raid Weekend Reward for {p.name} ({p.tag})."
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
    @commands.command(name="balance",aliases=['bal'])
    @commands.guild_only()
    async def command_bank_balance(self,ctx:commands.Context,clan_abbreviation:str=None):
        """
        Display your current Bank Balance (or Clan's balance).

        Clan balances are only usable by Clan Leaders and Co-Leaders.
        """
        currency = await bank.get_currency_name()

        clan = None
        if clan_abbreviation:
            try:
                clan = await aClan.from_abbreviation(clan_abbreviation)
            except InvalidAbbreviation as exc:
                clan = None
            
            check_permissions = True if (is_bank_admin(ctx) or ctx.author.id == clan.leader or ctx.author.id in clan.coleaders) else False
            if not check_permissions:
                clan = None
        
        if clan:
            embed = await clash_embed(
                context=ctx,
                message=f"**{clan.title}** has **{clan.balance:,} {currency}**.",
                timestamp=pendulum.now()
                )
            return await ctx.reply(embed=embed)

        member = aMember(ctx.author.id,ctx.guild.id)

        embed = await clash_embed(
            context=ctx,
            message=f"You have **{await bank.get_balance(ctx.author):,} {currency}** (Global Rank: #{await bank.get_leaderboard_position(member.discord_member)}).\nNext payday: "
                + (f"<t:{member.last_payday.add(days=1).int_timestamp}:R>" if member.last_payday and member.last_payday.add(days=1) > pendulum.now() else "Now! Use `payday` to claim your credits!"),
            timestamp=pendulum.now()
            )
        await ctx.reply(embed=embed)
    
    @app_commands.command(name="balance",
        description="Display your current Bank Balance.")
    @app_commands.guild_only()
    @app_commands.autocomplete(select_clan=autocomplete_clans_coleader)
    @app_commands.describe(
        select_clan="Select a Clan to view balances for. Only usable by Clan Leaders and Co-Leaders.")
    async def app_command_bank_balance(self,interaction:discord.Interaction,select_clan:str=None):
        
        await interaction.response.defer()
        currency = await bank.get_currency_name()

        clan = None
        if select_clan:
            try:
                clan = await aClan.create(select_clan)
            except:
                clan = None
            
            check_permissions = True if (is_bank_admin(interaction) or interaction.user.id == clan.leader or interaction.user.id in clan.coleaders) else False
            if not check_permissions:
                clan = None
        
        if clan:
            embed = await clash_embed(
                context=interaction,
                message=f"**{clan.title}** has **{clan.balance:,} {currency}**.",
                timestamp=pendulum.now()
                )
            return await interaction.followup.send(embed=embed)        

        member = aMember(interaction.user.id,interaction.guild.id)

        embed = await clash_embed(
            context=interaction,
            message=f"You have **{await bank.get_balance(member.discord_member):,} {currency}** (Global Rank: #{await bank.get_leaderboard_position(member.discord_member)}).\nNext payday: "
                + (f"<t:{member.last_payday.add(days=1).int_timestamp}:R>" if member.last_payday and member.last_payday.add(days=1) > pendulum.now() else "Now! Use `payday` to claim your credits!"),
            timestamp=pendulum.now()
            )
        await interaction.followup.send(embed=embed)
    
    ##################################################
    ### PAYDAY
    ##################################################    
    @commands.command(name="payday")
    @commands.guild_only()
    @commands.check(is_bank_server)
    async def command_payday(self,ctx:commands.Context):
        """
        Payday!

        Receive a set amount of money every 24 hours.
        """
        member = aMember(ctx.author.id,ctx.guild.id)

        is_booster = True if member.discord_member.premium_since else False
        # for g in self.eligible_boost_servers:
        #     m = aMember(ctx.author.id,g)
        #     if m.discord_member.premium_since:
        #         is_booster = True
        #         break

        last_payday = member.last_payday
        if last_payday:
            if last_payday.add(days=1) > pendulum.now():
                return await ctx.reply(f"You can claim your next payday <t:{last_payday.add(days=1).int_timestamp}:R>.")

        currency = await bank.get_currency_name()
        try:
            mee6user = await Mee6Rank._get_player(
                ctx.bot.get_cog("Mee6Rank"),
                ctx.author,
                get_avatar=False
                )
        except:
            mee6user = None

        basic_payout = 50
        xp_bonus = 10 * (mee6user.level // 10 if mee6user else 0)
        boost_bonus = 1000 if is_booster else 0

        total_payout = basic_payout + xp_bonus + boost_bonus
        await bank.deposit_credits(ctx.author,total_payout)

        member.last_payday = pendulum.now().int_timestamp

        embed = await clash_embed(
            context=ctx,
            message=f"Here's some money, {ctx.author.mention}! You received:"
                + f"\n\nBase Payout: {basic_payout} {currency}"
                + f"\nXP Bonus: {xp_bonus:,} {currency}"
                + f"\nNitro Bonus: {boost_bonus:,} {currency}"
                + f"\n\nTotal: {total_payout:,} {currency}. You now have: {await bank.get_balance(ctx.author):,} {currency}.",
            success=True,
            timestamp=pendulum.now()
            )        
        return await ctx.send(embed=embed)

    @app_commands.command(name="payday",
        description="Receive a set amount of money every 24 hours.")
    @app_commands.guild_only()
    @app_commands.check(is_bank_server)
    async def app_command_payday(self,interaction:discord.Interaction):

        await interaction.response.defer()        
        member = aMember(interaction.user.id,interaction.guild.id)

        last_payday = member.last_payday
        if last_payday:
            if last_payday.add(days=1) > pendulum.now():
                return await interaction.followup.send(f"You can claim your next payday <t:{last_payday.add(days=1).int_timestamp}:R>.")

        currency = await bank.get_currency_name()
        try:
            mee6user = await Mee6Rank._get_player(
                self.bot.get_cog("Mee6Rank"),
                member.discord_member,
                get_avatar=False
                )
        except:
            mee6user = None

        basic_payout = 50
        xp_bonus = 10 * (mee6user.level // 10 if mee6user else 0)
        boost_bonus = 1000 if member.discord_member.premium_since else 0

        total_payout = basic_payout + xp_bonus + boost_bonus
        await bank.deposit_credits(member.discord_member,total_payout)

        member.last_payday = pendulum.now().int_timestamp

        embed = await clash_embed(
            context=interaction,
            message=f"Here's some money, {member.mention}! You received:"
                + f"\n\nBase Payout: {basic_payout} {currency}"
                + f"\nXP Bonus: {xp_bonus:,} {currency}"
                + f"\nNitro Bonus: {boost_bonus:,} {currency}"
                + f"\n\nTotal: {total_payout:,} {currency}. You now have: {await bank.get_balance(member.discord_member):,} {currency}.",
            success=True,
            timestamp=pendulum.now()
            )        
        return await interaction.followup.send(embed=embed)         
    
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
    @command_group_bank.command(name="globalbal",aliases=['gbal'])
    @commands.guild_only()
    @commands.check(is_bank_admin)
    async def subcommand_bank_global_balances(self,ctx:commands.Context):
        """
        [Bank Admin only] Display Global Account Balances.
        """
        
        currency = await bank.get_currency_name()
        leaderboard = await bank.get_leaderboard()
        if len(leaderboard) == 0:
            total_balance = 0
        else:
            total_balance = sum([account['balance'] for id,account in leaderboard])

        try:
            alliance_members = self.client.cog.get_members_by_season()
        except CacheNotReady:
            alliance_members = []            

        embed = await clash_embed(
            context=ctx,
            title=f"**Guild Bank Accounts**",
            message=f"`{'Current':<10}` {self.current_account.balance:,} {currency}"
                + f"\n`{'Sweep':<10}` {self.sweep_account.balance:,} {currency}"
                + f"\n`{'Reserve':<10}` {self.reserve_account.balance:,} {currency}"
                + f"\n`{'Total':<10}` {total_balance:,} {currency}"
                + f"\n\nNew Monthly Balance (est.): {len(alliance_members) * 25000:,}",
            timestamp=pendulum.now()
            )
        return await ctx.send(embed=embed)

    @app_command_group_bank.command(name="global-balances",
        description="[Bank Admin only] Display Global Account Balances.")
    @app_commands.guild_only()
    @app_commands.check(is_bank_admin)
    async def app_command_global_balances(self,interaction:discord.Interaction):
        
        await interaction.response.defer()

        currency = await bank.get_currency_name()
        leaderboard = await bank.get_leaderboard()
        if len(leaderboard) == 0:
            total_balance = 0
        else:
            total_balance = sum([account['balance'] for id,account in leaderboard])

        try:
            alliance_members = self.client.cog.get_members_by_season()
        except CacheNotReady:
            alliance_members = []            

        embed = await clash_embed(
            context=interaction,
            title=f"**Guild Bank Accounts**",
            message=f"`{'Current':<10}` {self.current_account.balance:,} {currency}"
                + f"\n`{'Sweep':<10}` {self.sweep_account.balance:,} {currency}"
                + f"\n`{'Reserve':<10}` {self.reserve_account.balance:,} {currency}"
                + f"\n`{'Total':<10}` {total_balance:,} {currency}"
                + f"\n\nNew Monthly Balance (est.): {len(alliance_members) * 25000:,}",
            timestamp=pendulum.now()
            )
        return await interaction.followup.send(embed=embed)

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
            try:
                clan = await aClan.from_abbreviation(account_type_or_clan_abbreviation)
            except InvalidAbbreviation as exc:
                return await ctx.reply(exc.message)
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
                clan = await aClan.create(select_account)
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
                clan = await aClan.from_abbreviation(account_type_or_clan_abbreviation)
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
                clan = await aClan.create(select_account)
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
                clan = await aClan.from_abbreviation(account_type_or_clan_abbreviation)
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
                clan = await aClan.create(select_account)
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
    @command_group_bank.command(name="reward")
    @commands.guild_only()
    @commands.check(is_coleader_or_bank_admin)
    async def subcommand_bank_reward(self,ctx:commands.Context,account_type_or_clan_abbreviation:str,user:discord.Member,amount:int):
        """
        Rewards Discord Users with a set amount of money.

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
                clan = await aClan.from_abbreviation(account_type_or_clan_abbreviation)
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
    
    @app_command_group_bank.command(name="reward",
        description="Rewards Discord Users with a set amount of money.")
    @app_commands.check(is_coleader_or_bank_admin)
    @app_commands.autocomplete(select_account=autocomplete_eligible_accounts)
    @app_commands.describe(
        select_account="Select an Account to withdraw the reward from.",
        user="Select a User to reward.",
        amount="The amount to reward.")
    async def app_command_bank_reward(self,interaction:discord.Interaction,select_account:str,user:discord.Member,amount:int):
        
        await interaction.response.defer(ephemeral=True)

        if select_account in ['current','sweep','reserve']:
            if not is_bank_admin(interaction):
                return await interaction.followup.send("You don't have permission to do this.",ephemeral=True)
            account = MasterAccount(select_account)        
        else:
            clan = await aClan.create(select_account)
            check_permissions = True if (is_bank_admin(interaction) or interaction.user.id == clan.leader or interaction.user.id in clan.coleaders) else False
            if not check_permissions:
                return await interaction.followup.send("You don't have permission to do this.",ephemeral=True)            
            account = ClanAccount(clan.tag)     
        
        await account.withdraw(
            amount=amount,
            user_id=interaction.user.id,
            comment=f"Reward transfer to {user.name} {user.id}."
            )
        await bank.deposit_credits(user,amount)
        return await interaction.followup.send(f"Rewarded {user.mention} with {amount:,}.",ephemeral=True)