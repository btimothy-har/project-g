import asyncio
import coc
import pendulum
import copy
import random
import yappi

from typing import *
from collections import defaultdict
from ..api_client import BotClashClient as client
from ..exceptions import InvalidTag, ClashAPIError

from redbot.core.utils import AsyncIter, bounded_gather

from .default import TaskLoop

from ..discord.feeds.capital_contribution import CapitalContributionFeed

from ..coc_objects.players.player import db_Player, aPlayer, db_PlayerStats
from ..utils.constants.coc_constants import activity_achievements
from ..utils.utils import chunks

bot_client = client()
default_sleep = 60

############################################################
############################################################
#####
##### DEFAULT PLAYER TASKS
#####
############################################################
############################################################
class PlayerTasks():
    
    @staticmethod
    async def compare_achievement(old_player:aPlayer,new_player:aPlayer,achievement:coc.Achievement):
        old_ach = old_player.get_achievement(achievement.name)
        new_ach = new_player.get_achievement(achievement.name)
        compare = old_ach.value != new_ach.value
        return compare, old_ach, new_ach
    
    ############################################################
    ### PLAYER LAST SEEN
    ############################################################
    @staticmethod
    async def player_time_in_home_clan(old_player:aPlayer,new_player:aPlayer):
        try:
            if new_player.is_member and getattr(new_player.clan,'tag',False) == getattr(new_player.home_clan,'tag',True):
                current_season = await new_player.get_current_season()
                await current_season.add_time_in_home_clan(new_player.timestamp.int_timestamp - old_player.timestamp.int_timestamp)
        except:
            bot_client.coc_main_log.exception(f"{new_player.tag}: Error in Player Home Clan Timer task.")

    @staticmethod
    async def player_last_seen_main(old_player:aPlayer,new_player:aPlayer):
        try:
            # if not await new_player.is_member:
            #     return
            
            update = False
            if old_player.name != new_player.name:
                update = True        
            if old_player.clan and new_player.clan and old_player.war_opted_in != new_player.war_opted_in:
                update = True        
            if old_player.label_ids != new_player.label_ids:
                update = True
            
            if update:
                current_season = await new_player.get_current_season()
                await current_season.add_last_seen(new_player.timestamp)
        except:
            bot_client.coc_main_log.exception(f"{new_player.tag}: Error in Player Last Seen Main task.")

    @staticmethod
    async def player_last_seen_achievement(old_player:aPlayer,new_player:aPlayer,achievement:coc.Achievement):
        try:
            # if not await new_player.is_member:
            #     return
            
            if achievement.name in activity_achievements:
                old_ach = old_player.get_achievement(achievement.name)
                new_ach = new_player.get_achievement(achievement.name)

                if old_ach.value != new_ach.value:
                    current_season = await new_player.get_current_season()
                    await current_season.add_last_seen(new_player.timestamp)
        except:
            bot_client.coc_main_log.exception(f"{new_player.tag}: Error in Player Last Seen Achievement task.")

    ############################################################
    ### PLAYER STAT UPDATES
    ############################################################
    @staticmethod
    async def player_attack_wins(old_player:aPlayer,new_player:aPlayer):       
        try:
            # if not await new_player.is_member:
            #     return
            
            current_season = await new_player.get_current_season()

            if current_season.attacks._prior_seen:
                increment = new_player.attack_wins - current_season.attacks.last_update
            else:
                increment = new_player.attack_wins - old_player.attack_wins
            
            if increment > 0 or new_player.attack_wins != current_season.attacks.last_update:
                stat = await current_season.attacks.increment_stat(
                    increment=max(increment,0),
                    latest_value=new_player.attack_wins
                    )
                bot_client.coc_data_log.debug(
                    f"{new_player.tag} {new_player.name}: attack_wins {'+' if increment >= 0 else ''}{increment:,} (new: {stat.season_total:,}). Received: {new_player.attack_wins} vs {old_player.attack_wins}."
                    )
        except:
            bot_client.coc_main_log.exception(f"{new_player.tag}: Error in Player Attack Wins task.")

    @staticmethod
    async def player_defense_wins(old_player:aPlayer,new_player:aPlayer):        
        try:
            # if not await new_player.is_member:
            #     return
            
            current_season = await new_player.get_current_season()

            if current_season.defenses._prior_seen:
                increment = new_player.defense_wins - current_season.defenses.last_update
            else:
                increment = new_player.defense_wins - old_player.defense_wins

            if increment > 0 or new_player.defense_wins != current_season.defenses.last_update:
                stat = await current_season.defenses.increment_stat(
                    increment=max(increment,0),
                    latest_value=new_player.defense_wins
                    )
                bot_client.coc_data_log.debug(
                    f"{new_player.tag} {new_player.name}: defense_wins {'+' if increment >= 0 else ''}{increment:,} (new: {stat.season_total:,}). Received: {new_player.defense_wins} vs {old_player.defense_wins}."
                    )
        except:
            bot_client.coc_main_log.exception(f"{new_player.tag}: Error in Player Defense Wins task.")

    @staticmethod
    async def player_donations_sent(old_player:aPlayer,new_player:aPlayer):
        try:
            # if not await new_player.is_member:
            #     return
            
            current_season = await new_player.get_current_season()

            if current_season.donations._prior_seen:
                increment = new_player.donations - current_season.donations.last_update
            else:
                increment = new_player.donations - old_player.donations            
            
            if increment > 0 or new_player.donations != current_season.donations.last_update:
                stat = await current_season.donations.increment_stat(
                    increment=max(increment,0),
                    latest_value=new_player.donations
                    )
                bot_client.coc_data_log.debug(
                    f"{new_player.tag} {new_player.name}: donations_sent {'+' if increment >= 0 else ''}{increment:,} (new: {stat.season_total:,}). Received: {new_player.donations} vs {old_player.donations}."
                    )
        except:
            bot_client.coc_main_log.exception(f"{new_player.tag}: Error in Player Donations Sent task.")

    @staticmethod
    async def player_donations_received(old_player:aPlayer,new_player:aPlayer):
        try:
            # if not await new_player.is_member:
            #     return
            
            current_season = await new_player.get_current_season()
           
            if current_season.received._prior_seen:
                increment = new_player.received - current_season.received.last_update
            else:
                increment = new_player.received - old_player.received

            if increment > 0 or new_player.received != current_season.received.last_update:
                stat = await current_season.received.increment_stat(
                    increment=max(increment,0),
                    latest_value=new_player.received
                    )
                bot_client.coc_data_log.debug(
                    f"{new_player.tag} {new_player.name}: donations_rcvd {'+' if increment >= 0 else ''}{increment:,} (new: {stat.season_total:,}). Received: {new_player.received} vs {old_player.received}."
                    )
        except:
            bot_client.coc_main_log.exception(f"{new_player.tag}: Error in Player Donations Rcvd task.")
    
    @staticmethod
    async def player_stat_achievements(old_player:aPlayer,new_player:aPlayer,achievement:coc.Achievement):
        try:
            # if not await new_player.is_member:
            #     return
            
            current_season = await new_player.get_current_season()

            #Loot Gold
            if achievement.name == "Gold Grab":
                compare, old_ach, new_ach = await PlayerTasks.compare_achievement(old_player,new_player,achievement)

                if current_season.loot_gold._prior_seen:
                    increment = new_ach.value - current_season.loot_gold.last_update
                else:
                    increment = new_ach.value - old_ach.value
                
                if increment > 0 or new_ach.value != current_season.loot_gold.last_update:
                    stat = await current_season.loot_gold.increment_stat(
                        increment=max(increment,0),
                        latest_value=new_ach.value
                        )                
                    bot_client.coc_data_log.debug(
                        f"{new_player.tag} {new_player.name}: loot_gold {'+' if increment >= 0 else ''}{increment:,} (new: {stat.season_total:,}). Received: {new_ach.value:,} vs {old_ach.value:,}."
                        )
            
            #Loot Elixir
            if achievement.name == "Elixir Escapade":
                compare, old_ach, new_ach = await PlayerTasks.compare_achievement(old_player,new_player,achievement)

                if current_season.loot_elixir._prior_seen:
                    increment = new_ach.value - current_season.loot_elixir.last_update
                else:
                    increment = new_ach.value - old_ach.value

                if increment > 0 or new_ach.value != current_season.loot_elixir.last_update:
                    stat = await current_season.loot_elixir.increment_stat(
                        increment=max(increment,0),
                        latest_value=new_ach.value
                        )
                    
                    bot_client.coc_data_log.debug(
                        f"{new_player.tag} {new_player.name}: loot_elixir {'+' if increment >= 0 else ''}{increment:,} (new: {stat.season_total:,}). Received: {new_ach.value:,} vs {old_ach.value:,}."
                        )
            
            #Loot Dark Elixir
            if achievement.name == "Heroic Heist":
                compare, old_ach, new_ach = await PlayerTasks.compare_achievement(old_player,new_player,achievement)

                if current_season.loot_darkelixir._prior_seen:
                    increment = new_ach.value - current_season.loot_darkelixir.last_update
                else:
                    increment = new_ach.value - old_ach.value
                
                if increment > 0 or new_ach.value != current_season.loot_darkelixir.last_update:
                    stat = await current_season.loot_darkelixir.increment_stat(
                        increment=max(increment,0),
                        latest_value=new_ach.value
                        )
                    
                    bot_client.coc_data_log.debug(
                        f"{new_player.tag} {new_player.name}: loot_darkelixir {'+' if increment >= 0 else ''}{increment:,} (new: {stat.season_total:,}). Received: {new_ach.value:,} vs {old_ach.value:,}."
                        )
        except:
            bot_client.coc_main_log.exception(f"{new_player.tag}: Error in Player Loot Achievements task.")

    @staticmethod
    async def player_capital_contribution(old_player:aPlayer,new_player:aPlayer,achievement:coc.Achievement):            
        try:
            # if not await new_player.is_member:
            #     return
            
            current_season = await new_player.get_current_season()
            
            #Capital Contribution
            if achievement.name == "Most Valuable Clanmate":
                compare, old_ach, new_ach = await PlayerTasks.compare_achievement(old_player,new_player,achievement)

                if current_season.capitalcontribution._prior_seen:
                    increment = new_ach.value - current_season.capitalcontribution.last_update
                else:
                    increment = new_ach.value - old_ach.value
                
                if increment > 0 or new_ach.value != current_season.capitalcontribution.last_update:
                    stat = await current_season.capitalcontribution.increment_stat(
                        increment=max(increment,0),
                        latest_value=new_ach.value
                        )
                
                    if increment > 0:
                        await CapitalContributionFeed.send_feed_update(new_player,increment)
                    
                    bot_client.coc_data_log.debug(
                        f"{new_player.tag} {new_player.name}: capital_contribution {'+' if increment >= 0 else ''}{increment:,} (new: {stat.season_total:,}). Received: {new_ach.value:,} vs {old_ach.value:,}."
                        )
        except:
            bot_client.coc_main_log.exception(f"{new_player.tag}: Error in Player Capital Contributions task.")

    @staticmethod
    async def player_clan_games(old_player:aPlayer,new_player:aPlayer,achievement:coc.Achievement):        
        try:
            # if not await new_player.is_member:
            #     return
            
            current_season = await new_player.get_current_season()
            if achievement.name == "Games Champion":
                if not new_player.clan and not old_player.clan:
                    return
                
                compare, old_ach, new_ach = await PlayerTasks.compare_achievement(old_player,new_player,achievement)

                if current_season.clangames._prior_seen:
                    increment = new_ach.value - current_season.clangames.last_update
                else:
                    increment = new_ach.value - old_ach.value
                
                if increment > 0 or new_ach.value != current_season.clangames.last_update:
                    await current_season.clangames.update(
                        increment=max(increment,0),
                        latest_value=new_ach.value,
                        timestamp=new_player.timestamp,
                        clan_tag=new_player.clan.tag if new_player.clan else old_player.clan.tag
                        )
        except:
            bot_client.coc_main_log.exception(f"{new_player.tag}: Error in Player Clan Games task.")

