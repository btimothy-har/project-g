from typing import *
from mongoengine import *
from .base_clan import BasicClan

from ...constants.coc_emojis import *
from ...constants.ui_emojis import *
from ...constants.coc_constants import *
from ...exceptions import *

class aPlayerClan(BasicClan):
    def __init__(self,**kwargs):

        if kwargs.get('tag'):
            self.tag = kwargs.get('tag')        
            BasicClan.__init__(self,tag=self.tag)
        else:
            BasicClan.__init__(self)
        
        if kwargs.get('name'):
            self.name = kwargs.get('name')
        if kwargs.get('badge'):
            self.badge = kwargs.get('badge')        
        if kwargs.get('level'):
            self.level = kwargs.get('level')
        
        if self.tag:
            if self.name == 'No Clan':
                self.name = self.cached_name
            if not hasattr(self,'badge'):
                self.badge = self.cached_badge
            if not hasattr(self,'level'):
                self.level = self.cached_level