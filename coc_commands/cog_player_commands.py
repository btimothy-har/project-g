import coc
import discord

from typing import *

from redbot.core import commands, app_commands
from redbot.core.bot import Red

from coc_main.client.global_client import GlobalClient
from coc_main.cog_coc_main import ClashOfClansMain as coc_main

from coc_main.coc_objects.players.player import aPlayer
from coc_main.discord.member import aMember

from coc_main.utils.components import clash_embed
from coc_main.utils.checks import is_coleader, has_manage_roles
from coc_main.utils.autocomplete import autocomplete_players, autocomplete_players_members_only

from .views.new_member import NewMemberMenu
from .views.remove_member import RemoveMemberMenu
from .views.promote_demote import MemberRankMenu
from .views.member_nickname import MemberNicknameMenu
from .views.user_profile import UserProfileMenu
from .views.player_profile import PlayerProfileMenu

############################################################
############################################################
#####
##### CONTEXT MENUS
#####
############################################################
############################################################
@app_commands.context_menu(name="User Profile")
@app_commands.guild_only()
async def context_menu_user_profile(interaction:discord.Interaction,member:discord.Member):
    menu = None
    try:
        await interaction.response.defer()
        menu = UserProfileMenu(interaction,member)
        await menu.start()
    except Exception as exc:
        await GlobalClient.handle_command_error(exc,interaction,getattr(menu,'message',None))

@app_commands.context_menu(name="Clash Accounts")
@app_commands.guild_only()
async def context_menu_clash_accounts(interaction:discord.Interaction,member:discord.Member):
    menu = None
    try:
        await interaction.response.defer()

        member = await aMember(member.id,member.guild.id)
        accounts = [p async for p in GlobalClient.coc_client.get_players(member.account_tags)]
        menu = PlayerProfileMenu(interaction,accounts)
        await menu.start()

    except Exception as exc:
        await GlobalClient.handle_command_error(exc,interaction,getattr(menu,'message',None))

@app_commands.context_menu(name="Change Nickname")
@app_commands.guild_only()
async def context_menu_change_nickname(interaction:discord.Interaction,member:discord.Member):
    menu = None
    try:
        await interaction.response.defer(ephemeral=True)
        menu = MemberNicknameMenu(interaction,member,ephemeral=True)

        if not menu.for_self:
            if not is_coleader(interaction):
                return await interaction.followup.send(
                    content="You must be a Co-Leader or higher to use this on someone else.",
                    ephemeral=True
                    )
        await menu.start()
    except Exception as exc:
        await GlobalClient.handle_command_error(exc,interaction,getattr(menu,'message',None))

@app_commands.context_menu(name="Restore Roles")
@app_commands.guild_only()
async def context_menu_restore_roles(interaction:discord.Interaction,member:discord.Member):

    await interaction.response.defer(ephemeral=True)
    if not has_manage_roles(interaction):
        return await interaction.followup.send(
            content="You must have the Manage Roles permission to use this.",
            ephemeral=True
            )
    
    try:
        amember = await aMember(member.id,member.guild.id)
        added, failed = await amember.restore_user_roles()

        embed = await clash_embed(
            context=interaction,
            title=f"Restore Roles: {member.display_name}"
            )
        added_text = "\n".join([f"{role.mention}" for role in added])
        failed_text = "\n".join([f"{role.mention}" for role in failed])

        embed.add_field(
            name="Roles Added",
            value=added_text if len(added) > 0 else "None"
                + "\n\u200b",
            inline=False
            )
        embed.add_field(
            name="Roles Failed",
            value=failed_text if len(failed) > 0 else "None"
                + "\n\u200b",
            inline=False
            )
        await interaction.followup.send(embed=embed,ephemeral=True)

    except Exception as exc:
        await GlobalClient.handle_command_error(exc,interaction)

