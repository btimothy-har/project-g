class EmojisClash:
    LOGO = "<:clashlogo:1048867909163810816>"
    EXP = "<:Exp:825654249475932170>"
    CLAN = "<:Clan:1109470668329853090>"
    CLANWAR = "<:ClanWars:1109470155513278467>"
    WARLEAGUES = "<:ClanWarLeagues:825752759948279848>"
    CLANGAMES = "<:ClanGames:834063648494190602>"
    CAPITALRAID = "<:CapitalRaids:1109470302452326551>"
    LABORATORY = "<:laboratory:1044904659917209651>"
    BLACKSMITH = "<:Smithy:1187488001006248047>"
    BOOKFIGHTING = "<:TotalTroopStrength:827730290491129856>"
    BOOKSPELLS = "<:TotalSpellStrength:827730290294259793>"
    BOOKHEROES = "<:TotalHeroStrength:827730291149635596>"
    ATTACK = "<:Attack:828103854814003211>"
    DEFENSE = "<:Defense:828103708956819467>"
    DONATIONSOUT = "<:donated:825574412589858886>"
    DONATIONSRCVD = "<:received:825574507045584916>"
    GOLD = "<:gold:825613041198039130>"
    ELIXIR = "<:elixir:825612858271596554>"
    DARKELIXIR = "<:darkelixir:825640568973033502>"
    CAPITALGOLD = "<:CapitalGoldContributed:971012592057339954>"
    RAIDMEDALS = "<:RaidMedals:983374303552753664>"
    STAR = "<:WarStars:825756777844178944>"
    THREESTARS = "<:Triple:1034033279411687434>"
    UNUSEDATTACK = "<:MissedHits:825755234412396575>"
    DESTRUCTION = "<:destruction:1112279414223425586>"
    CAPITALTROPHY = "<:capital_trophy:1079625435001933865>"
    WARLEAGUETROPHY = "<:war_league_trophy:1126180852326481921>"

class EmojisTownHall:
    TH1 = "<:01:1037000998566240256>"
    TH2 = "<:02:1037000999753228320>"
    TH3 = "<:03:1037001001275752498>"
    TH4 = "<:04:1037001002852827136>"
    TH5 = "<:05:1037001004106907708>"
    TH6 = "<:06:1037001005524590623>"
    TH7 = "<:07:1037001006879354910>"
    TH8 = "<:08:1037001008062140497>"
    TH9 = "<:09:1037001009207201832>"
    TH10 = "<:10:1045961362913902642>"
    TH11 = "<:11:1045961399563714560>"
    TH12 = "<:12:1045961448888741888>"
    TH13 = "<:13:1045961633131941889>"
    TH14 = "<:14:1045961676974997606>"
    TH15 = "<:15:1045961696939872276>"
    TH16 = "<:16:1182255918176546826>"

    @classmethod
    def get(cls, townhall:int):
        return getattr(cls, f"TH{townhall}", cls.TH1)

class EmojisBuilderHall:
    BH1 = "<:bb01:1037001017155395654>"
    BH2 = "<:bb02:1037001018526945350>"
    BH3 = "<:bb03:1037001020158513203>"
    BH4 = "<:bb04:1037001021374865509>"
    BH5 = "<:bb05:1037001022930952202>"
    BH6 = "<:bb06:1037001024080199871>"
    BH7 = "<:bb07:1037001025221054494>"
    BH8 = "<:bb08:1037001026294788116>"
    BH9 = "<:bb09:1037001027687297045>"
    BH10 = "<:bb10:1037001028854825472>"

    @classmethod
    def get(cls, builderhall:int):
        return getattr(cls, f"BH{builderhall}", cls.BH1)

class EmojisCapitalHall:
    CH1 = "<:Capital_Hall1:1038113658145886229>"
    CH2 = "<:Capital_Hall2:1038113660041711626>"
    CH3 = "<:Capital_Hall3:1038113661811695708>"
    CH4 = "<:Capital_Hall4:1038113663644602409>"
    CH5 = "<:Capital_Hall5:1038113665569792000>"
    CH6 = "<:Capital_Hall6:1038113667822129206>"
    CH7 = "<:Capital_Hall7:1038113669801844876>"
    CH8 = "<:Capital_Hall8:1038113671630573679>"
    CH9 = "<:Capital_Hall9:1038113673547362304>"
    CH10 = "<:Capital_Hall10:1038113473487441970>"

    @classmethod
    def get(cls, capitalhall:int):
        return getattr(cls, f"CH{capitalhall}", cls.CH1)

