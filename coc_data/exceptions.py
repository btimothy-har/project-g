import coc

from coc_client.exceptions import *

class ClashDataError(ClashOfClansError):
    """
    Base Class for Clash of Clans Data Errors.

    This inherits from the ClashOfClansError class.
    """
    pass

##################################################
##### CLASH API ERRORS
##################################################
class ClashAPIError(ClashDataError):
    def __init__(self,exception):
        if isinstance(exception,coc.Maintenance):
            self.message = f"Clash of Clans API is currently under maintenance. Please try again later."
        else:
            self.message = f"The Clash of Clans API isn't available right now. Please try again later."
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'

class InvalidTag(ClashDataError):
    def __init__(self,tag):
        self.tag = tag
        self.message = f'The tag `{tag}` appears to be invalid.'
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'

##################################################
##### CLASH DATA / DATABASE ERRORS
##################################################
class InvalidAbbreviation(ClashDataError):
    def __init__(self,abbr):
        self.abbreviation_input = abbr.upper()
        self.message = f'The abbreviation `{abbr.upper()}` is does not correspond to any Alliance Clan.'
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'

class InvalidID(ClashDataError):
    def __init__(self,event_id):
        self.message = f'The ID {event_id} is not valid.'
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'

class NoClansRegistered(ClashDataError):
    def __init__(self):
        self.message = f"There are no clans registered to the Alliance."
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'

class CacheNotReady(ClashDataError):
    def __init__(self):
        self.message = f"I'm not ready to do this yet! Please try again in a few minutes."
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'

##################################################
##### DISCORD OBJECT ERRORS
##################################################
class InvalidGuild(ClashDataError):
    def __init__(self,guild_id):
        self.guild_id = guild_id
        self.message = f'The server `{self.guild_id}` is not a valid Discord Guild. Please ensure that the bot is invited to the server.'
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'

class InvalidUser(ClashDataError):
    def __init__(self,user_id):
        self.user_id = user_id
        self.message = f"The user ID `{self.user_id}` doesn't seem to be a valid Discord User. Please check again."
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'
    
class InvalidRole(ClashDataError):
    def __init__(self,role_id):
        self.role_id = role_id
        self.message = f'The role ID `{self.role_id}` appears to be invalid. Please check again.'
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'

class InvalidChannel(ClashDataError):
    def __init__(self,channel_id):
        self.channel_id = channel_id
        self.message = f'The channel ID `{self.channel_id}` appears to be invalid. Please check again.'
        super().__init__(self.message)
    
    def __str__(self):
        return f'{self.message}'

# ##################################################
# ##### COMMAND ERRORS
# ##################################################
# class CommandUnauthorized(ClashCogError):
#     def __init__(self):
#         self.message = f"You don't have permissions to use this command."
#         super().__init__(self.message)
#     def __str__(self):
#         return f'{self.message}'

# class NotRecruitingTicket(ClashCogError):
#     def __init__(self,channel:discord.TextChannel):
#         self.channel = channel
#         self.message = f'The channel {self.channel.mention} is not a recruiting ticket.'
#         super().__init__(self.message)
        


# class SessionTimeOut(ClashCogError):
#     def __init__(self,exc):
#         self.message = exc
#         super().__init__(self.message)
#     def __str__(self):
#         return f'{self.message}'



# async def handle_invalid_season(ctx,season_id,message=None):
#     error_embed = await clash_embed(
#         ctx=ctx,
#         title=f"**Invalid Season**",
#         message=f'`{season_id}` is not a valid tracked season.',
#         color="fail")
#     if message:
#         await message.edit(embed=error_embed)
#     else:
#         await ctx.send(embed=error_embed)

# async def no_clans_registered(ctx,message=None):
#     eEmbed = await clash_embed(ctx=ctx,
#         message=f"There are no clans registered to the Alliance.",
#         color="fail")
#     if message:
#         return await message.edit(embed=eEmbed)
#     else:
#         return await ctx.send(embed=eEmbed)


# async def error_not_valid_abbreviation(ctx,abbr_input):
#     eEmbed = await clash_embed(ctx=ctx,
#         message=f"The abbreviation `{abbr_input}` does not correspond to any Alliance clan.",
#         color="fail")
#     return await ctx.send(embed=eEmbed)

# async def error_end_processing(ctx,preamble,err):
#     eEmbed = await clash_embed(ctx=ctx,
#         message=f"{preamble}: {err}",
#         color="fail")
#     return await ctx.send(embed=eEmbed)
