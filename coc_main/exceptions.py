import coc
import discord

class ClashOfClansError(Exception):
    """Base Class for Clash of Clans Errors."""
    pass

##################################################
##### CLASH API ERRORS
##################################################
class LoginNotSet(ClashOfClansError):
    def __init__(self, exc):
        self.message = exc
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'

class DiscordLinksError(ClashOfClansError):
    def __init__(self, exc):
        self.message = exc
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'
    
class ClashAPIError(ClashOfClansError):
    def __init__(self,exception):
        if isinstance(exception,coc.Maintenance):
            self.message = f"Clash of Clans API is currently under maintenance. Please try again later."
        else:
            self.message = f"The Clash of Clans API isn't available right now. Please try again later."
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'

class InvalidTag(ClashOfClansError):
    def __init__(self,tag):
        self.tag = tag
        self.message = f'The tag `{tag}` appears to be invalid.'
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'
    
##################################################
##### CLASH DATA / DATABASE ERRORS
##################################################
class InvalidAbbreviation(ClashOfClansError):
    def __init__(self,abbr):
        self.abbreviation_input = abbr.upper()
        self.message = f'The abbreviation `{abbr.upper()}` is does not correspond to any Alliance Clan.'
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'

class InvalidID(ClashOfClansError):
    def __init__(self,event_id):
        self.message = f'The ID {event_id} is not valid.'
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'

class NoClansRegistered(ClashOfClansError):
    def __init__(self):
        self.message = f"There are no clans registered to the Alliance."
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'

class CacheNotReady(ClashOfClansError):
    def __init__(self):
        self.message = f"I'm not ready to do this yet! Please try again in a few minutes."
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'

##################################################
##### DISCORD OBJECT ERRORS
##################################################
class InvalidGuild(ClashOfClansError):
    def __init__(self,guild_id):
        self.guild_id = guild_id
        self.message = f'The server `{self.guild_id}` is not a valid Discord Guild. Please ensure that the bot is invited to the server.'
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'

class InvalidUser(ClashOfClansError):
    def __init__(self,user_id):
        self.user_id = user_id
        self.message = f"The user ID `{self.user_id}` doesn't seem to be a valid Discord User. Please check again."
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'
    
class InvalidRole(ClashOfClansError):
    def __init__(self,role_id):
        self.role_id = role_id
        self.message = f'The role ID `{self.role_id}` appears to be invalid. Please check again.'
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'

class InvalidChannel(ClashOfClansError):
    def __init__(self,channel_id):
        self.channel_id = channel_id
        self.message = f'The channel ID `{self.channel_id}` appears to be invalid. Please check again.'
        super().__init__(self.message)
    
    def __str__(self):
        return f'{self.message}'
    
class CommandUnauthorized(ClashOfClansError):
    def __init__(self):
        self.message = f"You don't have permissions to use this command."
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'

class NotRecruitingTicket(ClashOfClansError):
    def __init__(self,channel:discord.TextChannel):
        self.channel = channel
        self.message = f'The channel {self.channel.mention} is not a recruiting ticket.'
        super().__init__(self.message)

class SessionTimeOut(ClashOfClansError):
    def __init__(self,exc):
        self.message = exc
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'