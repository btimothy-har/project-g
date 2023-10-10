import discord
import random

from redbot.core import bank

from mongoengine import *
from typing import *

from coc_main.api_client import BotClashClient

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

    required_role = IntField(default=0)
    show_in_store = BooleanField(default=True)
    disabled = BooleanField(default=False)
    
    role_id = IntField(default=0)
    bidirectional_role = BooleanField(default=False)
    
    random_items = ListField(StringField(),default=[])

class ShopItem():
    @classmethod
    def get_by_id(cls,item_id:str):
        try:
            item = db_ShopItem.objects.get(id=item_id)
            return cls(item)
        except DoesNotExist:
            return None

    @classmethod
    def get_by_guild(cls,guild_id:int):
        items = db_ShopItem.objects(guild_id=guild_id,disabled=False)
        return [cls(item) for item in items]

    @classmethod
    def get_by_guild_category(cls,guild_id:int,category:str):
        items = db_ShopItem.objects(guild_id=guild_id,category=category,disabled=False)
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
    
    def save(self):
        db_item = db_ShopItem(
            id=self.id,
            guild_id=self.guild_id,
            type=self.type,
            name=self.name,
            price=self.price,
            stock=self._stock,
            description=self.description,
            category=self._category,
            buy_message=self.buy_message,
            required_role=self._required_role,
            show_in_store=self.show_in_store,
            disabled=self.disabled,            
            role_id=self.role_id,
            bidirectional_role=self.bidirectional_role,
            random_items=self.random_items
            )
        db_item.save()
    
    async def can_i_buy(self,member:discord.Member):        
        if self.disabled:
            return False
        if self.required_role:
            if self.required_role not in [r.id for r in member.roles]:
                return False
        if isinstance(self.stock,int) and self.stock < 1:
            return False
        if self.type == 'role' and not self.bidirectional_role:
            if self.role_id in [r.id for r in member.roles]:
                return False
        can_spend = await bank.can_spend(member,self.price)
        if not can_spend:
            return False
        return True

    @property
    def guild(self):
        return bot_client.bot.get_guild(self.guild_id)
    
    @property
    def stock(self):
        if self._stock < 0:
            return "Infinite"
        return self._stock
    @stock.setter
    def stock(self,new_stock:int):
        if self._stock >= 0:
            self._stock = new_stock
            self.save()
    
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
    
    @property
    def grants_items(self) -> List['ShopItem']:
        if self.type == 'random':
            return [item for item in [ShopItem.get_by_id(item) for item in self.random_items] if not item.disabled]
        return []

    def random_select(self):
        total_price = sum([item.price for item in self.grants_items])

        pick_weights = [(total_price - item.price) for item in self.grants_items]
        chosen_item = random.choices(self.grants_items, pick_weights, k=1)[0]
        return chosen_item
    
    @classmethod
    async def create(cls,**kwargs):
        item = db_ShopItem(
            guild_id=kwargs.get('guild_id'),
            type=kwargs.get('type'),

            name=kwargs.get('name'),
            price=kwargs.get('price'),
            stock=kwargs.get('stock') if kwargs.get('stock') else -1,
            description=kwargs.get('description') if kwargs.get('description') else "",
            category=kwargs.get('category') if kwargs.get('category') else "",
            buy_message=kwargs.get('buy_message') if kwargs.get('buy_message') else "",
            required_role=kwargs.get('required_role') if kwargs.get('required_role') else 0,
            show_in_store=False,
            disabled=False,            
            role_id=kwargs.get('role_id') if kwargs.get('role_id') else 0,
            bidirectional_role=kwargs.get('bidirectional_role') if kwargs.get('bidirectional_role') else False,
            random_items=kwargs.get('random_items') if kwargs.get('random_items') else []
            )
        item.save()
        return cls(item)
    
    async def delete(self):
        self.disabled = True
        self.save()
    
    async def unhide(self):
        self.show_in_store = True
        self.save()
    
    async def hide(self):
        self.show_in_store = False
        self.save()

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
        if self.type in ['roleadd','rolebidirectional']:
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
            required_role=getattr(self.required_role,'id',None),
            role_id=getattr(self.associated_role,'id',None),
            bidirectional_role=self.bidirectional_role,
            random_items=self.random_items
            )
        return item