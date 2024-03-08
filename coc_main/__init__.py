import asyncio

from redbot.core.bot import Red
from .cog_coc_main import ClashOfClansMain as coc_main

async def setup(bot:Red):
    cog_main = coc_main(bot)
    await bot.add_cog(cog_main)


# # LOGGER SET UP
# log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
# main_logpath = f"{self.bot.coc_log_path}/main"
# if not os.path.exists(main_logpath):
#     os.makedirs(main_logpath)
# cocmain_log_handler = logging.handlers.RotatingFileHandler(
#     f"{main_logpath}/main.log",
#     maxBytes=3*1024*1024,
#     backupCount=9
#     )
# cocmain_log_handler.setFormatter(log_formatter)
# self.coc_main_log.addHandler(cocmain_log_handler)

# data_logpath = f"{self.bot.coc_log_path}/data"
# if not os.path.exists(data_logpath):
#     os.makedirs(data_logpath)
# cocdata_log_handler = logging.handlers.RotatingFileHandler(
#     f"{data_logpath}/data.log",
#     maxBytes=10*1024*1024,
#     backupCount=9
#     )
# cocdata_log_handler.setFormatter(log_formatter)
# self.coc_data_log.addHandler(cocdata_log_handler)

# clashlinks_logpath = f"{self.bot.coc_log_path}/discordlinks"
# if not os.path.exists(clashlinks_logpath):
#     os.makedirs(clashlinks_logpath)
# clashlinks_log_handler = logging.handlers.RotatingFileHandler(
#     f"{clashlinks_logpath}/discordlinks.log",
#     maxBytes=3*1024*1024,
#     backupCount=9
#     )
# clashlinks_log_handler.setFormatter(log_formatter)
# self.discordlinks_log.addHandler(clashlinks_log_handler)