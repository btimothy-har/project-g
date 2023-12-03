import discord
import random
import asyncio

from redbot.core import bank
from collections import defaultdict

from mongoengine import *
from typing import *

from coc_main.api_client import BotClashClient
from ..exceptions import CannotPurchase

#Available Item Types
#1 Basic
#2 Role
#3 Random
#4 Cash

bot_client = BotClashClient()

class db_ShopItem(Document):
    guild_id = IntField(required=True)
    type = StringField(required=True)
    
    name = StringField(required=True)
    price = IntField(required=True)
    stock = IntField(required=True)
    description = StringField(default="")
    category = StringField(default="")
    buy_message = StringField(default="")

    exclusive_role = BooleanField(default=False)
    required_role = IntField(default=0)
    show_in_store = BooleanField(default=True)
    disabled = BooleanField(default=False)
    
    role_id = IntField(default=0)
    bidirectional_role = BooleanField(default=False)
    
    random_items = ListField(StringField(),default=[])

class ShopItem():
    _locks = defaultdict(asyncio.Lock)

    __slots__ = [
        'id',
        'guild_id',
        'type',
        'name',
        'price',
        '_stock',
        'category',
        'description',
        'buy_message',
        'exclusive_role',
        '_required_role',
        'show_in_store',
        'disabled',
        'role_id',
        'bidirectional_role',
        'random_items'
        ]

    @classmethod
    async def get_by_id(cls,item_id:str) -> Optional['ShopItem']:        
        query = await bot_client.coc_db.db__shop_item.find_one({'_id':item_id})
        if query:
            return cls(query)
        return None

    @classmethod
    async def get_by_guild(cls,guild_id:int):        
        query = bot_client.coc_db.db__shop_item.find({'guild_id':guild_id,'disabled':False})
        return [cls(item) async for item in query]

    @classmethod
    async def get_by_guild_category(cls,guild_id:int,category:str):        
        query = bot_client.coc_db.db__shop_item.find({'guild_id':guild_id,'category':category,'disabled':False})
        return [cls(item) async for item in query]

    def __init__(self,database_entry:dict):      
        
        self.id = str(database_entry.get['_id'])
        self.guild_id = database_entry.get('guild_id',None)
        
        self.type = database_entry.get('type','')

        self.name = database_entry.get('name','')
        self.price = database_entry.get('price',0)
        self._stock = database_entry.get('stock',0)
        self.category = database_entry.get('category','') if len(database_entry.get('category','')) > 0 else "Uncategorized"
        self.description = database_entry.get('description',"")
        self.buy_message = database_entry.get('buy_message',"")
        
        self.exclusive_role = database_entry.get('exclusive_role',False)
        self._required_role = database_entry.get('required_role',0)
        
        self.show_in_store = database_entry.get('show_in_store',True)
        self.disabled = database_entry.get('disabled',False)
        
        self.role_id = database_entry.get('role_id',0)
        self.bidirectional_role = database_entry.get('bidirectional_role',False)
        
        self.random_items = database_entry.get('random_items',[])
    
    def __str__(self):
        return f"{self.type.capitalize()} Item: {self.name} (Price: {self.price:,}) (Stock: {self.stock})"

    def __eq__(self,other):
        if isinstance(other,ShopItem):
            return self.id == other.id
        return False
    
    @property
    def lock(self) -> asyncio.Lock:
        return self._locks[self.id]
    @property
    def guild(self) -> Optional[discord.Guild]:
        return bot_client.bot.get_guild(self.guild_id)    
    @property
    def stock(self) -> Union[int,str]:
        if self._stock < 0:
            return "Infinite"
        return self._stock
    @property
    def assigns_role(self) -> Optional[discord.Role]:
        if self.type == 'role':
            return self.guild.get_role(self.role_id)
        return None
    @property
    def required_role(self) -> Optional[discord.Role]:
        return self.guild.get_role(self._required_role)
    
    def can_i_buy(self,member:discord.Member) -> bool:
        if self.disabled:
            return False
        if self.required_role:
            if self.required_role.id not in [r.id for r in member.roles]:
                return False
        if isinstance(self.stock,int) and self.stock < 1:
            return False
        if self.type == 'role':
            if self.bidirectional_role:
                pass
            elif self.role_id in [r.id for r in member.roles]:
                return False
        return True

    async def purchase(self,user:discord.Member,quantity:int=1):        
        async with self.lock:
            if not self.can_i_buy(user):
                raise CannotPurchase(self)

            if self._stock > 0:
                item = bot_client.coc_db.db__shop_item.find_one_and_update(
                    {'_id':self.id},
                    {'$inc': {'stock':-quantity}}
                    )
                self._stock = item['stock']

    async def restock(self,quantity:int=1):
        async with self.lock:
            if self._stock >= 0:
                item = bot_client.coc_db.db__shop_item.find_one_and_update(
                    {'_id':self.id},
                    {'$inc': {'stock':quantity}}
                    )
                self._stock = item['stock']
    
    async def delete(self):        
        async with self.lock:
            self.disabled = True
            await bot_client.coc_db.db__shop_item.update_one(
                {'_id':self.id},
                {'$set': {'disabled':True}}
                )
    
    async def unhide(self):
        async with self.lock:
            self.show_in_store = True
            await bot_client.coc_db.db__shop_item.update_one(
                {'_id':self.id},
                {'$set': {'show_in_store':True}}
                )
                
    async def hide(self):
        async with self.lock:
            self.show_in_store = False
            await bot_client.coc_db.db__shop_item.update_one(
                {'_id':self.id},
                {'$set': {'show_in_store':False}}
                )
    
    async def random_select(self):
        grant_items = await asyncio.gather(*(ShopItem.get_by_id(item) for item in self.random_items))
        eligible_items = [item for item in grant_items if not item.disabled]
        
        total_price = sum([item.price for item in eligible_items])
        pick_weights = [(total_price - item.price) for item in eligible_items]

        chosen_item = random.choices(eligible_items, pick_weights, k=1)[0]
        return chosen_item
    
    @classmethod
    async def create(cls,**kwargs):        
        new_item = await bot_client.coc_db.db__shop_item.insert_one(
            {
                'guild_id':kwargs['guild_id'],
                'type':kwargs['type'],
                'name':kwargs['name'],
                'price':kwargs['price'],
                'stock':kwargs.get('stock') if kwargs.get('stock') else -1,
                'description':kwargs.get('description') if kwargs.get('description') else "",
                'category':kwargs.get('category') if kwargs.get('category') else "Uncategorized",
                'buy_message':kwargs.get('buy_message') if kwargs.get('buy_message') else "",
                'exclusive_role':kwargs.get('exclusive_role') if kwargs.get('exclusive_role') else False,
                'required_role':kwargs.get('required_role') if kwargs.get('required_role') else 0,
                'show_in_store':False,
                'disabled':False,
                'role_id':kwargs.get('role_id') if kwargs.get('role_id') else 0,
                'bidirectional_role':kwargs.get('bidirectional_role') if kwargs.get('bidirectional_role') else False,
                'random_items':kwargs.get('random_items') if kwargs.get('random_items') else []
                }
            )
        item = await cls.get_by_id(new_item.inserted_id)
        bot_client.coc_main_log.info(f"Created new shop item: {item} {item.guild_id} {item.id}")
        return item

class NewShopItem():
    def __init__(self,guild_id):
        self.guild_id = guild_id
        self.type = None

        self.name = None
        self.price = None
        self.stock = None
        self.description = None
        self.category = None
        self.buy_message = None

        self.required_role = None

        self.associated_role = None
        self.bidirectional_role = None

        self.exclusive = False
        self.bidirectional = False

        self.random_items = None
    
    @property
    def ready_to_save(self):
        if self.type is None:
            return False
        if self.name is None:
            return False
        if self.price is None:
            return False
        if self.stock is None:
            return False
        if self.type in ['role']:
            if self.associated_role is None:
                return False
        if self.type == 'random':
            if self.random_items is None:
                return False
        return True
    
    async def save_item(self):        
        item = await ShopItem.create(
            guild_id=self.guild_id,
            type=self.type,
            name=self.name,
            price=self.price,
            stock=self.stock,
            description=self.description,
            category=self.category,
            buy_message=self.buy_message,
            exclusive_role=self.exclusive,
            required_role=getattr(self.required_role,'id',None),
            role_id=getattr(self.associated_role,'id',None),
            bidirectional_role=self.bidirectional,
            random_items=self.random_items
            )
        return item