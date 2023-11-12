import discord
import random
import asyncio

from redbot.core import bank

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
    _locks = {}

    @classmethod
    async def get_by_id(cls,item_id:str) -> Optional['ShopItem']:
        def _db_query():
            try:
                item = db_ShopItem.objects.get(id=item_id)
            except DoesNotExist:
                return None
            return item
        
        item = await bot_client.run_in_thread(_db_query)
        if item is None:
            return None
        return cls(item)

    @classmethod
    async def get_by_guild(cls,guild_id:int):
        def _db_query():
            item = db_ShopItem.objects(guild_id=guild_id,disabled=False)
            return [i for i in item]
        
        items = await bot_client.run_in_thread(_db_query)
        return [cls(item) for item in items]

    @classmethod
    async def get_by_guild_category(cls,guild_id:int,category:str):
        def _db_query():
            item = db_ShopItem.objects(guild_id=guild_id,category=category,disabled=False)
            return [i for i in item]
        
        items = await bot_client.run_in_thread(_db_query)
        return [cls(item) for item in items]

    def __init__(self,database_entry:db_ShopItem):      
        self.id = str(database_entry.id)

        self.guild_id = database_entry.guild_id

        self.type = database_entry.type

        self.name = database_entry.name
        self.price = database_entry.price
        self._stock = database_entry.stock
        self._category = database_entry.category
        self.description = database_entry.description        
        self.buy_message = database_entry.buy_message
        
        self.exclusive_role = database_entry.exclusive_role
        self._required_role = database_entry.required_role
        self.show_in_store = database_entry.show_in_store
        self.disabled = database_entry.disabled
        
        self.role_id = database_entry.role_id
        self.bidirectional_role = database_entry.bidirectional_role
        self.random_items = database_entry.random_items
    
    def __str__(self):
        return f"{self.type.capitalize()} Item: {self.name} (Price: {self.price:,}) (Stock: {self.stock})"

    def __eq__(self,other):
        if isinstance(other,ShopItem):
            return self.id == other.id
        return False
    
    @property
    def lock(self):
        try:
            lock = ShopItem._locks[self.id]
        except KeyError:
            ShopItem._locks[self.id] = lock = asyncio.Lock()
        return lock
    
    def can_i_buy(self,member:discord.Member):        
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
        def _update_in_db():
            item = db_ShopItem.objects.get(id=self.id)
            current_stock = item.stock

            if current_stock > 0:
                new_stock = current_stock - quantity
                db_ShopItem.objects(id=self.id).update_one(set__stock=new_stock)
                return new_stock            
            return current_stock
        
        async with self.lock:
            if not self.can_i_buy(user):
                raise CannotPurchase(self)
            self._stock = await bot_client.run_in_thread(_update_in_db)

    async def restock(self,quantity:int=1):
        def _update_in_db():
            item = db_ShopItem.objects.get(id=self.id)
            current_stock = item.stock

            if current_stock <= 0:
                new_stock = current_stock + quantity
                db_ShopItem.objects(id=self.id).update_one(set__stock=new_stock)
                return new_stock            
            return current_stock
        
        async with self.lock:
            self._stock = await bot_client.run_in_thread(_update_in_db)
    
    async def delete(self):
        def _update_in_db():
            db_ShopItem.objects(id=self.id).update_one(set__disabled=self.disabled)
        
        async with self.lock:
            self.disabled = True
            await bot_client.run_in_thread(_update_in_db)
    
    async def unhide(self):
        def _update_in_db():
            db_ShopItem.objects(id=self.id).update_one(set__show_in_store=self.show_in_store)
        
        async with self.lock:
            self.show_in_store = True
            await bot_client.run_in_thread(_update_in_db)
    
    async def hide(self):
        def _update_in_db():
            db_ShopItem.objects(id=self.id).update_one(set__show_in_store=self.show_in_store)
        
        async with self.lock:
            self.show_in_store = False
            await bot_client.run_in_thread(_update_in_db)

    @property
    def guild(self):
        return bot_client.bot.get_guild(self.guild_id)
    
    @property
    def stock(self):
        if self._stock < 0:
            return "Infinite"
        return self._stock
    
    @property
    def category(self):
        return self._category if len(self._category) > 0 else "Uncategorized"

    @property
    def assigns_role(self):
        if self.type == 'role':
            return self.guild.get_role(self.role_id)
        return None

    @property
    def required_role(self):
        return self.guild.get_role(self._required_role)

    async def random_select(self):
        grant_items = await asyncio.gather(*(ShopItem.get_by_id(item) for item in self.random_items))
        eligible_items = [item for item in grant_items if not item.disabled]
        
        total_price = sum([item.price for item in eligible_items])
        pick_weights = [(total_price - item.price) for item in eligible_items]

        chosen_item = random.choices(eligible_items, pick_weights, k=1)[0]
        return chosen_item
    
    @classmethod
    async def create(cls,**kwargs):
        def _save_to_db():
            item = db_ShopItem(
                guild_id=kwargs.get('guild_id'),
                type=kwargs.get('type'),
                name=kwargs.get('name'),
                price=kwargs.get('price'),
                stock=kwargs.get('stock') if kwargs.get('stock') else -1,
                description=kwargs.get('description') if kwargs.get('description') else "",
                category=kwargs.get('category') if kwargs.get('category') else "",
                buy_message=kwargs.get('buy_message') if kwargs.get('buy_message') else "",
                exclusive_role=kwargs.get('exclusive_role') if kwargs.get('exclusive_role') else False,
                required_role=kwargs.get('required_role') if kwargs.get('required_role') else 0,
                show_in_store=False,
                disabled=False,            
                role_id=kwargs.get('role_id') if kwargs.get('role_id') else 0,
                bidirectional_role=kwargs.get('bidirectional_role') if kwargs.get('bidirectional_role') else False,
                random_items=kwargs.get('random_items') if kwargs.get('random_items') else []
                )
            item.save()
            return item
        item = await bot_client.run_in_thread(_save_to_db)

        s_item = cls(item)
        bot_client.coc_main_log.info(f"Created new shop item: {s_item} {s_item.guild_id} {s_item.id}")
        return s_item

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