import discord
import pendulum
import re

from typing import *
from collections import Counter

from redbot.core import commands, app_commands
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter

from coc_main.api_client import BotClashClient, aClashSeason, ClashOfClansError, InvalidAbbreviation, InvalidRole
from coc_main.cog_coc_client import ClashOfClansClient, aClan

from coc_main.utils.components import clash_embed, MenuConfirmation, ClanLinkMenu
from coc_main.utils.utils import chunks
from coc_main.utils.autocomplete import autocomplete_clans, autocomplete_clans_coleader, autocomplete_seasons
from coc_main.utils.checks import is_admin, is_coleader, is_admin_or_leader, is_admin_or_coleader

from coc_main.utils.constants.coc_emojis import EmojisTownHall
from coc_main.utils.constants.ui_emojis import EmojisUI

from coc_main.exceptions import ClashAPIError, InvalidTag

from coc_main.discord.clan_link import ClanGuildLink

from .views.clan_settings import ClanSettingsMenu
from .views.clan_members import ClanMembersMenu
from .excel.clan_export import ClanExcelExport

from coc_main.discord.feeds.raid_results import RaidResultsFeed

bot_client = BotClashClient()

async def autocomplete_clan_settings(interaction:discord.Interaction,current:str):
    try:
        member = interaction.guild.get_member(interaction.user.id)
        if interaction.user.id in interaction.client.owner_ids or member.guild_permissions.administrator:
            return await autocomplete_clans(interaction,current)       
        else:
            return await autocomplete_clans_coleader(interaction,current)
        
    except Exception:
        bot_client.coc_main_log.exception("Error in autocomplete_clan_settings")

