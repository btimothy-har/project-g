import asyncio
import coc
import pendulum
import copy
import random

from typing import *
from ..api_client import BotClashClient as client
from ..exceptions import InvalidTag, ClashAPIError

from redbot.core.utils import AsyncIter, bounded_gather

from .default import TaskLoop

from ..discord.feeds.capital_contribution import CapitalContributionFeed

from ..coc_objects.players.player import db_Player, aPlayer, db_PlayerStats
from ..utils.constants.coc_constants import activity_achievements

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
            # if not new_player.is_member:
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
            if not new_player.is_member:
                return
            
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
        def _update_in_db(db_id,stat_json):
            db_PlayerStats.objects(
                stats_id=db_id
                ).update_one(
                    set__attacks=stat_json,
                    upsert=True
                    )
        try:
            # if not new_player.is_member:
            #     return
            
            current_season = await new_player.get_current_season()
            if current_season.attacks._prior_seen:
                increment = new_player.attack_wins - current_season.attacks.last_update
            else:
                increment = new_player.attack_wins - old_player.attack_wins
            
            if increment > 0 or new_player.attack_wins != current_season.attacks.last_update:
                stat = await current_season.attacks.increment_stat(
                    increment=max(increment,0),
                    latest_value=new_player.attack_wins,
                    db_update=_update_in_db,
                    alliance=getattr(new_player.clan,'is_alliance_clan',False)
                    )
                bot_client.coc_data_log.debug(
                    f"{new_player.tag} {new_player.name}: attack_wins {'+' if increment >= 0 else ''}{increment:,} (new: {stat.season_total:,}). Received: {new_player.attack_wins} vs {old_player.attack_wins}."
                    )
        except:
            bot_client.coc_main_log.exception(f"{new_player.tag}: Error in Player Attack Wins task.")

    @staticmethod
    async def player_defense_wins(old_player:aPlayer,new_player:aPlayer):
        def _update_in_db(db_id,stat_json):
            db_PlayerStats.objects(
                stats_id=db_id
                ).update_one(
                    set__defenses=stat_json,
                    upsert=True
                    )
        try:
            # if not new_player.is_member:
            #     return
            
            current_season = await new_player.get_current_season()
            if current_season.defenses._prior_seen:
                increment = new_player.defense_wins - current_season.defenses.last_update
            else:
                increment = new_player.defense_wins - old_player.defense_wins

            if increment > 0 or new_player.defense_wins != current_season.defenses.last_update:
                stat = await current_season.defenses.increment_stat(
                    increment=max(increment,0),
                    latest_value=new_player.defense_wins,
                    db_update=_update_in_db,
                    alliance=getattr(new_player.clan,'is_alliance_clan',False)
                    )
                bot_client.coc_data_log.debug(
                    f"{new_player.tag} {new_player.name}: defense_wins {'+' if increment >= 0 else ''}{increment:,} (new: {stat.season_total:,}). Received: {new_player.defense_wins} vs {old_player.defense_wins}."
                    )
        except:
            bot_client.coc_main_log.exception(f"{new_player.tag}: Error in Player Defense Wins task.")

    @staticmethod
    async def player_donations_sent(old_player:aPlayer,new_player:aPlayer):
        def _update_in_db(db_id,stat_json):
            db_PlayerStats.objects(
                stats_id=db_id
                ).update_one(
                    set__donations_sent=stat_json,
                    upsert=True
                    )
        try:
            # if not new_player.is_member:
            #     return
            
            current_season = await new_player.get_current_season()            
            if current_season.donations._prior_seen:
                increment = new_player.donations - current_season.donations.last_update
            else:
                increment = new_player.donations - old_player.donations
            
            if increment > 0 or new_player.donations != current_season.donations.last_update:
                stat = await current_season.donations.increment_stat(
                    increment=max(increment,0),
                    latest_value=new_player.donations,
                    db_update=_update_in_db,
                    alliance=getattr(new_player.clan,'is_alliance_clan',False)
                    )
                bot_client.coc_data_log.debug(
                    f"{new_player.tag} {new_player.name}: donations_sent {'+' if increment >= 0 else ''}{increment:,} (new: {stat.season_total:,}). Received: {new_player.donations} vs {old_player.donations}."
                    )
        except:
            bot_client.coc_main_log.exception(f"{new_player.tag}: Error in Player Donations Sent task.")

    @staticmethod
    async def player_donations_received(old_player:aPlayer,new_player:aPlayer):
        def _update_in_db(db_id,stat_json):
            db_PlayerStats.objects(
                stats_id=db_id
                ).update_one(
                    set__donations_rcvd=stat_json,
                    upsert=True
                    )
        try:
            # if not new_player.is_member:
            #     return
            
            current_season = await new_player.get_current_season()            
            if current_season.received._prior_seen:
                increment = new_player.received - current_season.received.last_update
            else:
                increment = new_player.received - old_player.received

            if increment > 0 or new_player.received != current_season.received.last_update:
                stat = await current_season.received.increment_stat(
                    increment=max(increment,0),
                    latest_value=new_player.received,
                    db_update=_update_in_db,
                    alliance=getattr(new_player.clan,'is_alliance_clan',False)
                    )
                bot_client.coc_data_log.debug(
                    f"{new_player.tag} {new_player.name}: donations_rcvd {'+' if increment >= 0 else ''}{increment:,} (new: {stat.season_total:,}). Received: {new_player.received} vs {old_player.received}."
                    )
        except:
            bot_client.coc_main_log.exception(f"{new_player.tag}: Error in Player Donations Rcvd task.")
    
    @staticmethod
    async def player_stat_achievements(old_player:aPlayer,new_player:aPlayer,achievement:coc.Achievement):
        def _update_gold_db(db_id,stat_json):
            db_PlayerStats.objects(
                stats_id=db_id
                ).update_one(
                    set__loot_gold=stat_json,
                    upsert=True
                    )
        def _update_elixir_db(db_id,stat_json):
            db_PlayerStats.objects(
                stats_id=db_id
                ).update_one(
                    set__loot_elixir=stat_json,
                    upsert=True
                    )        
        def _update_darkelixir_db(db_id,stat_json):
            db_PlayerStats.objects(
                stats_id=db_id
                ).update_one(
                    set__loot_darkelixir=stat_json,
                    upsert=True
                    )
        try:
            # if not new_player.is_member:
            #     return
            
            current_season = await new_player.get_current_season()

            #Loot Gold
            if achievement.name == "Gold Grab":
                old_ach = old_player.get_achievement(achievement.name)
                new_ach = new_player.get_achievement(achievement.name)

                if current_season.loot_gold._prior_seen:
                    increment = new_ach.value - current_season.loot_gold.last_update
                else:
                    increment = new_ach.value - old_ach.value
                
                if increment > 0 or new_ach.value != current_season.loot_gold.last_update:
                    stat = await current_season.loot_gold.increment_stat(
                        increment=max(increment,0),
                        latest_value=new_ach.value,
                        db_update=_update_gold_db,
                        alliance=getattr(new_player.clan,'is_alliance_clan',False)
                        )                
                    bot_client.coc_data_log.debug(
                        f"{new_player.tag} {new_player.name}: loot_gold {'+' if increment >= 0 else ''}{increment:,} (new: {stat.season_total:,}). Received: {new_ach.value:,} vs {old_ach.value:,}."
                        )
            
            #Loot Elixir
            if achievement.name == "Elixir Escapade":
                old_ach = old_player.get_achievement(achievement.name)
                new_ach = new_player.get_achievement(achievement.name)

                if current_season.loot_elixir._prior_seen:
                    increment = new_ach.value - current_season.loot_elixir.last_update
                else:
                    increment = new_ach.value - old_ach.value

                if increment > 0 or new_ach.value != current_season.loot_elixir.last_update:
                    stat = await current_season.loot_elixir.increment_stat(
                        increment=max(increment,0),
                        latest_value=new_ach.value,
                        db_update=_update_elixir_db,
                        alliance=getattr(new_player.clan,'is_alliance_clan',False)
                        )
                    
                    bot_client.coc_data_log.debug(
                        f"{new_player.tag} {new_player.name}: loot_elixir {'+' if increment >= 0 else ''}{increment:,} (new: {stat.season_total:,}). Received: {new_ach.value:,} vs {old_ach.value:,}."
                        )
            
            #Loot Dark Elixir
            if achievement.name == "Heroic Heist":
                old_ach = old_player.get_achievement(achievement.name)
                new_ach = new_player.get_achievement(achievement.name)

                if current_season.loot_darkelixir._prior_seen:
                    increment = new_ach.value - current_season.loot_darkelixir.last_update
                else:
                    increment = new_ach.value - old_ach.value
                
                if increment > 0 or new_ach.value != current_season.loot_darkelixir.last_update:
                    stat = await current_season.loot_darkelixir.increment_stat(
                        increment=max(increment,0),
                        latest_value=new_ach.value,
                        db_update=_update_darkelixir_db,
                        alliance=getattr(new_player.clan,'is_alliance_clan',False)
                        )
                    
                    bot_client.coc_data_log.debug(
                        f"{new_player.tag} {new_player.name}: loot_darkelixir {'+' if increment >= 0 else ''}{increment:,} (new: {stat.season_total:,}). Received: {new_ach.value:,} vs {old_ach.value:,}."
                        )
        except:
            bot_client.coc_main_log.exception(f"{new_player.tag}: Error in Player Loot Achievements task.")

    @staticmethod
    async def player_capital_contribution(old_player:aPlayer,new_player:aPlayer,achievement:coc.Achievement):
        def _update_capitalcontribution_db(db_id,stat_json):
            db_PlayerStats.objects(
                stats_id=db_id
                ).update_one(
                    set__capitalcontribution=stat_json,
                    upsert=True
                    )
        try:
            # if not new_player.is_member:
            #     return
            
            current_season = await new_player.get_current_season()
            
            #Capital Contribution
            if achievement.name == "Most Valuable Clanmate":
                old_ach = old_player.get_achievement(achievement.name)
                new_ach = new_player.get_achievement(achievement.name)

                if current_season.capitalcontribution._prior_seen:
                    increment = new_ach.value - current_season.capitalcontribution.last_update
                else:
                    increment = new_ach.value - old_ach.value
                
                if increment > 0 or new_ach.value != current_season.capitalcontribution.last_update:
                    stat = await current_season.capitalcontribution.increment_stat(
                        increment=max(increment,0),
                        latest_value=new_ach.value,
                        db_update=_update_capitalcontribution_db,
                        alliance=getattr(new_player.clan,'is_alliance_clan',False)
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
        def _update_clangames(db_id,stat_json):
            db_PlayerStats.objects(
                stats_id=db_id
                ).update_one(
                    set__clangames=stat_json,
                    upsert=True
                    )
        
        try:
            # if not new_player.is_member:
            #     return 
            
            current_season = await new_player.get_current_season()
            
            if achievement.name == "Games Champion":
                old_ach = old_player.get_achievement(achievement.name)
                new_ach = new_player.get_achievement(achievement.name)

                if new_ach.value != old_ach.value:
                    increment = new_ach.value - old_ach.value

                    await current_season.clangames.update(
                        increment=max(increment,0),
                        latest_value=new_ach.value,
                        timestamp=new_player.timestamp,
                        clan=new_player.clan,
                        db_update=_update_clangames
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
    _locks = {}
    
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
    
    def add_to_loop(self,tag:str):
        add, n_tag = super().add_to_loop(tag)
        if add:
            bot_client.coc_main_log.debug(f"Added {n_tag} to Player Loop.")
    
    def remove_to_loop(self,tag:str):
        remove, n_tag = super().remove_to_loop(tag)
        if remove:
            bot_client.coc_main_log.debug(f"Removed {n_tag} from Player Loop.")
    
    def delay_multiplier(self,player:Optional[aPlayer]=None) -> int:
        return 1
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
    
    def defer(self,player:Optional[aPlayer]=None) -> bool:
        return False
        if self.task_lock.locked():
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
        async def gather(*args):
            return await asyncio.gather(*args,return_exceptions=True)
        
        try:
            while self.loop_active:

                self._status = "Not Running"

                if self.api_maintenance:
                    await asyncio.sleep(10)
                    continue

                if self._queue.qsize() > 1000000:
                    while not self._queue.empty():
                        self._status = "On Hold"
                        await asyncio.sleep(10)
                        continue

                tags = copy.copy(self._tags)
                if len(tags) == 0:
                    await asyncio.sleep(10)
                    continue

                st = pendulum.now()
                self._running = True
                self._status = "Running"
                tasks = []
                
                scope_tags = random.sample(list(tags),min(len(tags),10000))                
                bot_client.coc_main_log.info(
                    f"Started loop for {len(scope_tags)} players."
                    )
                sleep = 10 / len(scope_tags)
                a_iter = AsyncIter(scope_tags)
                await self._run_single_loop('#LJC8V0GCJ')            
                async for tag in a_iter:
                    task = asyncio.create_task(self._run_single_loop(tag))
                    tasks.append(task)
                    await asyncio.sleep(sleep)

                self._last_loop = pendulum.now()
                self._running = False
                try:
                    runtime = self._last_loop-st
                    bot_client.coc_main_log.info(
                        f"Loop for {len(scope_tags)} players took {round(runtime.total_seconds(),2)} seconds."
                        )
                except:
                    pass

                wrap_task = asyncio.create_task(gather(*tasks))
                await self._queue.put(wrap_task)
                self._status = "Not Running"
                await asyncio.sleep(10)
                continue
        
        except Exception as exc:
            if self.loop_active:
                bot_client.coc_main_log.exception(
                    f"FATAL PLAYER LOOP ERROR. Attempting restart. {exc}"
                    )
                await TaskLoop.report_fatal_error(
                    message="FATAL PLAYER LOOP ERROR",
                    error=exc,
                    )
                await asyncio.sleep(60)
                await self._loop_task()
    
    async def _collector_task(self):
        try:
            while True:
                task = await self._queue.get()
                if task.done() or task.cancelled():
                    try:
                        await task
                    except asyncio.CancelledError:
                        continue
                    except Exception as exc:
                        if self.loop_active:
                            bot_client.coc_main_log.exception(f"PLAYER TASK ERROR: {exc}")
                            await TaskLoop.report_fatal_error(
                                message="PLAYER TASK ERROR",
                                error=exc,
                                )
                    finally:
                        self._queue.task_done()
                else:
                    await self._queue.put(task)
                
                await asyncio.sleep(0)
                        
        except asyncio.CancelledError:
            while not self._queue.empty():
                task = await self._queue.get()
                try:
                    await task
                except:
                    continue
                finally:
                    self._queue.task_done()                
                await asyncio.sleep(0)
    
    async def _run_single_loop(self,tag:str):
        try:
            lock = self._locks[tag]
        except KeyError:
            self._locks[tag] = lock = asyncio.Lock()

        try:
            async with self.task_semaphore:   
                if lock.locked():
                    return
                await lock.acquire()
                st = pendulum.now()

                cached_player = self._cached.get(tag,None)
                if self.defer(cached_player):
                    bot_client.coc_data_log.info(f"loop deferred")
                    return self.loop.call_later(10,self.unlock,lock)

                async with self.api_semaphore:
                    new_player = None
                    try:
                        new_player = await self.coc_client.fetch_player(tag)
                    except InvalidTag:
                        return self.loop.call_later(3600,self.unlock,lock)
                    except ClashAPIError:
                        return self.loop.call_later(10,self.unlock,lock)        

                await new_player._sync_cache()            
                
                wait = int(min(getattr(new_player,'_response_retry',default_sleep) * self.delay_multiplier(new_player),600))
                #wait = getattr(new_player,'_response_retry',default_sleep)
                self.loop.call_later(wait,self.unlock,lock)
                
                if cached_player:        
                    if new_player.timestamp.int_timestamp > getattr(cached_player,'timestamp',pendulum.now()).int_timestamp:
                        self._cached[tag] = new_player
                        await self._dispatch_events(cached_player,new_player)
                else:
                    self._cached[tag] = new_player

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
            et = pendulum.now()
            try:
                runtime = et - st
                self.run_time.append(runtime.total_seconds())
                if tag == "#LJC8V0GCJ":
                    bot_client.coc_main_log.info(f"Player Loop: {tag} took {round(runtime.total_seconds(),2)} seconds.")
            except:
                pass
            
    async def _dispatch_events(self,old_player:aPlayer,new_player:aPlayer):
        a_iter = AsyncIter(PlayerLoop._player_events)
        async for event in a_iter:
            task = asyncio.create_task(event(old_player,new_player))
            await self._queue.put(task)

        achievement_iter = AsyncIter(new_player.achievements)
        async for achievement in achievement_iter:
            a_iter = AsyncIter(PlayerLoop._achievement_events)
            async for event in a_iter:
                task = asyncio.create_task(event(old_player,new_player,achievement))
                await self._queue.put(task)