import asyncio
import coc
import pendulum

from ..api_client import BotClashClient as client
from ..exceptions import InvalidTag, ClashAPIError

from redbot.core.utils import AsyncIter

from .default import TaskLoop

from ..discord.feeds.capital_contribution import CapitalContributionFeed

from ..coc_objects.players.player import aPlayer, db_PlayerStats
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
                await new_player.current_season.add_time_in_home_clan(new_player.timestamp.int_timestamp - old_player.timestamp.int_timestamp)
        except:
            bot_client.coc_main_log.exception(f"{new_player.tag}: Error in Player Home Clan Timer task.")

    @staticmethod
    async def player_last_seen_main(old_player:aPlayer,new_player:aPlayer):
        try:
            update = False

            if old_player.name != new_player.name:
                update = True        
            if old_player.war_opted_in != None and new_player.war_opted_in != None and old_player.war_opted_in != new_player.war_opted_in:
                update = True        
            if old_player.label_ids != new_player.label_ids:
                update = True
            
            if update:
                await new_player.current_season.add_last_seen(new_player.timestamp)
        except:
            bot_client.coc_main_log.exception(f"{new_player.tag}: Error in Player Last Seen Main task.")

    @staticmethod
    async def player_last_seen_achievement(old_player:aPlayer,new_player:aPlayer,achievement:coc.Achievement):
        try:
            if achievement.name in activity_achievements:
                old_ach = old_player.get_achievement(achievement.name)
                new_ach = new_player.get_achievement(achievement.name)

                if old_ach.value != new_ach.value:
                    await new_player.current_season.add_last_seen(new_player.timestamp)
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
            if new_player.current_season.attacks._prior_seen:
                increment = new_player.attack_wins - new_player.current_season.attacks.last_update
            else:
                increment = new_player.attack_wins - old_player.attack_wins
            
            stat = await new_player.current_season.attacks.increment_stat(
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
            if new_player.current_season.defenses._prior_seen:
                increment = new_player.defense_wins - new_player.current_season.defenses.last_update
            else:
                increment = new_player.defense_wins - old_player.defense_wins

            stat = await new_player.current_season.defenses.increment_stat(
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
            if new_player.current_season.donations._prior_seen:
                increment = new_player.donations - new_player.current_season.donations.last_update
            else:
                increment = new_player.donations - old_player.donations
            
            stat = await new_player.current_season.donations.increment_stat(
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
            if new_player.current_season.received._prior_seen:
                increment = new_player.received - new_player.current_season.received.last_update
            else:
                increment = new_player.received - old_player.received

            stat = await new_player.current_season.received.increment_stat(
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
            #Loot Gold
            if achievement.name == "Gold Grab":
                old_ach = old_player.get_achievement(achievement.name)
                new_ach = new_player.get_achievement(achievement.name)

                if new_player.current_season.loot_gold._prior_seen:
                    increment = new_ach.value - new_player.current_season.loot_gold.last_update
                else:
                    increment = new_ach.value - old_ach.value

                stat = await new_player.current_season.loot_gold.increment_stat(
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

                if new_player.current_season.loot_elixir._prior_seen:
                    increment = new_ach.value - new_player.current_season.loot_elixir.last_update
                else:
                    increment = new_ach.value - old_ach.value

                stat = await new_player.current_season.loot_elixir.increment_stat(
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

                if new_player.current_season.loot_darkelixir._prior_seen:
                    increment = new_ach.value - new_player.current_season.loot_darkelixir.last_update
                else:
                    increment = new_ach.value - old_ach.value

                stat = await new_player.current_season.loot_darkelixir.increment_stat(
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
            #Capital Contribution
            if achievement.name == "Most Valuable Clanmate":
                old_ach = old_player.get_achievement(achievement.name)
                new_ach = new_player.get_achievement(achievement.name)

                if new_player.current_season.capitalcontribution._prior_seen:
                    increment = new_ach.value - new_player.current_season.capitalcontribution.last_update
                else:
                    increment = new_ach.value - old_ach.value

                stat = await new_player.current_season.capitalcontribution.increment_stat(
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
            if achievement.name == "Games Champion":
                old_ach = old_player.get_achievement(achievement.name)
                new_ach = new_player.get_achievement(achievement.name)

                if new_ach.value != old_ach.value:
                    increment = new_ach.value - old_ach.value

                    await new_player.current_season.clangames.update(
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
    _loops = {}
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

    def __new__(cls,player_tag:str):
        if player_tag not in cls._loops:
            instance = super().__new__(cls)
            instance._is_new = True
            cls._loops[player_tag] = instance
        return cls._loops[player_tag]

    def __init__(self,player_tag:str):
        self.tag = player_tag
        
        if self._is_new:
            super().__init__()
            self._is_new = False
            self._lock = asyncio.Lock()
            self.cached_player = None

    async def start(self):
        i = await super().start()
        if i:
            bot_client.coc_main_log.debug(f"{self.tag}: Player Loop started.")
    
    async def stop(self):        
        await super().stop()
        self.unlock(self._lock)
        try:
            self.main_log.debug(f"{self.tag}: Player Loop stopped.")
        except:
            pass
    
    @property
    def delay_multiplier(self) -> float:
        if not self.cached_player:
            return 1
        if self.cached_player.is_member:
            return 1
        if getattr(self.cached_player.clan,'is_registered_clan',False):
            return 1.5
        if getattr(self.cached_player.clan,'is_active_league_clan',False):
            return 1.5
        if bot_client.bot.get_user(self.cached_player.discord_user):
            return 2
        return 3
    
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

    ##################################################
    ### PRIMARY TASK LOOP
    ##################################################
    async def _loop_task(self):
        try:
            while self.loop_active:
                await asyncio.sleep(10)
                if self.api_maintenance:
                    continue
                await self._run_single_loop()
        
        except asyncio.CancelledError:
            return await self.stop()
        
        except Exception as exc:
            if not self.loop_active:
                return await self.stop()
            
            bot_client.coc_main_log.exception(
                f"{self.tag}: FATAL PLAYER LOOP ERROR. Attempting restart. {exc}"
                )
            await TaskLoop.report_fatal_error(
                message="FATAL PLAYER LOOP ERROR",
                error=exc,
                )
            await self.stop()
            return await self.start()
    
    async def _run_single_loop(self):
        if self._lock.locked():
            return        
        await self._lock.acquire()
        
        if self.task_lock.locked():
            if self.to_defer:
                self.defer_count += 1
                self.deferred = True
                return self.unlock(self._lock)
            else:
                async with self.task_lock:
                    await asyncio.sleep(0)
            
        async with self.task_semaphore:
            self.deferred = False
            self.defer_count = 0
            st = pendulum.now()

            new_player = None
            try:
                new_player = await self.coc_client.fetch_player(self.tag,no_cache=True,enforce_lock=True)
            except InvalidTag as exc:
                raise asyncio.CancelledError from exc
            except ClashAPIError as exc:
                return
            finally:
                wait = int(min(getattr(new_player,'_response_retry',default_sleep) * self.delay_multiplier,300))
                self.loop.call_later(wait,self.unlock,self._lock)

            if self.cached_player:
                old_player = self.cached_player
                await self._dispatch_events(old_player,new_player)
            
            self.cached_player = new_player

            et = pendulum.now()
            runtime = et-st
            self.run_time.append(runtime.total_seconds())
    
    async def _dispatch_events(self,old_player:aPlayer,new_player:aPlayer):
        asyncio.create_task(new_player._sync_cache())
        for event in PlayerLoop._player_events:
            asyncio.create_task(event(old_player,new_player))

        achievement_iter = AsyncIter(new_player.achievements)
        async for achievement in achievement_iter:
            for event in PlayerLoop._achievement_events:
                asyncio.create_task(event(old_player,new_player,achievement))