class EmojisLeagues:
    UNRANKED = "<:Unranked:1037033299610185879>"
    
    BRONZE_LEAGUE_III = "<:BronzeLeagueIII:1037033267519557632>"
    BRONZE_LEAGUE_II = "<:BronzeLeagueII:1037033266483576842>"
    BRONZE_LEAGUE_I = "<:BronzeLeagueI:1037033265309155408>"
    SILVER_LEAGUE_III = "<:SilverLeagueIII:1037033271713865818>"
    SILVER_LEAGUE_II = "<:SilverLeagueII:1037033270048723065>"
    SILVER_LEAGUE_I = "<:SilverLeagueI:1037033268471664830>"
    GOLD_LEAGUE_III = "<:GoldLeagueIII:1037033275711029328>"
    GOLD_LEAGUE_II = "<:GoldLeagueII:1037033274146570360>"
    GOLD_LEAGUE_I = "<:GoldLeagueI:1037033273047650404>"
    CRYSTAL_LEAGUE_III = "<:CrystalLeagueIII:1037033283520831509>"
    CRYSTAL_LEAGUE_II = "<:CrystalLeagueII:1037033280643543131>"
    CRYSTAL_LEAGUE_I = "<:CrystalLeagueI:1037033278970011658>"
    MASTER_LEAGUE_III = "<:MasterLeagueIII:1037033287970992158>"
    MASTER_LEAGUE_II = "<:MasterLeagueII:1037033286482014339>"
    MASTER_LEAGUE_I = "<:MasterLeagueI:1037033285290827816>"
    CHAMPION_LEAGUE_III = "<:ChampionLeagueIII:1037033292169478334>"
    CHAMPION_LEAGUE_II = "<:ChampionLeagueII:1037033291032821760>"
    CHAMPION_LEAGUE_I = "<:ChampionLeagueI:1037033289564815430>"
    TITAN_LEAGUE_III = "<:TitanLeagueIII:1037033296720297995>"
    TITAN_LEAGUE_II = "<:TitanLeagueII:1037033295130656808>"
    TITAN_LEAGUE_I = "<:TitanLeagueI:1037033293423587398>"
    LEGEND_LEAGUE = "<:LegendLeague:1037033298460954704>"

    # WOOD_LEAGUE_V
    # WOOD_LEAGUE_IV
    # WOOD_LEAGUE_III
    # WOOD_LEAGUE_II
    # WOOD_LEAGUE_I
    # CLAY_LEAGUE_V
    # CLAY_LEAGUE_IV
    # CLAY_LEAGUE_III
    # CLAY_LEAGUE_II
    # CLAY_LEAGUE_I

    # STONE_LEAGUE_V
    # STONE_LEAGUE_IV
    # STONE_LEAGUE_III
    # STONE_LEAGUE_II
    # STONE_LEAGUE_I

    # COPPER_LEAGUE_V
    # COPPER_LEAGUE_IV
    # COPPER_LEAGUE_III
    # COPPER_LEAGUE_II
    # COPPER_LEAGUE_I

    # BRASS_LEAGUE_III
    # BRASS_LEAGUE_II
    # BRASS_LEAGUE_I

    # IRON_LEAGUE_III
    # IRON_LEAGUE_II
    # IRON_LEAGUE_I

    # STEEL_LEAGUE_III
    # STEEL_LEAGUE_II
    # STEEL_LEAGUE_I

    # TITANIUM_LEAGUE_III
    # TITANIUM_LEAGUE_II
    # TITANIUM_LEAGUE_I

    # PLATINUM_LEAGUE_III
    # PLATINUM_LEAGUE_II
    # PLATINUM_LEAGUE_I

    # EMERALD_LEAGUE_III
    # EMERALD_LEAGUE_II
    # EMERALD_LEAGUE_I

    # RUBY_LEAGUE_III
    # RUBY_LEAGUE_II
    # RUBY_LEAGUE_I

    # DIAMOND_LEAGUE

    @classmethod
    def get(cls, league:str):
        return getattr(cls, league.replace(" ","_").upper(), cls.UNRANKED)

