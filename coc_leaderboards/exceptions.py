from coc_main.exceptions import ProjectGError

class LeaderboardExists(ProjectGError):
    def __init__(self, exc):
        self.message = exc
        super().__init__(self.message)
    def __str__(self):
        return f'{self.message}'