############################################################
############################################################
#####
##### CLIENT COG
#####
############################################################
############################################################
class Clans(commands.Cog):
    """
    Clan Commands
    """

    __author__ = bot_client.author
    __version__ = bot_client.version

    def __init__(self,bot:Red,version:int):
        self.bot = bot
        self.sub_v = version

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}.{self.sub_v}"
    
    @property
    def bot_client(self) -> BotClashClient:
        return BotClashClient()

    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    async def cog_command_error(self,ctx,error):
        if isinstance(getattr(error,'original',None),ClashOfClansError):
            embed = await clash_embed(
                context=ctx,
                message=f"{error.original.message}",
                success=False,
                timestamp=pendulum.now()
                )
            await ctx.send(embed=embed)
            return
        await self.bot.on_command_error(ctx,error,unhandled_by_cog=True)

    async def cog_app_command_error(self,interaction,error):
        if isinstance(getattr(error,'original',None),ClashOfClansError):
            embed = await clash_embed(
                context=interaction,
                message=f"{error.original.message}",
                success=False,
                timestamp=pendulum.now()
                )
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed,view=None)
            else:
                await interaction.response.send_message(embed=embed,view=None,ephemeral=True)
            return
    
    @commands.Cog.listener()
    async def on_assistant_cog_add(self,cog:commands.Cog):
        schemas = [
            {
                "name": "_assistant_get_clan_named",
                "description": "Searches the database for Clans by a given name or abbreviation string. Returns a list of matches.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "clan_name_or_abbreviation": {
                            "description": "Clan Name or Abbreviation. Not caps sensitive.",
                            "type": "string",
                            },
                        },
                    "required": ["clan_name_or_abbreviation"],
                    },
                },
            {
                "name": "_assistant_get_clan_information",
                "description": "Returns complete information about a Clan. An identifying Clan Tag must be provided as this only returns one clan.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "clan_tag": {
                            "description": "The Clan Tag to search for.",
                            "type": "string",
                            },
                        },
                    "required": ["clan_tag"],
                    },
                },
            ]
        await cog.register_functions(cog_name="Clans", schemas=schemas)
    
    async def _assistant_get_clan_named(self,clan_name_or_abbreviation:str,*args,**kwargs) -> str:
        q_doc = {
            '$or':[
                {'name':{'$regex':f'^{clan_name_or_abbreviation}',"$options":"i"}},
                {'abbreviation':{'$regex':f'^{clan_name_or_abbreviation}',"$options":"i"}}
                ]
            }
        pipeline = [
            {'$match': q_doc},
            {'$sample': {'size': 8}}
            ]
        query = bot_client.coc_db.db__clan.aggregate(pipeline)

        clan_tags = [c['_id'] async for c in query]
        clans = await self.client.fetch_many_clans(*clan_tags)

        ret_clans = [c.assistant_name_json() for c in clans]
        return f"Found {len(ret_clans)} Clans matching `{clan_name_or_abbreviation}`. Clans: {ret_clans}"

    async def _assistant_get_clan_information(self,clan_tag:str,*args,**kwargs) -> str:
        try:
            clan = await self.client.fetch_clan(clan_tag)
        except ClashAPIError:
            return "The API Service isn't available right now."
        except InvalidTag:
            return f"The tag {clan_tag} appears to be invalid."
        
        ret_clan = clan.assistant_clan_information()
        return f"Found Clan: {ret_clan}"
    
    ##################################################
    ### CLAN ABBREVIATION LISTENER
    ##################################################
    @commands.Cog.listener("on_message")
    async def clan_abbreviation_listener(self,message:discord.Message):

        found_clans = []
        chk = True

        if not message.guild:
            return        
        if message.author.bot:
            return
        
        valid_prefixes = await self.bot.get_valid_prefixes(guild=message.guild)
        if not message.content.startswith(tuple(valid_prefixes)):
            return
        
        content_text = message.content[1:]

        for text in content_text.split():
            try:
                found_clans.append(await self.client.from_clan_abbreviation(text))
            except InvalidAbbreviation:
                chk = False
        
        if chk and len(found_clans) > 0:
            context = await self.bot.get_context(message)
            view = ClanLinkMenu(found_clans)
            embeds = []
            async for clan in AsyncIter(found_clans):
                embed = await clash_embed(
                    context=context,
                    title=f"{clan.title}",
                    message=f"{clan.long_description}"
                        + (f"\n\n> **Recruiting:** {clan.recruitment_level_emojis}" if clan.is_alliance_clan else "")
                        + f"\n\n{clan.description}",
                    thumbnail=clan.badge,
                    show_author=False,
                    )
                embeds.append(embed)
            return await message.reply(embeds=embeds,view=view)
    
    ############################################################
    ############################################################
    #####
    ##### COMMAND DIRECTORY
    ##### - Clan / Export
    ##### - Clan / Compo
    ##### - Clan / Strength
    ##### - Clan / Donations
    ##### - Clan / Members
    ##### - Clan / Info
    ##### - Clan-Games
    ##### - ClanData / War Log** [under construction]
    ##### - ClanData / Raid Log** [under construction]
    ##### - ClanSet / Register
    ##### - ClanSet / Delete
    ##### - ClanSet / Link
    ##### - ClanSet / Unlink
    ##### - ClanSet / SetLeader
    ##### - ClanSet / Config    
    #####
    ############################################################
    ############################################################
    
    @commands.command(name="raidimg")
    @commands.is_owner()
    async def command_raidimg(self,ctx:commands.Context):
        clan = await self.client.from_clan_abbreviation("AS")
        raid = await self.client.get_raid_weekend(clan)

        img = await RaidResultsFeed.get_results_image(clan,raid)
        file = discord.File(img,filename="raid_weekend.png")
        await ctx.send(file=file)

    ##################################################
    ### PARENT COMMAND GROUPS
    ##################################################
    @commands.group(name="clan")
    @commands.guild_only()
    async def command_group_clan(self,ctx):
        """
        Group for Clan-related commands.

        **This is a command group. To use the sub-commands below, follow the syntax: `$clan [sub-command]`.**
        """
        if not ctx.invoked_subcommand:
            pass

    app_command_group_clan = app_commands.Group(
        name="clan",
        description="Group for Clan Data. Equivalent to [p]clandata.",
        guild_only=True
        )
    
    @commands.group(name="clanset")
    @commands.guild_only()
    async def command_group_clanset(self,ctx):
        """
        Group for Clan Settings.

        **This is a command group. To use the sub-commands below, follow the syntax: `$clanset [sub-command]`.**
        """
        if not ctx.invoked_subcommand:
            pass

    app_command_group_clanset = app_commands.Group(
        name="clan-set",
        description="Group for Clan Settings. Equivalent to [p]clanset.",
        guild_only=True
        )
    
    ##################################################
    ### CLAN FAMILY
    ##################################################
    async def helper_family_clans(self,context:Union[commands.Context,discord.Interaction]):
        clans = await self.client.get_registered_clans()
        a_iter = AsyncIter(clans)
        embed = await clash_embed(
            context=context,
            title=f"**{bot_client.bot.user.name} Registered Clans**",
            message='\n'.join([f"{clan.emoji} {clan.abbreviation} {clan.clean_name} ({clan.tag})" async for clan in a_iter]),
            )
        return embed

    @commands.command(name="familyclans")
    @commands.guild_only()
    async def command_family_clans(self,ctx:commands.Context):
        """
        Displays all Clans registered to the bot.
        """
        embed = await self.helper_family_clans(ctx)
        await ctx.reply(embed=embed)
        
    @app_commands.command(
        name="family-clans",
        description="Displays all Clans registered to the bot.")
    @app_commands.guild_only()
    async def app_command_family_clans(self,interaction:discord.Interaction):

        await interaction.response.defer()
        embed = await self.helper_family_clans(interaction)
        await interaction.followup.send(embed=embed)

    ##################################################
    ### FIND-CLAN (ALIAS: CLAN INFO)
    ##################################################
    async def helper_find_clan(self,context:Union[commands.Context,discord.Interaction],clan_tag:str) -> Tuple[discord.Embed,Optional[ClanLinkMenu]]:        
        clan = await self.client.fetch_clan(tag=clan_tag)
        if not clan:
            embed = await clash_embed(
            context=context,
            message=f"I couldn't find a Clan with the tag `{clan_tag}`.",
            )
            return embed,None

        view = ClanLinkMenu([clan])

        embed = await clash_embed(
            context=context,
            title=f"{clan.title}",
            message=f"{clan.long_description}"
                + (f"\n\n> **Recruiting:** {clan.recruitment_level_emojis}" if clan.is_alliance_clan else "")
                + f"\n\n{clan.description}",
            thumbnail=clan.badge,
            show_author=False,
            )
        return embed,view
    
    @commands.command(name="findclan")
    @commands.guild_only()
    async def command_find_clan(self,ctx:commands.Context,clan_tag:str):
        """
        Gets information about an in-game Clan.

        This command accepts an in-game Clash Tag. To use Alliance abbreviations, simply use `[p]abbreviation` instead.
        """

        embed, view = await self.helper_find_clan(ctx,clan_tag)
        await ctx.reply(embed=embed,view=view)
        
    @app_commands.command(
        name="find-clan",
        description="Get information about a Clan.")
    @app_commands.guild_only()
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan or manually enter a Tag.")
    async def app_command_find_clan(self,interaction:discord.Interaction,clan:str):

        await interaction.response.defer()
        embed, view = await self.helper_find_clan(interaction,clan)
        await interaction.followup.send(embed=embed,view=view)
    
    @command_group_clan.command(name="info")
    @commands.guild_only()
    async def command_get_clan_information(self,ctx:commands.Context,clan_tag:str):
        """
        Gets information about an in-game Clan.

        This command accepts an in-game Clash Tag. To use Alliance abbreviations, simply use `[p]abbreviation` instead.
        """

        embed, view = await self.helper_find_clan(ctx,clan_tag)
        await ctx.reply(embed=embed,view=view)
        
    @app_command_group_clan.command(
        name="info",
        description="Get information about a Clan.")
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan or manually enter a Tag.")
    async def app_command_clan_information(self,interaction:discord.Interaction,clan:str):

        await interaction.response.defer()
        embed, view = await self.helper_find_clan(interaction,clan)
        await interaction.followup.send(embed=embed,view=view)
    
    ##################################################
    ### CLANDATA / EXPORT
    ##################################################
    async def _clan_export_helper(self,
        context:Union[commands.Context,discord.Interaction],
        clan_tag_or_abbreviation:str,
        season:Optional[aClashSeason]=None):

        try:
            clan = await self.client.from_clan_abbreviation(clan_tag_or_abbreviation)
        except InvalidAbbreviation:
            clan = await self.client.fetch_clan(clan_tag_or_abbreviation)
        
        if not clan:
            embed = await clash_embed(
                context=context,
                message=f"I couldn't find a Clan with the input `{clan_tag_or_abbreviation}`.",
                success=False,
                )
            return embed, None

        if not clan.is_alliance_clan:
            embed = await clash_embed(
                context=context,
                message=f"Only Alliance Clans can be exported.",
                success=False,
                )
            return embed, None
        
        if not season:
            season = self.bot_client.current_season
        rp_file = await ClanExcelExport.generate_report(clan,season)
        discord_file = discord.File(rp_file)

        message = f"Here is your Data for **{clan}**.\n\nSeason: {season.description}."
        return message,discord_file

    @command_group_clan.command(name="export")
    @commands.guild_only()
    @commands.check(is_coleader)
    async def command_export_clan_data(self,ctx:commands.Context,clan_tag_or_abbreviation:str):
        """
        Exports a Clan's data to Excel.

        Only usable for Alliance clans. Defaults to current season. To export for different seasons, use the Slash command.
        """

        embed = await clash_embed(
            context=ctx,
            message=f"{EmojisUI.LOADING} Exporting data... please wait.",
            timestamp=pendulum.now(),
            )
        message = await ctx.reply(embed=embed)

        embed, discord_file = await self._clan_export_helper(ctx,clan_tag_or_abbreviation)
        attachments = [discord_file] if discord_file else []

        await message.edit(
            content=f'{ctx.author.mention} {embed}',
            embed=None,
            attachments=attachments
            )

    @app_command_group_clan.command(name="export",
        description="Export seasonal Clan Data to an Excel file.")
    @app_commands.check(is_coleader)
    @app_commands.autocomplete(
        clan=autocomplete_clans_coleader,
        season=autocomplete_seasons)
    @app_commands.describe(
        clan="Select a Clan. Only Alliance Clans can be selected.",
        season="Select a Season to export.")
    async def app_command_clan_export(self,interaction:discord.Interaction,clan:str,season:str):  
        
        await interaction.response.defer()

        get_season = await aClashSeason(season)

        embed, discord_file = await self._clan_export_helper(interaction,clan,get_season)
        attachments = [discord_file] if discord_file else []

        await interaction.edit_original_response(
            content=f'{interaction.user.mention} {embed}',
            embed=None,
            attachments=attachments
            )
    
    ##################################################
    ### CLANDATA / COMPO
    ##################################################
    async def _clan_composition_helper(self,
        context:Union[commands.Context,discord.Interaction],
        clan_tag_or_abbreviation:str) -> discord.Embed:

        try:
            clan = await self.client.from_clan_abbreviation(clan_tag_or_abbreviation)
        except InvalidAbbreviation:
            clan = await self.client.fetch_clan(clan_tag_or_abbreviation)
        
        if not clan:
            embed = await clash_embed(
                context=context,
                message=f"I couldn't find a Clan with the input `{clan_tag_or_abbreviation}`.",
                success=False,
                )
            return embed

        embed = await clash_embed(
            context=context,
            title=f"{clan.title}",
            message=f"**Clan Member Composition**",
            thumbnail=clan.badge,
            )
                   
        ingame_members = await self.client.fetch_many_players(*[member.tag for member in clan.members])

        if clan.is_alliance_clan and clan.alliance_member_count > 0:
            clan_members = await self.client.fetch_many_players(*clan.alliance_members)
            townhall_levels = [member.town_hall.level for member in clan_members]
            townhall_levels.sort(reverse=True)

            average_townhall = round(sum(townhall_levels)/len(townhall_levels),2)
            townhall_counts = Counter(townhall_levels)
            
            embed.add_field(
                name="**Registered Members**",
                value=f"Total: {len(clan_members)} {EmojisUI.MEMBERS}\n"
                    + f"Average: {EmojisTownHall.get(int(average_townhall))} {average_townhall}\n\n"
                    + "\n".join([
                        f"{EmojisTownHall.get(th)} `TH{th:02}`: {(count/len(clan_members))*100:.1f}% ({count})"
                        for th, count in townhall_counts.items()
                        ])
                    + "\n\u200b",
                inline=False,
                )
            
        townhall_levels = [member.town_hall.level for member in ingame_members]
        townhall_levels.sort(reverse=True)
        average_townhall = round(sum(townhall_levels)/len(townhall_levels),2)
        townhall_counts = Counter(townhall_levels)

        embed.add_field(
            name="**In-Game Members**",
            value=f"Total: {len(ingame_members)} {EmojisUI.MEMBERS}\n"
                + f"Average: {EmojisTownHall.get(int(average_townhall))} {average_townhall}\n\n"
                + "\n".join([
                    f"{EmojisTownHall.get(th)} `TH{th:02}`: {(count/len(ingame_members))*100:.1f}% ({count})"
                    for th, count in townhall_counts.items()
                    ])
                + "\n\u200b",
            inline=False,
            )
        return embed

    @command_group_clan.command(name="compo")
    @commands.guild_only()
    async def command_clan_composition(self,ctx:commands.Context,clan_tag_or_abbreviation:str):
        """
        View a Clan's Town Hall composition.

        For registered Alliance clans, returns registered and in-game compositions.
        """

        embed = await self._clan_composition_helper(ctx,clan_tag_or_abbreviation)
        await ctx.reply(embed=embed)

    @app_command_group_clan.command(
        name="compo",
        description="View a Clan's Townhall composition.")
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan.")
    async def app_command_clan_composition(self,interaction:discord.Interaction,clan:str):

        await interaction.response.defer()
        embed = await self._clan_composition_helper(interaction,clan)
        await interaction.followup.send(embed=embed)

    ##################################################
    ### CLANDATA / STRENGTH
    ##################################################
    async def _clan_strength_helper(self,
        context:Union[commands.Context,discord.Interaction],
        clan_tag_or_abbreviation:str) -> discord.Embed:

        try:
            clan = await self.client.from_clan_abbreviation(clan_tag_or_abbreviation)
        except InvalidAbbreviation:
            clan = await self.client.fetch_clan(clan_tag_or_abbreviation)
        
        if not clan:
            embed = await clash_embed(
                context=context,
                message=f"I couldn't find a Clan with the input `{clan_tag_or_abbreviation}`.",
                success=False,
                )
            return embed
        
        if clan.is_alliance_clan and clan.alliance_member_count > 0:
            showing_registered = True
            clan_members = await self.client.fetch_many_players(*clan.alliance_members)
        else:
            showing_registered = False
            clan_members = await self.client.fetch_many_players(*[member.tag for member in clan.members])
        
        townhall_levels = list(set([member.town_hall.level for member in clan_members]))
        townhall_levels.sort(reverse=True)
        average_th = round(sum([member.town_hall.level for member in clan_members])/len([member.town_hall.level for member in clan_members]),2)

        embed = await clash_embed(
            context=context,
            title=f"{clan.title}",
            message=f"**Clan Offensive Strength**\n"
                + f"**Average TH: {EmojisTownHall.get(round(average_th))} {average_th}**\n\n"
                + (f"*Showing registered members only.*\n" if showing_registered else "*Showing in-game members only.*\n")
                + (f"The {EmojisUI.LOGOUT} emoji denotes a registered member who is currently not in the clan.\n" if clan.is_alliance_clan and clan.alliance_member_count > 0 else "")
                + f"\n`{'BK':^2}{'':^2}{'AQ':^2}{'':^2}{'GW':^2}{'':^2}{'RC':^2}{'':^2}{'Troops':>7}{'':^2}{'Spells':>7}{'':^2}`",
            thumbnail=clan.badge,
            )

        async for th in AsyncIter(townhall_levels):
            th_members = [member for member in clan_members if member.town_hall.level == th]
            th_members.sort(key=lambda member:(member.hero_strength,member.troop_strength,member.spell_strength),reverse=True)
            
            chunked_members = [c async for c in chunks(th_members,10)]
            a_iter = AsyncIter(chunked_members)

            async for i, members_chunk in a_iter.enumerate():
                embed.add_field(
                    name=f"{EmojisTownHall.get(th)} **TH{th}**"
                        + (f" - ({i+1}/{len(chunked_members)})" if len(chunked_members) > 1 else ""),
                    value="\n".join([
                        f"`"
                        + f"{getattr(member.barbarian_king,'level',''):^2}{'':^2}"
                        + f"{getattr(member.archer_queen,'level',''):^2}{'':^2}"
                        + f"{getattr(member.grand_warden,'level',''):^2}{'':^2}"
                        + f"{getattr(member.royal_champion,'level',''):^2}{'':^2}"
                        + f"{str(round(member.troop_strength_pct))+'%':>7}{'':^2}"
                        + f"{str(round(member.spell_strength_pct))+'%':>7}{'':^2}"
                        + "`"
                        + f"\u3000{re.sub('[_*/]','',member.clean_name)}"
                        + (f" {EmojisUI.LOGOUT}" if clan.is_alliance_clan and member.tag not in clan.members_dict else "")
                        for member in members_chunk
                        ]),
                    inline=False,
                    )
        return embed

    @command_group_clan.command(name="strength")
    @commands.guild_only()
    async def subcommand_clan_strength(self,ctx:commands.Context,clan_tag_or_abbreviation:str):
        """
        View a Clan's overall Offensive Strength.

        For registered Alliance clans, returns only registered members.
        """
        
        embed = await self._clan_strength_helper(ctx,clan_tag_or_abbreviation)
        await ctx.reply(embed=embed)
    
    @app_command_group_clan.command(
        name="strength",
        description="View a Clan's Offensive strength.")
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan.")
    async def app_command_clan_strength(self,interaction:discord.Interaction,clan:str):

        await interaction.response.defer()
        embed = await self._clan_strength_helper(interaction,clan)
        await interaction.followup.send(embed=embed)
    
    ##################################################
    ### CLAN / MEMBERS
    ##################################################
    @command_group_clan.command(name="members")
    @commands.guild_only()
    async def subcommand_clan_membersummary(self,ctx:commands.Context,clan_tag_or_abbreviation:str):
        """
        Display info on a Clan's Members.

        Contains menus for Discord Links, Rank Status, and War Opt-Ins.

        By default, this shows all in-game members. For Alliance Clans, this will also return registered members who are not in the in-game clan.
        """
  
        try:
            clan = await self.client.from_clan_abbreviation(clan_tag_or_abbreviation)
        except InvalidAbbreviation:
            clan = await self.client.fetch_clan(clan_tag_or_abbreviation)

        if not clan:
            embed = await clash_embed(
                context=ctx,
                message=f"I couldn't find a Clan with the input `{clan_tag_or_abbreviation}`.",
                success=False,
                )
            return await ctx.reply(embed=embed)
        
        menu = ClanMembersMenu(ctx,clan)
        await menu.start()

    @app_command_group_clan.command(name="members",
        description="View Clan Member information.")
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(
        clan="Select a Clan.") 
    async def app_command_clan_membersummary(self,interaction:discord.Interaction,clan:str):

        await interaction.response.defer()

        get_clan = await self.client.fetch_clan(clan)
        if not clan:
            embed = await clash_embed(
                context=interaction,
                message=f"I couldn't find a Clan with the input `{clan}`.",
                success=False,
                )
            return await interaction.edit_original_response(embed=embed)

        menu = ClanMembersMenu(interaction,get_clan)
        await menu.start()
    
    ##################################################
    ### CLANSET / REGISTER
    ##################################################
    async def helper_register_clan(self,
        context:Union[commands.Context,discord.Interaction],
        clan_tag:str,
        emoji:str,
        unicode_emoji:str,
        abbreviation:str):

        clan = await self.client.fetch_clan(clan_tag)
        await clan.register(abbreviation=abbreviation,emoji=emoji,unicode_emoji=unicode_emoji)
        embed = await clash_embed(
            context=context,
            title=f"Registered: {clan.title}",
            message=clan.long_description,
            thumbnail=clan.badge,
            success=True
            )
        return embed

    @command_group_clanset.command(name="register")
    @commands.guild_only()
    @commands.admin()
    async def subcommand_register_clan(self,ctx:commands.Context,clan_tag:str,emoji:str,unicode_emoji:str,abbreviation:str):
        """
        [Admin-only] Register an in-game Clan to the bot.

        Assigns:
        > - Clan Emoji
        > - Clan Abbreviation
        """
        
        embed = await self.helper_register_clan(ctx,clan_tag,emoji,unicode_emoji,abbreviation)
        await ctx.reply(embed=embed)
    
    @app_command_group_clanset.command(
        name="register",
        description="[Admin-only] Register an in-game Clan to the bot.")
    @app_commands.check(is_admin)
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(
        clan="Select a Clan, or enter a Clan Tag.",
        emoji="Provide the Emoji to use for the Clan.",
        unicode_emoji="Provide the Unicode Emoji to use for the Clan.",
        abbreviation="Provide the Clan's abbreviation.")
    async def app_subcommand_register_clan(self,interaction:discord.Interaction,
        clan:str,
        emoji:str,
        unicode_emoji:str,
        abbreviation:str):
        
        await interaction.response.defer()
        embed = await self.helper_register_clan(interaction,clan,emoji,unicode_emoji,abbreviation)
        await interaction.followup.send(embed=embed)
    
    ##################################################
    ### CLANSET / LINK
    ##################################################
    @command_group_clanset.command(name="link")
    @commands.guild_only()
    @commands.admin()
    async def subcommand_link_clan(self,ctx:commands.Context,clan_tag:str,coleader_role_id:int,elder_role_id:int,member_role_id:int):
        """
        [Admin-only] Links a Clan to this Discord Server.

        Linked Clans have linked Discord Roles, and will be synced based on membership status.
        > - Co-Leader Role
        > - Elder Role
        > - Member Role

        This command requires you to provide Co-Leader, Elder, and Member roles. To add a Visitor or Clan War Role, use the Slash command.
        """
        
        clan = await self.client.fetch_clan(clan_tag)

        coleader_role = ctx.guild.get_role(coleader_role_id)
        if not coleader_role:
            raise InvalidRole(f"Co-Leader Role ID `{coleader_role_id}` is not valid.")
        
        elder_role = ctx.guild.get_role(elder_role_id)
        if not elder_role:
            raise InvalidRole(f"Elder Role ID `{elder_role_id}` is not valid.")
        
        member_role = ctx.guild.get_role(member_role_id)
        if not member_role:
            raise InvalidRole(f"Member Role ID `{member_role_id}` is not valid.")
        
        embed = await clash_embed(
            context=ctx,
            title=f"Link Clan: **{clan.title}**",
            message=f"**Co-Leader Role:** {coleader_role.mention}"
                + f"\n**Elder Role:** {elder_role.mention}"
                + f"\n**Member Role:** {member_role.mention}",
            thumbnail=clan.badge)
        confirm_view = MenuConfirmation(ctx)
        
        message = await ctx.reply(
            content=f"{ctx.author.mention}, please confirm the below action.",
            embed=embed,
            view=confirm_view
            )        
        view_timed_out = await confirm_view.wait()

        if view_timed_out:
            timeout_embed = await clash_embed(
                context=ctx,
                message=f"Confirmation timed out. Please try again.",
                success=False)
            return await message.edit(content=None,embed=[embed,timeout_embed],view=None)
    
        if not confirm_view.confirmation:
            cancel_embed = await clash_embed(
                context=ctx,
                message=f"Task cancelled.",
                success=False)
            return await message.edit(content=None,embed=[embed,cancel_embed],view=None)

        if confirm_view.confirmation:
            await clan._sync_cache()

            await ClanGuildLink.link_member_role(clan_tag=clan.tag,guild=ctx.guild,member_role=member_role)
            await ClanGuildLink.link_elder_role(clan_tag=clan.tag,guild=ctx.guild,elder_role=elder_role)
            await ClanGuildLink.link_coleader_role(clan_tag=clan.tag,guild=ctx.guild,coleader_role=coleader_role)

            link = await ClanGuildLink.get_link(clan.tag,ctx.guild.id)
            complete_embed = await clash_embed(
                context=ctx,
                title=f"Clan Linked: **{clan.title}**",
                message=f"**Co-Leader Role:** {link.coleader_role.mention}"
                    + f"\n**Elder Role:** {link.elder_role.mention}"
                    + f"\n**Member Role:** {link.member_role.mention}",
                url=clan.share_link,
                success=True,
                thumbnail=clan.badge)
            return await message.edit(content=None,embed=complete_embed,view=None)

    @app_command_group_clanset.command(
        name="link",
        description="[Admin-only] Links a Clan to this Discord Server.")
    @app_commands.check(is_admin)
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(
        clan="Select a Clan.",
        coleader_role="The Role to assign to Co-Leaders and Leaders.",
        elder_role="The Role to assign to Elders and above.",
        member_role="The Role to assign to registered Members. Only applicable if this is a Guild Clan.",
        visitor_role="The Role to assign to all in-game members, if linked to a Discord user.",
        clan_war_role="The Role to assign to all in-game members who are participating in the current Clan War.")
    async def app_subcommand_link_clan(self,interaction:discord.Interaction,
        clan:str,
        coleader_role:Optional[discord.Role]=None,
        elder_role:Optional[discord.Role]=None,
        member_role:Optional[discord.Role]=None,
        visitor_role:Optional[discord.Role]=None,
        clan_war_role:Optional[discord.Role]=None):
        
        await interaction.response.defer()
        
        select_clan = await self.client.fetch_clan(clan)
        embed = await clash_embed(
            context=interaction,
            title=f"Link Clan: **{select_clan.title}**",
            message=(f"**Co-Leader Role:** {coleader_role.mention}\n" if coleader_role else "")
                + (f"**Elder Role:** {elder_role.mention}\n" if elder_role else "")
                + (f"**Member Role:** {member_role.mention}\n" if member_role else "")
                + (f"**Visitor Role:** {visitor_role.mention}\n" if visitor_role else "")
                + (f"**Clan War Role:** {clan_war_role.mention}" if clan_war_role else ""),
            thumbnail=select_clan.badge)
        confirm_view = MenuConfirmation(interaction)

        await interaction.followup.send(
            content=f"{interaction.user.mention}, please confirm the below action.",
            embed=embed,
            view=confirm_view,
            wait=True
            )
        view_timed_out = await confirm_view.wait()

        if view_timed_out:
            timeout_embed = await clash_embed(
                context=interaction,
                message=f"Confirmation timed out. Please try again.",
                success=False)
            return await interaction.edit_original_response(content=None,embeds=[embed,timeout_embed],view=None)
    
        if not confirm_view.confirmation:
            cancel_embed = await clash_embed(
                context=interaction,
                message=f"Task cancelled.",
                success=False)
            return await interaction.edit_original_response(content=None,embeds=[embed,cancel_embed],view=None)

        if confirm_view.confirmation:
            await select_clan._sync_cache()

            if member_role:
                await ClanGuildLink.link_member_role(clan_tag=select_clan.tag,guild=interaction.guild,member_role=member_role)
            if elder_role:
                await ClanGuildLink.link_elder_role(clan_tag=select_clan.tag,guild=interaction.guild,elder_role=elder_role) 
            if coleader_role:
                await ClanGuildLink.link_coleader_role(clan_tag=select_clan.tag,guild=interaction.guild,coleader_role=coleader_role)
            if visitor_role:
                await ClanGuildLink.link_visitor_role(clan_tag=select_clan.tag,guild=interaction.guild,visitor_role=visitor_role)
            if clan_war_role:
                await ClanGuildLink.link_clan_war_role(clan_tag=select_clan.tag,guild=interaction.guild,clan_war_role=clan_war_role)

            link = await ClanGuildLink.get_link(select_clan.tag,interaction.guild.id) 
            complete_embed = await clash_embed(
                context=interaction,
                title=f"Link Clan: **{select_clan.title}**",
                message=f"**Co-Leader Role:** {getattr(link.coleader_role,'mention','Not Linked')}"
                    + f"\n**Elder Role:** {getattr(link.elder_role,'mention','Not Linked')}"
                    + f"\n**Member Role:** {getattr(link.member_role,'mention','Not Linked')}"
                    + f"\n**Visitor Role:** {getattr(link.visitor_role,'mention','Not Linked')}"
                    + f"\n**Clan War Role:** {getattr(link.clan_war_role,'mention','Not Linked')}",
                url=select_clan.share_link,
                success=True,
                thumbnail=select_clan.badge)
            return await interaction.edit_original_response(content=None,embed=complete_embed,view=None)
    
    ##################################################
    ### CLANSET / UNLINK
    ##################################################
    @command_group_clanset.command(name="unlink")
    @commands.guild_only()
    @commands.admin()
    async def subcommand_unlink_clan(self,ctx:commands.Context,clan_tag:str):
        """
        [Admin-only] Unlinks a Clan from this Discord Server.
        """
        clan = await self.client.fetch_clan(clan_tag)
        link = await ClanGuildLink.get_link(clan.tag,ctx.guild.id)
        
        embed = await clash_embed(
            context=ctx,
            title=f"Unlink Clan: **{clan.title}**",
            message=f"**Co-Leader Role:** {link.coleader_role.mention}"
                + f"\n**Elder Role:** {link.elder_role.mention}"
                + f"\n**Member Role:** {link.member_role.mention}",
            thumbnail=clan.badge)
        confirm_view = MenuConfirmation(ctx)
        
        message = await ctx.reply(
            content=f"{ctx.author.mention}, please confirm the below action.",
            embed=embed,
            view=confirm_view
            )        
        view_timed_out = await confirm_view.wait()

        if view_timed_out:
            timeout_embed = await clash_embed(
                context=ctx,
                message=f"Confirmation timed out. Please try again.",
                success=False)
            return await message.edit(content=None,embed=[embed,timeout_embed],view=None)
    
        if not confirm_view.confirmation:
            cancel_embed = await clash_embed(
                context=ctx,
                message=f"Task cancelled.",
                success=False)
            return await message.edit(content=None,embed=[embed,cancel_embed],view=None)

        if confirm_view.confirmation:
            await ClanGuildLink.delete(clan.tag,ctx.guild)
            complete_embed = await clash_embed(
                context=ctx,
                message=f"**{clan.title}** has been unlinked from {ctx.guild.name}.",
                success=True,
                thumbnail=clan.badge)
            return await message.edit(content=None,embed=complete_embed,view=None)

    @app_command_group_clanset.command(
        name="unlink",
        description="[Admin-only] Unlinks a Clan from this Discord Server.")
    @app_commands.check(is_admin)
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan.")
    async def app_subcommand_unlink_clan(self,interaction:discord.Interaction,clan:str):
        
        await interaction.response.defer()
        
        select_clan = await self.client.fetch_clan(clan)
        link = await ClanGuildLink.get_link(select_clan.tag,interaction.guild.id)

        if not link:
            embed = await clash_embed(
                context=interaction,
                message=f"**{select_clan.title}** is not linked to {interaction.guild.name}.",
                success=False,
                thumbnail=select_clan.badge)
            return await interaction.edit_original_response(embed=embed,view=None)

        embed = await clash_embed(
            context=interaction,
            title=f"Link Clan: **{select_clan.title}**",
            message=f"**Co-Leader Role:** {link.coleader_role.mention}"
                + f"\n**Elder Role:** {link.elder_role.mention}"
                + f"\n**Member Role:** {link.member_role.mention}",
            thumbnail=select_clan.badge)
        confirm_view = MenuConfirmation(interaction)

        await interaction.followup.send(
            content=f"{interaction.user.mention}, please confirm the below action.",
            embed=embed,
            view=confirm_view,
            wait=True
            )
        view_timed_out = await confirm_view.wait()

        if view_timed_out:
            timeout_embed = await clash_embed(
                context=interaction,
                message=f"Confirmation timed out. Please try again.",
                success=False)
            return await interaction.edit_original_response(content=None,embeds=[embed,timeout_embed],view=None)
    
        if not confirm_view.confirmation:
            cancel_embed = await clash_embed(
                context=interaction,
                message=f"Task cancelled.",
                success=False)
            return await interaction.edit_original_response(content=None,embeds=[embed,cancel_embed],view=None)

        if confirm_view.confirmation:
            await ClanGuildLink.delete(select_clan.tag,interaction.guild)
            complete_embed = await clash_embed(
                context=interaction,
                message=f"**{select_clan.title}** has been unlinked from {interaction.guild.name}.",
                success=True,
                thumbnail=select_clan.badge)
            return await interaction.edit_original_response(content=None,embed=complete_embed,view=None)
    
    ##################################################
    ### CLANSET / SETLEADER
    ##################################################
    def check_change_leader(self,guild:discord.Guild,clan:aClan,user_id:int):
        if user_id in self.bot.owner_ids:
            return True
        if user_id == clan.leader:
            return True
        member = guild.get_member(user_id)
        if clan.leader == 0 and member.guild_permissions.administrator:
            return True
        return False
        
    @command_group_clanset.command(name="leader")
    @commands.guild_only()
    @commands.check(is_admin_or_leader)
    async def subcommand_change_clan_leader(self,ctx:commands.Context,clan_abbreviation:str,new_leader:discord.Member):
        """
        Change the Leader of a registered Clan.

        Only the current Leader, or a Server Admin can use this Command.
        """

        clan = await self.client.from_clan_abbreviation(clan_abbreviation)

        if not self.check_change_leader(ctx.guild,clan,ctx.author.id):
            embed = await clash_embed(
                context=ctx,
                message=f"You do not have permission to change the Leader of **{clan.title}**.",
                success=False,
                )
            return await ctx.reply(embed=embed)
        
        embed = await clash_embed(
            context=ctx,
            title=f"Change Leader: **{clan.title}**",
            message=f"**Current Leader:** <@{clan.leader}>"
                + f"\n**New Leader:** {new_leader.mention}"
                + f"\n\n{clan.long_description}"
                + f"\n\n>>> {clan.description}",
            thumbnail=clan.badge)
        confirm_view = MenuConfirmation(ctx)

        message = await ctx.reply(
            content=f"{ctx.author.mention}, please confirm the below action.",
            embed=embed,
            view=confirm_view
            )
        view_timed_out = await confirm_view.wait()

        if view_timed_out:
            timeout_embed = await clash_embed(
                context=ctx,
                message=f"Confirmation timed out. Please try again.",
                success=False)
            return await message.edit(content=None,embeds=[embed,timeout_embed],view=None)

        if not confirm_view.confirmation:
            cancel_embed = await clash_embed(
                context=ctx,
                message=f"Task cancelled.",
                success=False)
            return await message.edit(content=None,embeds=[embed,cancel_embed],view=None)
        
        if confirm_view.confirmation:
            await clan.new_leader(new_leader.id)
            complete_embed = await clash_embed(
                context=ctx,
                title=f"Change Leader: **{clan.title}**",
                message=f"Leader: <@{clan.leader}>"
                    + f"\n\n{clan.long_description}"
                    + f"\n\n>>> {clan.description}",
                url=clan.share_link,
                success=True,
                thumbnail=clan.badge)
            return await message.edit(
                content=None,
                embed=complete_embed,
                view=None
                )

    @app_command_group_clanset.command(
        name="leader",
        description="[Admin-only] Change the Leader of a registered Clan.")
    @app_commands.check(is_admin_or_leader)
    @app_commands.autocomplete(clan=autocomplete_clans)
    @app_commands.describe(clan="Select a Clan.")
    async def app_subcommand_change_leader(self,interaction:discord.Interaction,clan:str,new_leader:discord.Member):

        await interaction.response.defer()

        select_clan = await self.client.fetch_clan(clan)

        if not self.check_change_leader(interaction.guild,select_clan,interaction.user.id):
            embed = await clash_embed(
                context=interaction,
                message=f"You do not have permission to change the Leader of **{clan.title}**.",
                success=False,
                )
            return await interaction.edit_original_response(embed=embed)
        
        embed = await clash_embed(
            context=interaction,
            title=f"Change Leader: **{select_clan.title}**",
            message=f"**Current Leader:** <@{select_clan.leader}>"
                + f"\n**New Leader:** {new_leader.mention}"
                + f"\n\n{select_clan.long_description}"
                + f"\n\n>>> {select_clan.c_description}",
            thumbnail=select_clan.badge)
        confirm_view = MenuConfirmation(interaction)

        await interaction.followup.send(
            content=f"{interaction.user.mention}, please confirm the below action.",
            embed=embed,
            view=confirm_view,
            wait=True
            )        
        view_timed_out = await confirm_view.wait()

        if view_timed_out:
            timeout_embed = await clash_embed(
                context=interaction,
                message=f"Confirmation timed out. Please try again.",
                success=False)            
            return await interaction.edit_original_response(content=None,embeds=[embed,timeout_embed],view=None)

        if not confirm_view.confirmation:
            cancel_embed = await clash_embed(
                context=interaction,
                message=f"Task cancelled.",
                success=False)
            return await interaction.edit_original_response(content=None,embeds=[embed,cancel_embed],view=None)
        
        if confirm_view.confirmation:
            await select_clan.new_leader(new_leader.id)
            complete_embed = await clash_embed(
                context=interaction,
                title=f"Leader Changed: **{select_clan.title}**",
                message=f"New Leader: <@{select_clan.leader}>"
                    + f"\n\n{select_clan.long_description}"
                    + f"\n\n>>> {select_clan.c_description}",
                url=select_clan.share_link,
                success=True,
                thumbnail=select_clan.badge)
            return await interaction.edit_original_response(content=None,embed=complete_embed,view=None)
    
    ##################################################
    ### CLANSET / CONFIG
    ##################################################
    @command_group_clanset.command(name="config")
    @commands.guild_only()
    @commands.check(is_admin_or_coleader)
    async def subcommand_change_clan_config(self,ctx:commands.Context,clan_tag_or_abbreviation:str):
        """
        [Admin or Co-Leaders] Show/change Clan Configuration Options.

        Allows Co-Leaders to set up Recruitment Levels, Custom Clan Descriptions, War/Raid Reminders.
        """

        try:
            clan = await self.client.from_clan_abbreviation(clan_tag_or_abbreviation)
        except InvalidAbbreviation:
            clan = await self.client.fetch_clan(clan_tag_or_abbreviation)
        menu = ClanSettingsMenu(ctx,clan)
        await menu.start() 
    
    @app_command_group_clanset.command(
        name="config",
        description="[Admin or Co-Leaders] Show/change Clan Configuration Options.")
    @app_commands.check(is_admin_or_coleader)
    @app_commands.autocomplete(clan=autocomplete_clan_settings)
    @app_commands.describe(clan="Select a Clan. You must be a Server Admin or Leader/Co-Leader for the Clan.")
    async def app_command_clan_settings(self,interaction:discord.Interaction,clan:str):
        
        await interaction.response.defer()
        get_clan = await self.client.fetch_clan(clan)
        menu = ClanSettingsMenu(interaction,get_clan)
        await menu.start()