class EmojisHeroes:
    BARBARIAN_KING = "<:BarbarianKing:1037000154173157397>"
    ARCHER_QUEEN = "<:ArcherQueen:1037000155561472096>"
    GRAND_WARDEN = "<:GrandWarden:1037000157088206939>"
    ROYAL_CHAMPION = "<:RoyalChampion:1037000158895943680>"
    BATTLE_MACHINE = "<:BattleMachine:1037002790305792072>"
    BATTLE_COPTER = "<:Battle_Copter:1108492706277232650>"

    @classmethod
    def get(cls, hero:str):
        return getattr(cls, hero.replace(" ","_").upper(), '')

class EmojisEquipment:
    GIANT_GAUNTLET = "<:giant_gauntlet:1187485991678791730>"
    RAGE_GEM = "<:rage_gem:1187485928600637452>"
    ARCHER_PUPPET = "<:archer_puppet:1187485921252229291>"
    BARBARIAN_PUPPET = "<:barbarian_puppet:1187485912041525268>"
    EARTHQUAKE_BOOTS = "<:earthquake_boots:1187485878105415720>"
    ETERNAL_TOME = "<:eternal_tome:1187485867099557999>"
    HEALER_PUPPET = "<:healer_puppet:1187485857792409682>"
    HEALING_TOME = "<:healing_tome:1187485849043087390>"
    RAGE_VIAL = "<:rage_vial:1187485844412563506>"
    LIFE_GEM = "<:life_gem:1187485836242071653>"
    GIANT_ARROW = "<:giant_arrow:1187485830604914798>"
    ROYAL_GEM = "<:royal_gem:1187485826855206943>"
    INVISIBILITY_VIAL = "<:invisibility_vial:1187485821557821450>"
    SEEKING_SHIELD = "<:seeking_shield:1187485811088818277>"
    VAMPSTACHE = "<:vampstache:1187485806437347378>"

    @classmethod
    def get(cls, equipment:str):
        return getattr(cls, equipment.replace(" ","_").upper(), '')


class EmojisPets:
    LASSI = "<:LASSI:1037000160246509639>"
    ELECTRO_OWL = "<:ElectroOwl:1043100246491811942>"
    MIGHTY_YAK = "<:MightyYak:1043100233934045184>"
    UNICORN = "<:Unicorn:1043100264296615937>"
    FROSTY = "<:Frosty:1037000165229350973>"
    DIGGY = "<:Diggy:1037000169360732220>"
    POISON_LIZARD = "<:PoisonLizard:1037000167221629048>"
    PHOENIX = "<:Phoenix:1037000168035340360>"
    SPIRIT_FOX = "<:spirit_fox:1182701308323565568>"

    @classmethod
    def get(cls, pet:str):
        return getattr(cls, pet.replace(" ","_").replace(".","").upper(), '')
    
