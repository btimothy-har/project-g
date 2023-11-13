import asyncio
import pendulum
import xlsxwriter

from functools import cached_property
from redbot.core.utils import AsyncIter
from coc_main.api_client import BotClashClient
from coc_main.cog_coc_client import ClashOfClansClient, aClan

from .transaction import db_BankTransaction
from mongoengine import *

bot_client = BotClashClient()

class BankAccount():    
    def __init__(self,account_id:str):
        self.id = account_id
    
    @property
    def bot_client(self) -> BotClashClient:
        return bot_client

    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    @cached_property
    def balance(self) -> int:
        return 0
    
    async def get_balance(self):
        def _query_balance():
            transactions = db_BankTransaction.objects(account=self.id)
            return transactions.sum('amount')
        self.balance = await bot_client.run_in_thread(_query_balance)
    
    async def deposit(self,amount:int,user_id:int=None,comment:str=None):
        def _save_to_db():
            transaction = db_BankTransaction(
                account=self.id,
                amount=amount,
                timestamp=pendulum.now().int_timestamp,
                user=user_id if user_id else 99,
                comment=comment
                )
            transaction.save()
        
        if self._master_lock.locked():
            async with self._master_lock:
                await asyncio.sleep(0.1)
        
        async with self._lock:
            await bot_client.run_in_thread(_save_to_db)            
            self.balance += amount

    async def withdraw(self,amount:int,user_id:int=None,comment:str=None):
        def _save_to_db():
            transaction = db_BankTransaction(
                account=self.id,
                amount=amount * -1,
                timestamp=pendulum.now().int_timestamp,
                user=user_id if user_id else 99,
                comment=comment
                )
            transaction.save()
        
        if self._master_lock.locked():
            async with self._master_lock:
                await asyncio.sleep(0.1)

        async with self._lock:
            await bot_client.run_in_thread(_save_to_db)
            self.balance -= amount
    
    async def admin_adjust(self,amount:int,user_id:int=None,comment:str=None):
        def _save_to_db():
            transaction = db_BankTransaction(
                account=self.id,
                amount=amount,
                timestamp=pendulum.now().int_timestamp,
                user=user_id if user_id else 99,
                comment=comment
                )
            transaction.save()
        
        async with self._lock:
            await bot_client.run_in_thread(_save_to_db)
            self.balance += amount
    
    async def query_transactions(self):
        def _query_transactions():
            transactions = db_BankTransaction.objects(
                (Q(account=self.id) & Q(timestamp__gte=cut_off))
                )
            return [t for t in transactions]
        
        cut_off = pendulum.now().subtract(months=1).int_timestamp
        transactions = await bot_client.run_in_thread(_query_transactions)

        if len(transactions) == 0:
            return None
        
        return transactions

    async def export(self,transactions):        
        report_file = bot_client.bot.coc_bank_path + '/' + f'BankTransactions_{pendulum.now().format("YYYYMMDDHHmmss")}.xlsx'

        workbook = xlsxwriter.Workbook(report_file)
        worksheet = workbook.add_worksheet('Bank Transactions')

        rpt_transactions = sorted(transactions,key=lambda t:t.timestamp,reverse=True)
        headers = ['Timestamp','User','Account','Debit','Credit','Comment']

        row = 0
        col = 0
        async for h in AsyncIter(headers):
            worksheet.write(row,col,h)
            col += 1

        async for t in AsyncIter(rpt_transactions):
            col = 0
            row += 1

            transaction_user = bot_client.bot.get_user(t.user)

            m_data = []
            m_data.append(pendulum.from_timestamp(t.timestamp).to_iso8601_string())
            if t.user == bot_client.bot.user.id:
                m_data.append('System')
            else:
                m_data.append(transaction_user.name if transaction_user else t.user)
                
            m_data.append(t.account)
            if t.amount < 0:
                m_data.append(t.amount * -1)
                m_data.append('')
            else:
                m_data.append('')
                m_data.append(t.amount)
            m_data.append(t.comment)

            for d in m_data:
                worksheet.write(row,col,d)
                col += 1
        
        workbook.close()
        return report_file
        
class ClanAccount(BankAccount):
    _cache = {}
    def __new__(cls,clan_tag):
        if clan_tag not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[clan_tag] = instance
        return cls._cache[clan_tag]
    
    def __init__(self,clan_tag):
        super().__init__(clan_tag)
        if self._is_new:
            self._master_lock = asyncio.Lock()
            self._lock = asyncio.Lock()
    
    @classmethod
    async def get(cls,clan:aClan):
        if not clan.is_alliance_clan:
            raise ValueError("Invalid Clan. Clan must be an Alliance clan.")
        
        c = cls(clan.tag)
        if c._is_new:
            await c.get_balance()
        c._is_new = False
        return c
   
class MasterAccount(BankAccount):
    _cache = {}
    def __new__(cls,id:str):
        if id not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[id] = instance
        return cls._cache[id]
    
    def __init__(self,id:str):
        if id not in ['current','sweep','reserve']:
            raise ValueError("Invalid Master Account ID.")
        super().__init__(id)

        if self._is_new:
            self._master_lock = asyncio.Lock()
            self._lock = asyncio.Lock()
    
    @classmethod
    async def get(cls,id:str):
        c = cls(id)
        if c._is_new:
            await c.get_balance()
        c._is_new = False
        return c