import asyncio
import pendulum
import xlsxwriter

from collections import defaultdict
from redbot.core.utils import AsyncIter
from async_property import AwaitLoader
from coc_main.api_client import BotClashClient
from coc_main.cog_coc_client import ClashOfClansClient, aClan

from .transaction import db_BankTransaction
from mongoengine import *

bot_client = BotClashClient()

class BankAccount(AwaitLoader):
    _master_locks = defaultdict(asyncio.Lock)
    _locks = defaultdict(asyncio.Lock)

    def __init__(self,account_id:str):
        self.id = account_id
        self.balance = 0
    
    @property
    def bot_client(self) -> BotClashClient:
        return bot_client
    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")    
    @property
    def _master_lock(self) -> asyncio.Lock:
        return self._master_locks[self.id]    
    @property
    def _lock(self) -> asyncio.Lock:
        return self._locks[self.id]
    
    async def load(self):
        if self.balance == 0:
            q_pipeline = [
                {'$match': {'account': self.id,'amount': {'$ne': 0}}},
                {'$group': {'_id': None, 'total_amount': {'$sum': '$amount'}}}
                ]
            balance_query = await bot_client.coc_db.db__bank_transaction.aggregate(q_pipeline).to_list(length=None)
            self.balance = balance_query[0]['total_amount'] if len(balance_query) > 0 else 0
    
    async def deposit(self,amount:int,user_id:int=None,comment:str=None):
        if self._master_lock.locked():
            async with self._master_lock:
                await asyncio.sleep(0.1)        
        async with self._lock:
            await bot_client.coc_db.db__bank_transaction.insert_one(
                {
                    'account': self.id,
                    'amount': amount,
                    'timestamp': pendulum.now().int_timestamp,
                    'user': user_id if user_id else 99,
                    'comment': comment
                }
            )
            self.balance += amount

    async def withdraw(self,amount:int,user_id:int=None,comment:str=None):
        if self._master_lock.locked():
            async with self._master_lock:
                await asyncio.sleep(0.1)

        async with self._lock:
            await bot_client.coc_db.db__bank_transaction.insert_one(
                {
                    'account': self.id,
                    'amount': amount * -1,
                    'timestamp': pendulum.now().int_timestamp,
                    'user': user_id if user_id else 99,
                    'comment': comment
                }
            )
            self.balance -= amount
    
    async def admin_adjust(self,amount:int,user_id:int=None,comment:str=None):
        async with self._lock:
            await bot_client.coc_db.db__bank_transaction.insert_one(
                {
                    'account': self.id,
                    'amount': amount,
                    'timestamp': pendulum.now().int_timestamp,
                    'user': user_id if user_id else 99,
                    'comment': comment
                }
            )            
    
    async def query_transactions(self):        
        cut_off = pendulum.now().subtract(days=30).int_timestamp
        transactions = await bot_client.coc_db.db__bank_transaction.find(
            {'account': self.id,'timestamp': {'$gte': cut_off},'amount': {'$ne': 0}}
            ).to_list(length=10000)

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

        a_iter = AsyncIter(rpt_transactions)
        async for t in a_iter:
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

    def __new__(cls,clan:aClan):
        if clan.tag not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[clan.tag] = instance
        return cls._cache[clan.tag]
    
    def __init__(self,clan:aClan):
        if not clan.is_alliance_clan:
            raise ValueError("Invalid Clan. Clan must be an Alliance clan.")
        super().__init__(clan.tag)
        self.is_new = False
   
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
        self._is_new = False