class EmojisTroops:
    BARBARIAN = "<:Barbarian:1036998335791382588>"
    ARCHER = "<:Archer:1036998337343275028>"
    GIANT = "<:Giant:1036998341160087652>"
    GOBLIN = "<:Goblin:1036998338089852970>"
    WALL_BREAKER = "<:WallBreaker:1036998339629154367>"
    BALLOON = "<:Balloon:1036998342376427610>"
    WIZARD = "<:Wizard:1036998343789916200>"
    HEALER = "<:Healer:1036998345106919424>"
    DRAGON = "<:Dragon:1036998346323275826>"
    MINION = "<:Minion:1036998347589959810>"
    HOG_RIDER = "<:HogRider:1036998348852441098>"
    PEKKA = "<:PEKKA:1036998349917802556>"
    VALKYRIE = "<:Valkyrie:1036998351268360192>"
    GOLEM = "<:Golem:1036998352505671820>"
    BABY_DRAGON = "<:BabyDragon:1036998353759785101>"
    WITCH = "<:Witch:1036998354921603202>"
    LAVA_HOUND = "<:LavaHound:1036998356125351976>"
    MINER = "<:Miner:1036998357127798794>"
    BOWLER = "<:Bowler:1036998358604193852>"
    ELECTRO_DRAGON = "<:ElectroDragon:1036998359690522665>"
    ICE_GOLEM = "<:IceGolem:1036998361036890183>"
    YETI = "<:Yeti:1036998362454560768>"
    HEADHUNTER = "<:Headhunter:1036998363817717851>"
    DRAGON_RIDER = "<:DragonRider:1043099676615909387>"
    ELECTRO_TITAN = "<:ElectroTitan:1036998366237818890>"
    APPRENTICE_WARDEN = "<:apprentice_warden:1117805712614096968>"
    ROOT_RIDER = "<:root_rider:1183054320531427360>"

    #Super Troops
    SUPER_BARBARIAN = "<:SuperBarbarian:1037032254116995103>"
    SUPER_ARCHER = "<:SuperArcher:1043101392090431521>"
    SUPER_GIANT = "<:SuperGiant:1037032258080608287>"
    SNEAKY_GOBLIN = "<:SneakyGoblin:1037032259888365668>"
    SUPER_WALL_BREAKER = "<:SuperWallBreaker:1043101411417796639>"
    ROCKET_BALLOON = "<:RocketBalloon:1043101388776935524>"
    SUPER_WIZARD = "<:superwizard:1037032265479360542>"
    SUPER_DRAGON = "<:SuperDragon:1043101400869122048>"
    INFERNO_DRAGON = "<:InfernoDragon:1037032268159528980>"
    SUPER_MINION = "<:SuperMinion:1043101404958572595>"
    SUPER_VALKYRIE = "<:SuperValkyrie:1043101408070733894>"
    SUPER_WITCH = "<:SuperWitch:1037032273909915648>"
    ICE_HOUND = "<:IceHound:1043101384284848199>"
    SUPER_BOWLER = "<:SuperBowler:1043101396196671538>"
    SUPER_MINER = "<:super_miner:1117001013283541074>"
    SUPER_HOG_RIDER = "<:super_hog_rider:1117863727346225222>"

    #Siege Machines
    WALL_WRECKER = "<:WallWrecker:1036998801237475378>"
    BATTLE_BLIMP = "<:BattleBlimp:1036998802013442100>"
    STONE_SLAMMER = "<:StoneSlammer:1036998803380764712>"
    SIEGE_BARRACKS = "<:SiegeBarracks:1036998804592939108>"
    LOG_LAUNCHER = "<:LogLauncher:1036998805775728660>"
    FLAME_FLINGER = "<:FlameFlinger:1036998807168237730>"
    BATTLE_DRILL = "<:BattleDrill:1036998808397160458>"
    
    @classmethod
    def get(cls, troop:str):
        return getattr(cls, troop.replace(" ","_").replace(".","").upper(), '')

class EmojisSpells:
    LIGHTNING_SPELL = "<:LightningSpell:1036999357255397497>"
    HEALING_SPELL = "<:HealingSpell:1036999358547230772>"
    RAGE_SPELL = "<:RageSpell:1036999360417898707>"
    POISON_SPELL = "<:PoisonSpell:1036999361734901780>"
    EARTHQUAKE_SPELL = "<:EarthquakeSpell:1036999363022565406>"
    JUMP_SPELL = "<:JumpSpell:1036999364356349982>"
    FREEZE_SPELL = "<:FreezeSpell:1036999366055047258>"
    HASTE_SPELL = "<:HasteSpell:1036999367304941610>"
    SKELETON_SPELL = "<:SkeletonSpell:1036999368852647956>"
    CLONE_SPELL = "<:CloneSpell:1036999369863475210>"
    BAT_SPELL = "<:BatSpell:1036999371008516237>"
    INVISIBILITY_SPELL = "<:InvisibilitySpell:1036999371985784885>"
    RECALL_SPELL = "<:recall:1036999373529296976>"
    
    @classmethod
    def get(cls, spell:str):
        return getattr(cls, spell.replace(" ","_").replace(".","").upper(), '')