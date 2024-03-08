import discord

class InvalidApplicationChannel(Exception):
    def __init__(self, channel):
        self.message = f"The channel {channel.mention} is not a valid application channel. Please check again."
        super().__init__(self.message)
        
    def __str__(self):
        return f'{self.message}'