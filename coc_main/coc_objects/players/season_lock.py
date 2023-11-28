import asyncio
from collections import defaultdict

from ..season.season import aClashSeason

class PlayerSeason():
    _locks = defaultdict(asyncio.Lock)

    def __init__(self,tag:str,season:aClashSeason):
        self._id = (tag,season.id)
        self._db_id = {'season': season.id,'tag': tag}
    
    @property
    def _lock(self) -> asyncio.Lock:
        return self._locks[self.id]
