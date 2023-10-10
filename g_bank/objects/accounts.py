import asyncio
import pendulum
import xlsxwriter

from redbot.core.utils import AsyncIter
from coc_main.api_client import BotClashClient
from coc_main.cog_coc_client import ClashOfClansClient

from .transaction import db_BankTransaction
from mongoengine import *

bot_client = BotClashClient()

class BankAccount():
    def __init__(self,account_id):
        self.id = account_id
    
    @property
    def bot_client(self) -> BotClashClient:
        return bot_client

    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    @property
    def balance(self):
        if self._balance == 0:
            self._balance = db_BankTransaction.objects(account=self.id).sum('amount')
        return self._balance
    
    async def deposit(self,amount:int,user_id:int=None,comment:str=None):
        async with self.lock:
            transaction = db_BankTransaction(
                account=self.id,
                amount=amount,
                timestamp=pendulum.now().int_timestamp,
                user=user_id if user_id else 99,
                comment=comment
                )
            transaction.save()
            self._balance = 0

    async def withdraw(self,amount:int,user_id:int=None,comment:str=None):
        async with self.lock:
            transaction = db_BankTransaction(
                account=self.id,
                amount=amount * -1,
                timestamp=pendulum.now().int_timestamp,
                user=user_id if user_id else 99,
                comment=comment
                )
            transaction.save()
            self._balance = 0
    
    async def admin_adjust(self,amount:int,user_id:int=None,comment:str=None):
        transaction = db_BankTransaction(
            account=self.id,
            amount=amount,
            timestamp=pendulum.now().int_timestamp,
            user=user_id if user_id else 99,
            comment=comment
            )
        transaction.save()
        self._balance = 0
    
    async def export(self):
        cut_off = pendulum.now().subtract(months=3).int_timestamp
        transactions = db_BankTransaction.objects(
            (Q(account=self.id) & Q(timestamp__gte=cut_off))
            )
        
        if len(transactions) == 0:
            return None
        
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
            self.lock = asyncio.Lock()
            self._balance = 0
            self._is_new = False
    
class MasterAccount(BankAccount):
    _cache = {}
    def __new__(cls,id):
        if id not in cls._cache:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._cache[id] = instance
        return cls._cache[id]
    
    def __init__(self,id):
        if id not in ['current','sweep','reserve']:
            raise ValueError("Invalid Master Account ID.")
        super().__init__(id)
        if self._is_new:
            self.lock = asyncio.Lock()
            self._balance = 0
            self._is_new = False