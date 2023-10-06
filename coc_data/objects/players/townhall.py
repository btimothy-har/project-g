from ...constants.coc_emojis import *

class aTownHall():
    def __init__(self,level=1,weapon=0):
        self.level = level
        self.weapon = weapon

    def __str__(self):
        return self.description
    
    @property
    def emoji(self):
        return EmojisTownHall.get(self.level)
    @property
    def emote(self):
        return EmojisTownHall.get(self.level)
    
    @property
    def description(self):
        if self.level >= 12:
            return f"**{self.level}**-{self.weapon}"
        else:
            return f"**{self.level}**"