############################################################
############################################################
#####
##### PLAYER TASK LOOP
#####
############################################################
############################################################
class PlayerLoop(TaskLoop):
    _instance = None
    _cached = {}
    _locks = defaultdict(asyncio.Lock)
    
    _player_events = [
        PlayerTasks.player_time_in_home_clan,
        PlayerTasks.player_last_seen_main,
        PlayerTasks.player_attack_wins,
        PlayerTasks.player_defense_wins,
        PlayerTasks.player_donations_sent,
        PlayerTasks.player_donations_received,
        ]
    _achievement_events = [
        PlayerTasks.player_last_seen_achievement,
        PlayerTasks.player_stat_achievements,
        PlayerTasks.player_capital_contribution,
        PlayerTasks.player_clan_games,
        ]
    
    @classmethod
    def add_player_event(cls,event):
        if event.__name__ not in [e.__name__ for e in cls._player_events]:
            cls._player_events.append(event)
            bot_client.coc_main_log.info(f"Registered {event.__name__} {event} to Player Events.")
    
    @classmethod
    def remove_player_event(cls,event):        
        if event.__name__ in [e.__name__ for e in cls._player_events]:
            event = [e for e in cls._player_events if e.__name__ == event.__name__][0]
            cls._player_events.remove(event)
            bot_client.coc_main_log.info(f"Removed {event.__name__} {event} from Player Events.")
    
    @classmethod
    def add_achievement_event(cls,event):
        if event.__name__ not in [e.__name__ for e in cls._achievement_events]: 
            cls._achievement_events.append(event)
            bot_client.coc_main_log.info(f"Registered {event.__name__} {event} to Player Achievement Events.")

    @classmethod
    def remove_achievement_event(cls,event):
        if event.__name__ in [e.__name__ for e in cls._achievement_events]:
            event = [e for e in cls._achievement_events if e.__name__ == event.__name__][0]
            cls._achievement_events.remove(event)
            bot_client.coc_main_log.info(f"Removed {event.__name__} {event} from Player Achievement Events.")

    @classmethod
    async def _dispatch_events(cls,old_player:aPlayer,new_player:aPlayer):
        [asyncio.create_task(event(old_player,new_player)) for event in cls._player_events]
        [asyncio.create_task(event(old_player,new_player,achievement)) for achievement in new_player.achievements for event in cls._achievement_events]

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._is_new = True
        return cls._instance

    def __init__(self):        
        if self._is_new:
            super().__init__()
            self._is_new = False
        
    async def start(self):
        bot_client.coc_main_log.info(f"Player Loop started.")
        await super().start()
    
    async def stop(self):
        try:
            bot_client.coc_main_log.info(f"Player Loop stopped.")
        except:
            pass
        await super().stop()
    
    async def delay_multiplier(self,player:aPlayer) -> int:
        if not player:
            return 1
        if player.is_member:
            return 1
        if getattr(player.clan,'is_alliance_clan',False):
            return 1
        if getattr(player.clan,'is_active_league_clan',False):
            return 1.5
        if getattr(player.clan,'is_registered_clan',False):
            return 2
        if bot_client.bot.get_user(player.discord_user):
            return 2
        return 10
    
    async def defer(self,player:Optional[aPlayer]=None) -> bool:
        if not self.task_limiter.has_capacity():
            if not player:
                return False
            if player.is_member:
                return False
            if getattr(player.clan,'is_alliance_clan',False):
                return False
            if getattr(player.clan,'is_active_league_clan',False):
                return False
            if getattr(player.clan,'is_registered_clan',False):
                return False
            if bot_client.bot.get_user(player.discord_user):
                return False
            if pendulum.now().int_timestamp - player.timestamp.int_timestamp >= 1800:
                return False
            return True
        return False

    ##################################################
    ### PRIMARY TASK LOOP
    ##################################################
    async def _loop_task(self):        
        try:
            while self.loop_active:
                if self.api_maintenance:
                    await asyncio.sleep(10)
                    continue

                c_tags = copy.copy(self._tags)
                tags = list(c_tags)

                if len(tags) == 0:
                    await asyncio.sleep(10)
                    continue

                bot_client.coc_main_log.info(f"Dispatching Player Loop for {len(tags)} tags.")
                st = pendulum.now()
                self._running = True

                tasks = []
                async for chunk in chunks(tags,1000):
                    tasks.append(asyncio.create_task(self._bulk_dispatch(chunk)))

                await asyncio.gather(*tasks)

                self._last_loop = pendulum.now()
                self._running = False
                try:
                    runtime = self._last_loop - st
                    self.dispatch_time.append(runtime.total_seconds())
                    bot_client.coc_main_log.info(f"Player Loop Dispatch Time for {len(tags)} tags: {runtime.total_seconds():.2f} seconds.")
                except:
                    pass
            
                await asyncio.sleep(30)
                continue

        except Exception as exc:
            if self.loop_active:
                bot_client.coc_main_log.exception(
                    f"FATAL PLAYER LOOP ERROR. Attempting restart. {exc}"
                    )
                await TaskLoop.report_fatal_error(
                    message=f"FATAL PLAYER LOOP ERROR",
                    error=exc,
                    )
                await asyncio.sleep(60)
                await self.start()

    async def _bulk_dispatch(self,tags:List[str]):
        a_iter = AsyncIter(tags)
        tasks = [asyncio.create_task(self._launch_single_loop(tag)) async for tag in a_iter]
        await asyncio.gather(*tasks)
    
    async def _launch_single_loop(self,tag:str):
        lock = self._locks[tag]
        if lock.locked():
            return
        await lock.acquire()
        asyncio.create_task(self._run_single_loop(tag,lock))
        
    async def _run_single_loop(self,tag:str,lock:asyncio.Lock):
        try:
            cached = self._cached.get(tag,None)
            finished = False
            if await self.defer(cached):
                return self.loop.call_later(10,self.unlock,lock)
            
            async with self.task_limiter:
                st = pendulum.now()

                async with self.api_semaphore:
                    new_player = None
                    try:
                        new_player = await self.coc_client.fetch_player(tag)
                    except InvalidTag:
                        return self.loop.call_later(3600,self.unlock,lock)
                    except ClashAPIError:
                        return self.loop.call_later(10,self.unlock,lock)     

                await new_player._sync_cache()           
                wait = int(min(getattr(new_player,'_response_retry',default_sleep) * await self.delay_multiplier(new_player),600))
                self.loop.call_later(wait,self.unlock,lock)
                
                if cached:        
                    if new_player.timestamp.int_timestamp > getattr(cached,'timestamp',pendulum.now()).int_timestamp:
                        asyncio.create_task(PlayerLoop._dispatch_events(cached,new_player))
                self._cached[tag] = new_player
                
                finished = True
        
        except asyncio.CancelledError:
            return

        except Exception as exc:
            if self.loop_active:
                bot_client.coc_main_log.exception(
                    f"PLAYER LOOP ERROR: {tag}"
                    )
                await TaskLoop.report_fatal_error(
                    message=f"PLAYER LOOP ERROR: {tag}",
                    error=exc,
                    )
            return self.unlock(lock)
        
        finally:
            if finished:
                et = pendulum.now()
                try:
                    runtime = et - st
                    self.run_time.append(runtime.total_seconds())
                except:
                    pass