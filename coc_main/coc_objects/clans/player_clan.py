from typing import *
from mongoengine import *

from .base_clan import *

from ...exceptions import *

class aPlayerClan(BasicClan):
    def __init__(self,**kwargs):

        if kwargs.get('tag'):
            self.tag = kwargs.get('tag')        
            BasicClan.__init__(self,tag=self.tag)
        else:
            BasicClan.__init__(self)
        
        if kwargs.get('name'):
            self._name = kwargs.get('name')
        if kwargs.get('badge'):
            self._badge = kwargs.get('badge')        
        if kwargs.get('level'):
            self._level = kwargs.get('level')
    
    @property
    def name(self) -> str:
        if getattr(self,'_name',None) is None:
            return BasicClan(self.tag).name
        return self._name
    @name.setter
    def name(self,value:str):
        self._name = value

    @property
    def badge(self) -> str:
        if getattr(self,'_badge',None) is None:
            return BasicClan(self.tag).badge
        return self._badge
    @badge.setter
    def badge(self,value:str):
        self._badge = value
    
    @property
    def level(self) -> int:
        if getattr(self,'_level',None) is None:
            return BasicClan(self.tag).level
        return self._level
    @level.setter
    def level(self,value:int):
        self._level = value