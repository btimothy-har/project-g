from typing import *

from ...utils.constants.coc_emojis import EmojisTownHall

class aTownHall():
    def __init__(self,level=1,weapon=0):
        self.level = level
        self.weapon = weapon

    def __str__(self) -> str:
        return self.description
    
    @property
    def emoji(self) -> str:
        return EmojisTownHall.get(self.level)
    @property
    def emote(self) -> str:
        return EmojisTownHall.get(self.level)
    
    @property
    def description(self) -> str:
        if self.level >= 12:
            return f"**{self.level}**-{self.weapon}"
        else:
            return f"**{self.level}**"