@app_commands.context_menu(name="Sync Roles")
@app_commands.guild_only()
async def context_menu_sync_roles(interaction:discord.Interaction,member:discord.Member):
    await interaction.response.defer(ephemeral=True)

    try:
        if not has_manage_roles(interaction):
            return await interaction.followup.send(
                content="You must have the Manage Roles permission to use this.",
                ephemeral=True
                )    
        m_member = await aMember(member.id,member.guild.id)
        added, removed = await m_member.sync_clan_roles(context=interaction,force=True)
        
        embed = await clash_embed(
            context=interaction,
            title=f"Sync Roles: {m_member.display_name}"
            )
        added_text = "\n".join([f"{role.mention}" for role in added])
        removed_text = "\n".join([f"{role.mention}" for role in removed])
        
        if len(added) == 0 and len(removed) == 0:
            embed.description = "No roles were changed."
        else:    
            embed.add_field(
                name="Roles Added",
                value=added_text if len(added) > 0 else "None"
                    + "\n\u200b",
                inline=False
                )
            embed.add_field(
                name="Roles Removed",
                value=removed_text if len(removed) > 0 else "None"
                    + "\n\u200b",
                inline=False
                )
        await interaction.followup.send(embed=embed,ephemeral=True)

    except Exception as exc:
        await GlobalClient.handle_command_error(exc,interaction)

