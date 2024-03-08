import coc
import discord

class ProjectGError(Exception):
    """Base Class for Project G Errors."""
    pass

class ClientNotReady(ProjectGError):
    """
    Raised when the bot is not ready to perform the requested action.
    """

##################################################
##### DATABASE ERRORS
##################################################
class DatabaseLogin(ProjectGError):
    """
    Raised when the bot is unable to login to the database.
    """

class SeasonNotLoaded(ProjectGError):
    """
    Raised when attempting to retrieve Seasons without being loaded.
    """

class DatabaseNotAvailable(ProjectGError):
    """
    Raised when the bot is unable to login to the database.
    """
    
##################################################
##### DISCORD ERRORS
##################################################
class InvalidGuild(ProjectGError):
    """
    Raised when the bot is unable to find a Discord Guild.
    """

class InvalidUser(ProjectGError):
    """
    Raised when the bot is unable to find a Discord User.
    """
    
class InvalidRole(ProjectGError):
    """
    Raised when the bot is unable to find a Discord Role.
    """

class InvalidChannel(ProjectGError):
    """
    Raised when the bot is unable to find a Discord Channel.
    """
    
# class ClashAPIError(ClashOfClansError):
#     def __init__(self,exception=None):
#         if exception and isinstance(exception,coc.Maintenance):
#             self.message = f"Clash of Clans API is currently under maintenance. Please try again later."
#         else:
#             self.message = f"The Clash of Clans API isn't available right now. Please try again later."
#         super().__init__(self.message)
#     def __str__(self):
#         return f'{self.message}'

# class InvalidTag(ClashOfClansError):
#     def __init__(self,tag):
#         self.tag = tag
#         self.message = f'The tag `{tag}` appears to be invalid.'
#         super().__init__(self.message)
#     def __str__(self):
#         return f'{self.message}'
    
# ##################################################
# ##### CLASH DATA / DATABASE ERRORS
# ##################################################
# class InvalidAbbreviation(ClashOfClansError):
#     def __init__(self,abbr):
#         self.abbreviation_input = abbr.upper()
#         self.message = f'The abbreviation `{abbr.upper()}` is does not correspond to any Alliance Clan.'
#         super().__init__(self.message)
#     def __str__(self):
#         return f'{self.message}'

# class InvalidID(ClashOfClansError):
#     def __init__(self,event_id):
#         self.message = f'The ID {event_id} is not valid.'
#         super().__init__(self.message)
#     def __str__(self):
#         return f'{self.message}'

# class NoClansRegistered(ClashOfClansError):
#     def __init__(self):
#         self.message = f"There are no clans registered to the Alliance."
#         super().__init__(self.message)
#     def __str__(self):
#         return f'{self.message}'

# class CacheNotReady(ClashOfClansError):
#     def __init__(self):
#         self.message = f"I'm not ready to do this yet! Please try again in a few minutes."
#         super().__init__(self.message)
#     def __str__(self):
#         return f'{self.message}'

# ##################################################
# ##### DISCORD OBJECT ERRORS
# ##################################################

# class NotRecruitingTicket(ClashOfClansError):
#     def __init__(self,channel:discord.TextChannel):
#         self.channel = channel
#         self.message = f'The channel {self.channel.mention} is not a recruiting ticket.'
#         super().__init__(self.message)

# class SessionTimeOut(ClashOfClansError):
#     def __init__(self,exc):
#         self.message = exc
#         super().__init__(self.message)
#     def __str__(self):
#         return f'{self.message}'