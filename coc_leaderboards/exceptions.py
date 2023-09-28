import coc
import discord

from coc_client.exceptions import *

class ClashLeaderboardError(ClashOfClansError):
    """
    Base Class for Clash of Clans Data Errors.
    
    This inherits from the ClashOfClansError class.
    """
    pass

# class CommandUnauthorized(ClashCommandError):
#     def __init__(self):
#         self.message = f"You don't have permissions to use this command."
#         super().__init__(self.message)
#     def __str__(self):
#         return f'{self.message}'

# class NotRecruitingTicket(ClashCommandError):
#     def __init__(self,channel:discord.TextChannel):
#         self.channel = channel
#         self.message = f'The channel {self.channel.mention} is not a recruiting ticket.'
#         super().__init__(self.message)

# class SessionTimeOut(ClashCommandError):
#     def __init__(self,exc):
#         self.message = exc
#         super().__init__(self.message)
#     def __str__(self):
#         return f'{self.message}'