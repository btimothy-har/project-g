class EventClosed(Exception):
    def __init__(self):
        self.message = f"The Event you are registering for is not open for registration."
        super().__init__(self.message)        
    def __str__(self):
        return f'{self.message}'

class NotEligible(Exception):
    def __init__(self):
        self.message = f"You are not eligible to register for this event."
        super().__init__(self.message)        
    def __str__(self):
        return f'{self.message}'
    
class AlreadyRegistered(Exception):
    def __init__(self):
        self.message = f"You have already reached the maximum registrations for this event."
        super().__init__(self.message)        
    def __str__(self):
        return f'{self.message}'