############################################################
############################################################
#####
##### PLAYER COMMANDS COG
#####
############################################################
############################################################
class Players(commands.Cog,GlobalClient):
    """
    Player Commands.
    """

    __author__ = coc_main.__author__
    __version__ = coc_main.__version__

    def __init__(self):
        pass

    def format_help_for_context(self, ctx: commands.Context) -> str:
        context = super().format_help_for_context(ctx)
        return f"{context}\n\nAuthor: {self.__author__}\nVersion: {self.__version__}"

    async def cog_command_error(self,ctx:commands.Context,error:discord.DiscordException):
        original_exc = getattr(error,'original',error)
        await GlobalClient.handle_command_error(original_exc,ctx)

    async def cog_app_command_error(self,interaction:discord.Interaction,error:discord.DiscordException):
        original_exc = getattr(error,'original',error)
        await GlobalClient.handle_command_error(original_exc,interaction)
    
    @property
    def bot(self) -> Red:
        return GlobalClient.bot
    
    ############################################################
    #####
    ##### ASSISTANT FUNCTIONS
    #####
    ############################################################   
    @commands.Cog.listener()
    async def on_assistant_cog_add(self,cog:commands.Cog):
        schema = [
            {
                "name": "_assistant_get_linked_clash_accounts",
                "description": "Gets a user's Clash Accounts that are linked to their Discord ID. Only returns high-level information. Use other functions to get specific details.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    },
                },
            {
                "name": "_assistant_get_player_named",
                "description": "Searches the database for players matching the provided name string. Returns a list of matches.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "player_name": {
                            "description": "The Clash of Clans Player Name to search for. Not caps sensitive.",
                            "type": "string",
                            },
                        },
                    "required": ["player_name"],
                    },
                },            
            {
                "name": "_assistant_get_player_clan_status",
                "description": "Gets Clan and Member information about a Clash Account. Use this if you need to find out which Clan a Player is in, or whether the Player is a member in the Alliance. A Player Tag identifier is needed.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "player_tag": {
                            "description": "The unique player tag of the account.",
                            "type": "string",
                            },
                        },
                    "required": ["player_tag"],
                    },
                },
            {
                "name": "_assistant_get_account_heroes",
                "description": "Gets only Hero details for a Clash Account, based on the Tag provided. Returns a JSON object.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "player_tag": {
                            "description": "The unique player tag of the account.",
                            "type": "string",
                            },
                        },
                    "required": ["player_tag"],
                    },
                }
            ]
        await cog.register_functions(cog_name="Players", schemas=schema)
    
    async def _assistant_get_player_named(self,player_name:str,*args,**kwargs) -> str:
        try:
            n = str(player_name)
            q_doc = {'name':{'$regex':f'^{n}',"$options":"i"}},
            pipeline = [
                {'$match': q_doc},
                {'$sample': {'size': 8}}
                ]
            query = self.database.db__player.aggregate(pipeline)

            player_tags = [c['_id'] async for c in query]
            if len(player_tags) == 0:
                return f"No matches for {player_name} found."
            
            players = [p async for p in self.coc_client.get_players(player_tags)]
            ret_players = [p.name_json() for p in players]
            return f"Found {len(ret_players)} Players matching `{player_name}`. Players: {ret_players}"
        except:
            return f"Error finding player with name `{player_name}`."

    async def _assistant_get_linked_clash_accounts(self,guild:discord.Guild,user:discord.Member,*args,**kwargs) -> str:
        if not user:
            return "No user found."        
        member = await aMember(user.id,guild.id)
        accounts = [p async for p in self.coc_client.get_players(member.account_tags)]
        return f"{user.name} has the following accounts linked: {[a.name_json() for a in accounts]}"
    
    async def _assistant_get_player_clan_status(self,player_tag:str,*args,**kwargs) -> str:
        try:
            account = await self.coc_client.get_player(player_tag)
        except coc.NotFound:
            return "The player tag provided does not exist."
        except (coc.Maintenance,coc.GatewayError):
            return "Clash of Clans API is currently not available."
        except:
            return "An exception occurred while fetching the player."
        if not account:
            return "No account found."
        return f"{account.profile_json()}"
    
    async def _assistant_get_account_heroes(self,player_tag:str,*args,**kwargs) -> str:
        try:
            account = await self.coc_client.get_player(player_tag)
        except coc.NotFound:
            return "The player tag provided does not exist."
        except (coc.Maintenance,coc.GatewayError):
            return "Clash of Clans API is currently not available."
        except:
            return "An exception occurred while fetching the player."
        if not account:
            return "No account found."
        return f"Hero Levels for account {account.name} (Tag: {account.tag}): {account.hero_json()}"

    ############################################################
    #####
    ##### COMMAND GROUP: MEMBER
    #####
    ############################################################
    @commands.group(name="member")
    @commands.guild_only()
    async def cmdgroup_member(self,ctx):
        """
        Group for Member-related Commands.

        **This is a command group. To use the sub-commands below, follow the syntax: `$member [sub-command]`.**
        """
        if not ctx.invoked_subcommand:
            pass

    appgrp_member = app_commands.Group(
        name="member",
        description="Group for Member commands. Equivalent to [p]member.",
        guild_only=True
        )

    ############################################################
    #####
    ##### COMMAND: MEMBER SENDDM
    #####
    ############################################################
    @cmdgroup_member.command(name="senddm")
    @commands.guild_only()
    @commands.check(is_coleader)
    async def subcmd_member_senddm(self,ctx:commands.Context,member:discord.Member):
        """
        Sends the Welcome DM to the user.
        """
   
        menu = NewMemberMenu(ctx,member)
        send = await menu.send_welcome_dm()
        if send:
            return await ctx.send(f"Sent Welcome DM to {member.display_name}.")
        else:
            return await ctx.send(f"Could not send Welcome DM to {member.display_name}.")
    
    @appgrp_member.command(name="senddm",
        description="Sends the Welcome DM to the user.")
    @app_commands.check(is_coleader)
    @app_commands.describe(
        member="The Discord User to send the DM to.")
    async def appcmd_member_senddm(self,interaction:discord.Interaction,member:discord.Member):

        await interaction.response.defer(ephemeral=True)
        menu = NewMemberMenu(interaction,member)
        send = await menu.send_welcome_dm()
        if send:
            return await interaction.followup.send(f"Sent Welcome DM to {member.display_name}.")
        else:
            return await interaction.followup.send(f"Could not send Welcome DM to {member.display_name}.")

    ############################################################
    #####
    ##### COMMAND: MEMBER ADD
    #####
    ############################################################
    @cmdgroup_member.command(name="add")
    @commands.guild_only()
    @commands.check(is_coleader)
    async def subcmd_member_add(self,ctx:commands.Context,member:discord.Member):
        """
        Add a Member to the Alliance.
        """
   
        menu = NewMemberMenu(ctx,member)
        await menu.start()
    
    @appgrp_member.command(name="add",
        description="Add a Member to the Alliance.")
    @app_commands.check(is_coleader)
    @app_commands.describe(
        member="The Discord User to add to the Alliance.",
        send_dm="Do you want to send the Welcome DM after adding? Defaults to Yes.")
    @app_commands.choices(send_dm=[
        app_commands.Choice(name="Yes",value=0),
        app_commands.Choice(name="No",value=1)])
    async def appcmd_member_add(self,interaction:discord.Interaction,member:discord.Member,send_dm:Optional[app_commands.Choice[int]]=0):

        await interaction.response.defer()
        menu = NewMemberMenu(interaction,member,bool(send_dm))
        await menu.start()
    
    ############################################################
    #####
    ##### COMMAND: MEMBER REMOVE
    #####
    ############################################################
    @cmdgroup_member.command(name="remove")
    @commands.guild_only()
    @commands.check(is_coleader)
    async def subcmd_member_remove(self,ctx:commands.Context,discord_member:discord.Member):
        """
        Remove a Member/Member's Accounts from the Alliance.

        Only accepts input by Discord Member. To remove by Clash Account Tag, use the equivalent App/Slash Command instead.
        """

        menu = RemoveMemberMenu(ctx,member=discord_member)            
        await menu.start()
    
    @appgrp_member.command(name="remove",
        description="Removes a Member/Clash Account from the Alliance.")
    @app_commands.check(is_coleader)
    @app_commands.autocomplete(player=autocomplete_players_members_only)
    @app_commands.describe(
        member="Select a Discord Member to remove from the Alliance.",
        player="Select a Clash of Clans account to remove. Only member accounts are valid.",
        discord_id="The Discord User ID to remove from the Alliance.")
    async def appcmd_member_remove(self,
        interaction:discord.Interaction,
        member:Optional[discord.Member]=None,
        player:Optional[str]=None,
        discord_id:Optional[str]=None):
        
        await interaction.response.defer()

        selected_account = None
        selected_member = None
        discord_id = int(discord_id) if discord_id else None

        if player:
            selected_account = await self.coc_client.get_player(player)
        selected_member = member if member else discord_id if discord_id else None

        menu = RemoveMemberMenu(interaction,member=selected_member,account=selected_account)
        await menu.start()
    
    ############################################################
    #####
    ##### COMMAND: PROMOTE
    #####
    ############################################################
    @commands.command(name="promote")
    @commands.guild_only()
    @commands.check(is_coleader)
    async def cmd_promote_member(self,ctx:commands.Context,discord_member:discord.Member):
        """
        Promote a Member.

        Members are ranked based on Discord Account and Clan. When promoting a Member, all their accounts registered in the provided Clan are promoted/demoted as a group.

        **Clan Permissions Apply**
        > - Only Clan Leaders and Co-Leaders can promote Elders/Members.
        > - Leaders and Co-Leaders cannot be promoted.
        > - You can only promote for Clans that you are a Leader/Co-Leader in.
        > - A User must have active accounts in that Clan to be eligible for promotion.

        **To change a Clan Leader, please contact <@644530507505336330>.**
        """
        menu = MemberRankMenu(ctx,discord_member)
        await menu.promote()

    @app_commands.command(name="promote",
        description="Promote a Member. Use `$help promote` for details.")
    @app_commands.check(is_coleader)
    @app_commands.describe(
        discord_member="The Member to promote. Members must have an active account to be eligible.")
    async def appcmd_promote_member(self,interaction:discord.Interaction,discord_member:discord.Member):
        
        await interaction.response.defer()
        menu = MemberRankMenu(interaction,discord_member)
        await menu.promote()
    
    ############################################################
    #####
    ##### COMMAND: DEMOTE
    #####
    ############################################################
    @commands.command(name="demote")
    @commands.guild_only()
    @commands.check(is_coleader)
    async def cmd_demote_member(self,ctx:commands.Context,discord_member:discord.Member):
        """
        Demote a Member.

        Members are ranked based on Discord Account and Clan. When promoting a Member, all their accounts registered in the provided Clan are promoted/demoted as a group.

        **Clan Permissions Apply**
        > - Only Clan Leaders can demote Co-Leaders.
        > - Clan Leaders and Co-Leaders can demote Elders.
        > - Leaders and Members cannot be demoted.
        > - You can only demote for Clans that you are a Leader/Co-Leader in.
        > - A User must have active accounts in that Clan to be eligible for demotion.

        **To change a Clan Leader, please contact <@644530507505336330>.**
        """

        menu = MemberRankMenu(ctx,discord_member)
        await menu.demote()

    @app_commands.command(name="demote",
        description="Demote a Member. Use `$help demote` for details.")
    @app_commands.check(is_coleader)
    @app_commands.describe(
        discord_member="The Member to demote. Members must have an active account to be eligible.")
    async def appcmd_demote_member(self,interaction:discord.Interaction,discord_member:discord.Member):

        await interaction.response.defer()
        menu = MemberRankMenu(interaction,discord_member)
        await menu.demote()
    
    ############################################################
    #####
    ##### COMMAND: NICKNAME
    #####
    ############################################################
    @commands.command(name="nickname")
    @commands.guild_only()
    async def cmd_user_nickname(self,ctx:commands.Context):
        """
        Change your Server Nickname.
        
        You can choose from one of your active member accounts to be displayed as your nickname.
        If you are not an active member, your nickname will default to your highest ranked Clash account.
        """    
        menu = MemberNicknameMenu(ctx,ctx.author)
        await menu.start()

    @app_commands.command(name="nickname",
        description="Select a Clash account to be displayed as your nickname.")
    @app_commands.guild_only()
    async def appcmd_user_nickname(self,interaction:discord.Interaction):

        await interaction.response.defer()
        menu = MemberNicknameMenu(interaction,interaction.user)
        await menu.start()
    
    ############################################################
    #####
    ##### COMMAND: PROMOTE
    #####
    ############################################################
    @commands.command(name="profile")
    @commands.guild_only()
    async def cmd_user_profile(self,ctx:commands.Context,discord_member:Optional[discord.User]=None):
        """
        View a Member's Clash Profile.

        Defaults to your own profile if no member is provided.

        If viewing your own profile, allows you to Add/Remove Account Links.
        """
        
        if discord_member is None:
            discord_member = ctx.author

        menu = UserProfileMenu(ctx,discord_member)
        await menu.start()
    
    @app_commands.command(name="profile",
        description="View your's or a Member's Clash Profile.")
    @app_commands.guild_only()
    @app_commands.describe(
        member="User to display profile for. If not specified, your own profile will be displayed.")
    async def appcmd_user_profile(self,interaction:discord.Interaction,member:Optional[discord.Member]=None):            
        
        await interaction.response.defer()
        if member is None:
            member = interaction.user

        menu = UserProfileMenu(interaction,member)
        await menu.start()
    
    ############################################################
    #####
    ##### COMMAND: PLAYER
    #####
    ############################################################
    @commands.command(name="player")
    @commands.guild_only()
    async def cmd_player_profile(self,ctx:commands.Context,player_tag:Optional[str]):
        """
        View Player Summary, Stats and Details.

        The Slash Command variant allows you to select by Discord User or Player Tag.
        """

        view_accounts = []
        if player_tag:
            player = await self.coc_client.get_player(player_tag)
            if isinstance(player,aPlayer):
                view_accounts.append(player)
        else:
            member = await aMember(ctx.author.id,ctx.guild.id)
            view_accounts.extend([p async for p in self.coc_client.get_players(member.account_tags)])
        
        if len(view_accounts) == 0:
            embed = await clash_embed(
                context=self.ctx,
                message="I couldn't find any accounts to show. Check your input, maybe?",
                success=False
                )
            return await ctx.send(embed=embed)
        
        menu = PlayerProfileMenu(ctx,view_accounts)
        await menu.start()
    
    @app_commands.command(name="player",
        description="View Player Summary, Stats and Details. If no input is provided, defaults to your own profile.")
    @app_commands.guild_only()
    @app_commands.autocomplete(player=autocomplete_players)
    @app_commands.describe(
        member="Show all accounts for a Discord Member.",
        player="Search for a Clash Player or manually input a Player Tag.",
        user_id="Get accounts for a Discord User, by Discord ID.")
    async def appcmd_player_profile(self,
        interaction:discord.Interaction,
        member:Optional[discord.Member]=None,
        player:Optional[str]=None,
        user_id:Optional[int]=None):

        await interaction.response.defer()

        view_accounts = []
        if player:
            get_player = await self.coc_client.get_player(player)
            if isinstance(get_player,aPlayer):
                view_accounts.append(get_player)

        if member:
            get_member = await aMember(member.id,interaction.guild.id)
            view_accounts.extend([p async for p in self.coc_client.get_players(get_member.account_tags)])

        if user_id:
            get_member = await aMember(user_id,interaction.guild.id)
            view_accounts.extend([p async for p in self.coc_client.get_players(get_member.account_tags)])

        if not (player or member or user_id):
            get_member = await aMember(interaction.user.id,interaction.guild.id)
            view_accounts.extend([p async for p in self.coc_client.get_players(get_member.account_tags)])
        
        if len(view_accounts) == 0:
            return await interaction.followup.send(content=f"Did not find any accounts for the provided input.")
        
        if len(view_accounts) == 0:
            embed = await clash_embed(
                context=self.ctx,
                message="I couldn't find any accounts to show. Check your input, maybe?",
                success=False
                )
            return await interaction.followup.send(embed=embed)
        
        menu = PlayerProfileMenu(interaction,view_accounts)
        await menu.start()