import logging
import motor.motor_asyncio

from typing import *

from redbot.core.bot import Red
from ..exceptions import DatabaseLogin

COC_LOG = logging.getLogger("coc.main")

class MotorClient():
    bot:Red = None
    motor_client:motor.motor_asyncio.AsyncIOMotorClient = None
    database:motor.motor_asyncio.AsyncIOMotorDatabase = None

    @classmethod
    async def client_login(cls,bot:Red) -> 'MotorClient':        
        clash_database = await bot.get_shared_api_tokens("clash_db")
        if clash_database.get("dbprimary") is None:
            raise DatabaseLogin()
        if clash_database.get("username") is None:
            raise DatabaseLogin()
        if clash_database.get("password") is None:
            raise DatabaseLogin()

        motor_client = motor.motor_asyncio.AsyncIOMotorClient(
            f'mongodb://{clash_database.get("username")}:{clash_database.get("password")}@localhost:27017/admin',
            uuidRepresentation="pythonLegacy",
            maxPoolSize=1000,
            )
        database = motor_client[clash_database.get("dbprimary")]

        cls.bot = bot
        cls.motor_client = motor_client
        cls.database = database

        COC_LOG.info("Connected to Mongo Database")
        return cls()
    
    @classmethod
    async def close(cls):
        cls.motor_client.close()
        COC_LOG.info("Closed Mongo Database Connection")