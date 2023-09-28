class ClashOfClansError(Exception):
    """Base Class for Clash of Clans Errors."""
    pass

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