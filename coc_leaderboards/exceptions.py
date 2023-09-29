import coc
import discord

from coc_client.exceptions import *

class ClashLeaderboardError(ClashOfClansError):
    """
    Base Class for Clash of Clans Data Errors.
    
    This inherits from the ClashOfClansError class.
    """
    pass

class LeaderboardExists(ClashLeaderboardError):
    def __init__(self, exc):
        self.message = exc
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'