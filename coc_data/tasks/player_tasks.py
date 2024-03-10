import coc
import logging
import asyncio

from typing import *
from redbot.core.utils import AsyncIter, bounded_gather

from coc_main.client.global_client import GlobalClient

from coc_main.coc_objects.season.season import aClashSeason
from coc_main.coc_objects.players.player import aPlayer
from coc_main.coc_objects.players.player_season import aPlayerSeason
from coc_main.coc_objects.players.player_activity import aPlayerActivity

from coc_main.utils.constants.coc_constants import HeroAvailability, TroopAvailability, SpellAvailability, PetAvailability

default_sleep = 60
LOG = logging.getLogger("coc.data")

############################################################
############################################################
#####
##### DEFAULT PLAYER TASKS
#####
############################################################
############################################################
class PlayerTasks():

    @coc.PlayerEvents._create_snapshot()
    async def on_player_check_snapshot(old_player:aPlayer,new_player:aPlayer):
        if not new_player._create_snapshot:
            return
        
        async def create_snapshot(player:aPlayer):
            await aPlayerActivity.create_new(
                player=player,
                timestamp=player.timestamp,
                activity="snapshot",
                )
            
            all_seasons = aClashSeason.all_seasons()        
            player_seasons = await bounded_gather(*[player.get_season_stats(s) for s in all_seasons])
            await bounded_gather(*[s.create_member_snapshot() for s in player_seasons if isinstance(s,aPlayerSeason)])
            
            LOG.debug(f"{player.tag} {player.name}: Created player snapshots.")

        task = asyncio.create_task(create_snapshot(new_player))
        await GlobalClient.task_queue.put(task)
    
    @coc.PlayerEvents.name()
    async def on_player_update_name(old_player:aPlayer,new_player:aPlayer):        
        
        task = asyncio.create_task(aPlayerActivity.create_new(
            player=new_player,
            timestamp=new_player.timestamp,
            activity="change_name",
            new_value=new_player.name
            ))
        await GlobalClient.task_queue.put(task)
        LOG.debug(f"{new_player.tag} {new_player.name}: Name Change from {old_player.name} to {new_player.name}.")
    
    @coc.PlayerEvents.war_opted_in()
    async def on_player_update_war_opted_in(old_player:aPlayer,new_player:aPlayer):
        if old_player.war_opted_in != None and new_player.war_opted_in != None:         
            task = asyncio.create_task(aPlayerActivity.create_new(
                player=new_player,
                timestamp=new_player.timestamp,
                activity="change_war_option",
                new_value=new_player.war_opted_in
                ))
            await GlobalClient.task_queue.put(task)
            LOG.debug(f"{new_player.tag} {new_player.name}: War Opt In from {old_player.war_opted_in} to {new_player.war_opted_in}.")
    
    @coc.PlayerEvents.label_ids()
    async def on_player_update_labels(old_player:aPlayer,new_player:aPlayer):
        task = asyncio.create_task(aPlayerActivity.create_new(
            player=new_player,
            timestamp=new_player.timestamp,
            activity="change_label",
            new_value=new_player.label_ids
            ))
        await GlobalClient.task_queue.put(task)
        LOG.debug(f"{new_player.tag} {new_player.name}: Labels changed to {new_player.label_ids}.")
    
    @coc.PlayerEvents.town_hall_level()
    async def on_player_upgrade_townhall(old_player:aPlayer,new_player:aPlayer):        
        task = asyncio.create_task(aPlayerActivity.create_new(
            player=new_player,
            timestamp=new_player.timestamp,
            activity="upgrade_townhall",
            change=new_player.town_hall.level - old_player.town_hall.level,
            new_value=new_player.town_hall.level
            ))
        await GlobalClient.task_queue.put(task)
        LOG.debug(f"{new_player.tag} {new_player.name}: Townhall upgraded to {new_player.town_hall.description}.")
    
    @coc.PlayerEvents.town_hall_weapon()
    async def on_player_upgrade_townhall_weapon(old_player:aPlayer,new_player:aPlayer):
        task = asyncio.create_task(aPlayerActivity.create_new(
            player=new_player,
            timestamp=new_player.timestamp,
            activity="upgrade_townhall_weapon",
            change=max(0,new_player.town_hall.weapon - old_player.town_hall.weapon),
            new_value=new_player.town_hall.weapon
            ))
        await GlobalClient.task_queue.put(task)
        LOG.debug(f"{new_player.tag} {new_player.name}: Townhall Weapon upgraded to {new_player.town_hall.description}.")
    
    @coc.PlayerEvents.hero_strength()
    async def on_player_upgrade_hero(old_player:aPlayer,new_player:aPlayer):

        async def _check_upgrade(old_player:aPlayer,new_player:aPlayer,hero:str):
            old_hero = old_player.get_hero(hero)
            new_hero = new_player.get_hero(hero)

            if getattr(new_hero,'level',0) > getattr(old_hero,'level',0):
                await aPlayerActivity.create_new(
                    player=new_player,
                    timestamp=new_player.timestamp,
                    activity="upgrade_hero",
                    stat=hero,
                    change=getattr(new_hero,'level',0) - getattr(old_hero,'level',0),
                    new_value=new_hero.level
                    )
                LOG.debug(f"{new_player.tag} {new_player.name}: {hero} upgraded to {new_hero.level}.")        

        heroes = HeroAvailability.return_all_unlocked(new_player.town_hall.level)
        a_iter = AsyncIter(heroes)
        async for hero in a_iter:
            task = asyncio.create_task(_check_upgrade(old_player,new_player,hero))
            await GlobalClient.task_queue.put(task)
    
    @coc.PlayerEvents.troop_strength()
    async def on_player_upgrade_troops(old_player:aPlayer,new_player:aPlayer):

        async def _check_troop_upgrade(old_player:aPlayer,new_player:aPlayer,troop:str):
            old_troop = old_player.get_troop(troop)
            new_troop = new_player.get_troop(troop)

            if getattr(new_troop,'level',0) > getattr(old_troop,'level',0):
                await aPlayerActivity.create_new(
                    player=new_player,
                    timestamp=new_player.timestamp,
                    activity="upgrade_troop",
                    stat=troop,
                    change=getattr(new_troop,'level',0) - getattr(old_troop,'level',0),
                    new_value=new_troop.level
                    )
                LOG.debug(f"{new_player.tag} {new_player.name}: {troop} upgraded to {new_troop.level}.")
        
        async def _check_pet_upgrade(old_player:aPlayer,new_player:aPlayer,pet:str):
            old_troop = old_player.get_pet(pet)
            new_troop = new_player.get_pet(pet)

            if getattr(new_troop,'level',0) > getattr(old_troop,'level',0):
                await aPlayerActivity.create_new(
                    player=new_player,
                    timestamp=new_player.timestamp,
                    activity="upgrade_troop",
                    stat=pet,
                    change=getattr(new_troop,'level',0) - getattr(old_troop,'level',0),
                    new_value=new_troop.level
                    )
                LOG.debug(f"{new_player.tag} {new_player.name}: {pet} upgraded to {new_troop.level}.")
        
        troops = TroopAvailability.return_all_unlocked(new_player.town_hall.level)
        troop_iter = AsyncIter(troops)
        async for t in troop_iter:
            task = asyncio.create_task(_check_troop_upgrade(old_player,new_player,t))
            await GlobalClient.task_queue.put(task)
        
        pets = PetAvailability.return_all_unlocked(new_player.town_hall.level)
        pet_iter = AsyncIter(pets)
        async for p in pet_iter:
            task = asyncio.create_task(_check_pet_upgrade(old_player,new_player,p))
            await GlobalClient.task_queue.put(task)
    
    @coc.PlayerEvents.spell_strength()
    async def on_player_upgrade_spells(old_player:aPlayer,new_player:aPlayer):
        
        async def _check_spell_upgrade(old_player:aPlayer,new_player:aPlayer,spell:str):
            old_spell = old_player.get_spell(spell)
            new_spell = new_player.get_spell(spell)

            if getattr(new_spell,'level',0) > getattr(old_spell,'level',0):
                await aPlayerActivity.create_new(
                    player=new_player,
                    timestamp=new_player.timestamp,
                    activity="upgrade_spell",
                    stat=spell,
                    change=getattr(new_spell,'level',0) - getattr(old_spell,'level',0),
                    new_value=new_spell.level
                    )
                LOG.debug(f"{new_player.tag} {new_player.name}: {spell} upgraded to {new_spell.level}.")

        spells = SpellAvailability.return_all_unlocked(new_player.town_hall.level)
        a_iter = AsyncIter(spells)
        async for spell in a_iter:
            task = asyncio.create_task(_check_spell_upgrade(old_player,new_player,spell))
            await GlobalClient.task_queue.put(task)
    
    @coc.PlayerEvents.clan_tag()
    async def on_player_update_clan(old_player:aPlayer,new_player:aPlayer):
        if old_player.clan_tag:            
            task = asyncio.create_task(aPlayerActivity.create_new(
                player=old_player,
                timestamp=new_player.timestamp,
                activity="leave_clan"
                ))
            await GlobalClient.task_queue.put(task)
            LOG.debug(f"{old_player.tag} {old_player.name}: Left Clan {old_player.clan.tag} {old_player.clan.name}.")
        
        if new_player.clan_tag:
            task = asyncio.create_task(aPlayerActivity.create_new(
                player=new_player,
                timestamp=new_player.timestamp,
                activity="join_clan",
                ))
            await GlobalClient.task_queue.put(task)
            LOG.debug(f"{new_player.tag} {new_player.name}: Joined Clan {new_player.clan.tag} {new_player.clan.name}.")
    
    @coc.PlayerEvents.trophies()
    async def on_player_update_trophies(old_player:aPlayer,new_player:aPlayer):
        task = asyncio.create_task(aPlayerActivity.create_new(
            player=new_player,
            timestamp=new_player.timestamp,
            activity="trophies",
            change=new_player.trophies - old_player.trophies,
            new_value=new_player.trophies
            ))
        await GlobalClient.task_queue.put(task)
        LOG.debug(f"{new_player.tag} {new_player.name}: Trophies changed to {new_player.trophies} ({new_player.trophies - old_player.trophies}).")
    
    @coc.PlayerEvents.attack_wins()
    async def on_player_update_attack_wins(old_player:aPlayer,new_player:aPlayer):

        async def _check_attack_wins(old_player:aPlayer,new_player:aPlayer):
            last_stat = await aPlayerActivity.get_last_for_player_by_type(new_player.tag,'attack_wins')
            ref_value = last_stat.new_value if last_stat else old_player.attack_wins
            change = max(0,new_player.attack_wins - ref_value)

            await aPlayerActivity.create_new(
                player=new_player,
                timestamp=new_player.timestamp,
                activity="attack_wins",
                change=change,
                new_value=new_player.attack_wins
                )            
            LOG.debug(f"{new_player.tag} {new_player.name}: Attack Wins changed to {new_player.attack_wins} (+{change}).")

        task = asyncio.create_task(_check_attack_wins(old_player,new_player))
        await GlobalClient.task_queue.put(task)
    
    @coc.PlayerEvents.defense_wins()
    async def on_player_update_defense_wins(old_player:aPlayer,new_player:aPlayer):

        async def _check_defense_wins(old_player:aPlayer,new_player:aPlayer):
            last_stat = await aPlayerActivity.get_last_for_player_by_type(new_player.tag,'defense_wins')
            ref_value = last_stat.new_value if last_stat else old_player.defense_wins
            change = max(0,new_player.defense_wins - ref_value)

            await aPlayerActivity.create_new(
                player=new_player,
                timestamp=new_player.timestamp,
                activity="defense_wins",
                change=change,
                new_value=new_player.defense_wins
                )
            LOG.debug(f"{new_player.tag} {new_player.name}: Defense Wins changed to {new_player.defense_wins} (+{change}).")
        
        task = asyncio.create_task(_check_defense_wins(old_player,new_player))
        await GlobalClient.task_queue.put(task)
    
    @coc.PlayerEvents.war_stars()
    async def on_player_update_war_stars(old_player:aPlayer,new_player:aPlayer):
        
        async def _check_war_stars(old_player:aPlayer,new_player:aPlayer):
            last_stat = await aPlayerActivity.get_last_for_player_by_type(new_player.tag,'war_stars')
            ref_value = last_stat.new_value if last_stat else old_player.war_stars
            change = max(0,new_player.war_stars - ref_value)

            await aPlayerActivity.create_new(
                player=new_player,
                timestamp=new_player.timestamp,
                activity="war_stars",
                change=change,
                new_value=new_player.war_stars
                )
            LOG.debug(f"{new_player.tag} {new_player.name}: War Stars changed to {new_player.war_stars} (+{change}).")

        task = asyncio.create_task(_check_war_stars(old_player,new_player))
        await GlobalClient.task_queue.put(task)
    
    @coc.PlayerEvents.donations()
    async def on_player_update_donations(old_player:aPlayer,new_player:aPlayer):

        async def _check_donations(old_player:aPlayer,new_player:aPlayer):
            last_stat = await aPlayerActivity.get_last_for_player_by_type(new_player.tag,'donations_sent')
            ref_value = last_stat.new_value if last_stat else old_player.donations
            change = max(0,new_player.donations - ref_value)

            await aPlayerActivity.create_new(
                player=new_player,
                timestamp=new_player.timestamp,
                activity="donations_sent",
                change=change,
                new_value=new_player.donations
                )
            LOG.debug(f"{new_player.tag} {new_player.name}: Donations Sent changed to {new_player.donations} (+{change}).")

        task = asyncio.create_task(_check_donations(old_player,new_player))
        await GlobalClient.task_queue.put(task)
    
    @coc.PlayerEvents.received()
    async def on_player_update_received(old_player:aPlayer,new_player:aPlayer):

        async def _check_received(old_player:aPlayer,new_player:aPlayer):
            last_stat = await aPlayerActivity.get_last_for_player_by_type(new_player.tag,'donations_received')
            ref_value = last_stat.new_value if last_stat else old_player.received
            change = max(0,new_player.received - ref_value)

            await aPlayerActivity.create_new(
                player=new_player,
                timestamp=new_player.timestamp,
                activity="donations_received",
                change=change,
                new_value=new_player.received
                )
            LOG.debug(f"{new_player.tag} {new_player.name}: Donations Rcvd changed to {new_player.received} (+{change}).")
        
        task = asyncio.create_task(_check_received(old_player,new_player))
        await GlobalClient.task_queue.put(task)
    
    @coc.PlayerEvents.clan_capital_contributions()
    async def on_player_update_capital_contributions(old_player:aPlayer,new_player:aPlayer):

        async def _check_capital_contribution(old_player:aPlayer,new_player:aPlayer):
            last_stat = await aPlayerActivity.get_last_for_player_by_type(new_player.tag,'capital_contribution')
            ref_value = last_stat.new_value if last_stat else old_player.clan_capital_contributions
            change = max(0,new_player.clan_capital_contributions - ref_value)

            await aPlayerActivity.create_new(
                player=new_player,
                timestamp=new_player.timestamp,
                activity="capital_contribution",
                change=change,
                new_value=new_player.clan_capital_contributions
                )
            LOG.debug(f"{new_player.tag} {new_player.name}: Capital Contribution changed to {new_player.clan_capital_contributions} (+{change}).")
        
        task = asyncio.create_task(_check_capital_contribution(old_player,new_player))
        await GlobalClient.task_queue.put(task)
    
    @coc.PlayerEvents.capital_gold_looted()
    async def on_player_update_loot_capital_gold(old_player:aPlayer,new_player:aPlayer):

        async def _check_capital_gold_looted(old_player:aPlayer,new_player:aPlayer):
            last_stat = await aPlayerActivity.get_last_for_player_by_type(new_player.tag,'loot_capital_gold')
            ref_value = last_stat.new_value if last_stat else old_player.capital_gold_looted
            change = max(0,new_player.capital_gold_looted - ref_value)

            await aPlayerActivity.create_new(
                player=new_player,
                timestamp=new_player.timestamp,
                activity="loot_capital_gold",
                change=change,
                new_value=new_player.capital_gold_looted
                )
            LOG.debug(f"{new_player.tag} {new_player.name}: Capital Gold Looted changed to {new_player.capital_gold_looted} (+{change}).")
        
        task = asyncio.create_task(_check_capital_gold_looted(old_player,new_player))
        await GlobalClient.task_queue.put(task)
    
    @coc.PlayerEvents.loot_gold()
    async def on_player_update_loot_gold(old_player:aPlayer,new_player:aPlayer):

        async def _check_loot_gold(old_player:aPlayer,new_player:aPlayer):
            last_stat = await aPlayerActivity.get_last_for_player_by_type(new_player.tag,'loot_gold')
            ref_value = last_stat.new_value if last_stat else old_player.loot_gold
            change = max(0,new_player.loot_gold - ref_value)

            await aPlayerActivity.create_new(
                player=new_player,
                timestamp=new_player.timestamp,
                activity="loot_gold",
                change=change,
                new_value=new_player.loot_gold
                )
            LOG.debug(f"{new_player.tag} {new_player.name}: Loot Gold changed to {new_player.loot_gold} (+{change}).")
        
        task = asyncio.create_task(_check_loot_gold(old_player,new_player))
        await GlobalClient.task_queue.put(task)
    
    @coc.PlayerEvents.loot_gold()
    async def on_player_update_loot_elixir(old_player:aPlayer,new_player:aPlayer):

        async def _check_loot_elixir(old_player:aPlayer,new_player:aPlayer):
            last_stat = await aPlayerActivity.get_last_for_player_by_type(new_player.tag,'loot_elixir')
            ref_value = last_stat.new_value if last_stat else old_player.loot_elixir
            change = max(0,new_player.loot_elixir - ref_value)

            await aPlayerActivity.create_new(
                player=new_player,
                timestamp=new_player.timestamp,
                activity="loot_elixir",
                change=change,
                new_value=new_player.loot_elixir
                )
            LOG.debug(f"{new_player.tag} {new_player.name}: Loot Elixir changed to {new_player.loot_elixir} (+{change}).")
        
        task = asyncio.create_task(_check_loot_elixir(old_player,new_player))
        await GlobalClient.task_queue.put(task)
    
    @coc.PlayerEvents.loot_darkelixir()
    async def on_player_update_loot_darkelixir(old_player:aPlayer,new_player:aPlayer):

        async def _check_loot_darkelixir(old_player:aPlayer,new_player:aPlayer):
            last_stat = await aPlayerActivity.get_last_for_player_by_type(new_player.tag,'loot_darkelixir')
            ref_value = last_stat.new_value if last_stat else old_player.loot_darkelixir
            change = max(0,new_player.loot_darkelixir - ref_value)

            await aPlayerActivity.create_new(
                player=new_player,
                timestamp=new_player.timestamp,
                activity="loot_darkelixir",
                change=change,
                new_value=new_player.loot_darkelixir
                )
            LOG.debug(f"{new_player.tag} {new_player.name}: Loot Dark Elixir changed to {new_player.loot_darkelixir} (+{change}).")
        
        task = asyncio.create_task(_check_loot_darkelixir(old_player,new_player))
        await GlobalClient.task_queue.put(task)
    
    @coc.PlayerEvents.clan_games()
    async def on_player_update_clan_games(old_player:aPlayer,new_player:aPlayer):

        async def _check_clan_games(old_player:aPlayer,new_player:aPlayer):
            last_stat = await aPlayerActivity.get_last_for_player_by_type(new_player.tag,'clan_games')
            ref_value = last_stat.new_value if last_stat else old_player.clan_games
            await aPlayerActivity.create_new(
                player=new_player,
                timestamp=new_player.timestamp,
                activity="clan_games",
                change=max(0,new_player.clan_games - ref_value),
                new_value=new_player.clan_games
                )
            LOG.debug(f"{new_player.tag} {new_player.name}: Clan Games changed to {new_player.clan_games} (+{max(0,new_player.clan_games - ref_value)}).")
            
        task = asyncio.create_task(_check_clan_games(old_player,new_player))
        await GlobalClient.task_queue.put(task)