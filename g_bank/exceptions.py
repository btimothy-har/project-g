from coc_main.exceptions import ClashOfClansError

class CannotPurchase(ClashOfClansError):
    def __init__(self, item):
        self.message = f'You cannot purchase {item}.'
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'