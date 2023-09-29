import discord

from typing import *
from redbot.core import commands

from coc_data.objects.players.player import aPlayer
from coc_data.objects.discord.member import aMember

from coc_data.utilities.components import *

from coc_data.constants.ui_emojis import *
from coc_data.constants.coc_emojis import *
from coc_data.constants.coc_constants import *
from coc_data.exceptions import *

from ..helpers.components import *
from ..exceptions import *

####################################################################################################
#####
##### VIEW MENU: USER PROFILE / LINKS
#####
####################################################################################################
class UserProfileMenu(DefaultView):
    def __init__(self,
        context:Union[commands.Context,discord.Interaction],
        member:Union[discord.User,discord.Member]):

        self.add_link_button = DiscordButton(
            function=self._add_link,
            label="Add",
            emoji=EmojisUI.ADD,
            style=discord.ButtonStyle.blurple
            )
        self.delete_link_button = DiscordButton(
            function=self._delete_link,
            label="Delete",
            emoji=EmojisUI.DELETE,
            style=discord.ButtonStyle.grey
            )
        super().__init__(context,timeout=300)

        self.member = aMember(member.id,self.guild.id)

        if self.user.id == self.member.user_id:
            self.add_item(self.add_link_button)
            self.add_item(self.delete_link_button)        

    ##################################################
    ### OVERRIDE BUILT IN METHODS
    ##################################################
    async def on_timeout(self):
        await self.message.edit(view=None)
        self.stop_menu()
    
    ##################################################
    ### START / STOP
    ##################################################
    async def start(self):
        self.is_active = True
        embed = await UserProfileMenu.profile_embed(self.ctx,self.member)

        if isinstance(self.ctx,discord.Interaction):
            await self.ctx.edit_original_response(embeds=embed,view=self)
            self.message = await self.ctx.original_response()
        else:
            self.message = await self.ctx.reply(embeds=embed,view=self)
    
    ##################################################
    ### ADD LINK FUNCTIONS/CALLBACKS
    ##################################################
    async def _add_link(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer(ephemeral=True)
        add_link_view = AddLinkMenu(interaction,self.member)
        await add_link_view._start_add_link()

        await add_link_view.wait()
        embed = await UserProfileMenu.profile_embed(self.ctx,self.member)
        await interaction.edit_original_response(embeds=embed,view=self)
    
    async def _delete_link(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.defer(ephemeral=True)
        delete_link_view = DeleteLinkMenu(interaction,self.member)
        await delete_link_view._start_delete_link()

        await delete_link_view.wait()
        embed = await UserProfileMenu.profile_embed(self.ctx,self.member)
        await interaction.edit_original_response(embeds=embed,view=self)
    
    ##################################################
    ### HELPERS
    ##################################################
    @staticmethod
    async def profile_embed(ctx:Union[discord.Interaction,commands.Context],member:aMember):


        embed = await clash_embed(
            context=ctx,
            title=member.display_name,
            message=(f"{' '.join([c.emoji for c in member.home_clans])}\n\n" if len(member.home_clans) > 0 else "")
                + "\u200b",
            embed_color=next((r.color for r in sorted(member.discord_member.roles,key=lambda x:(x.position),reverse=True) if r.color.value), None),
            thumbnail=member.display_avatar
            )

        for account in member.accounts[:10]:
            embed.add_field(
                name=(f"{account.home_clan.emoji} " if account.is_member else "") + f"{account.town_hall.emote} **{account.name}**",
                value=f"{account.hero_description}\n[Player Link: {account.tag}]({account.share_link})\n\u200b",
                inline=False
                )
        if len(member.accounts) > 10:
            embed_2 = await clash_embed(
                context=ctx,
                embed_color=next((r.color for r in sorted(member.discord_member.roles,key=lambda x:(x.position),reverse=True) if r.color.value), None),
                thumbnail=member.display_avatar,
                show_author=False,
                )
            for account in member.accounts[10:20]:
                embed_2.add_field(
                    name=(f"{account.home_clan.emoji} " if account.is_member else "") + f"{account.town_hall.emote} **{account.name}**",
                    value=f"{account.hero_description}\n[Player Link: {account.tag}]({account.share_link})\n\u200b",
                    inline=False
                    )
            return [embed,embed_2]
        return [embed]

class AddLinkMenu(DefaultView):
    def __init__(self,
        context:discord.Interaction,
        member:aMember):

        self.member = member
        self.start_add_link = DiscordButton(
            function=self._callback_add_link,
            label="I have my Tag/Token",
            style=discord.ButtonStyle.blurple
            )
        
        super().__init__(context,timeout=120)        
        self.add_item(self.start_add_link)

        self.add_link_modal = DiscordModal(
            function=self._callback_add_link_modal,
            title=f"Add Clash Link",
            )
        self.add_link_modal.add_field(
            label="Clash Account Tag",
            placeholder="#XXXXXX",
            required=True
            )
        self.add_link_modal.add_field(
            label="API Token",
            placeholder="API Tokens are not case sensitive.",
            required=True
            )
    ##################################################
    ### OVERRIDE BUILT IN METHODS
    ##################################################
    async def on_timeout(self):
        self.is_active = False
        self.start_add_link.label = "Sorry, you timed out! Please try again."
        self.start_add_link.disabled = True
        await self.message.edit(view=self)
        self.stop_menu()

    ##################################################
    ### CALLBACK METHODS
    ################################################## 
    async def _start_add_link(self):
        self.is_active = True
        embed = await clash_embed(
            context=self.ctx,
            message=f"To link a new Clash Account, you will need:"
                + f"\n> 1) The Account Tag of the account"
                + f"\n> 2) An in-game API Token"
                + f"\n\n**Refer to the image below on how to retrieve the API Token.** When you are ready, click on the button below to submit your Tag/Token pair."
                + f"\n\u200b",
            image='https://i.imgur.com/Q1JwMzK.png'
            )
        embed.add_field(
            name="**Important Information**",
            value="- Accounts already registered as **Clan Members** cannot be modified."
                + f"\n- If an account is already linked to another Discord account, it will be unlinked from that account and linked to yours."
                + f"\n- Link information is not shared with other Clash of Clans bots.",
            inline=False
            )
        self.message = await self.ctx.followup.send(embed=embed,view=self,ephemeral=True,wait=True)
        
    async def _callback_add_link(self,interaction:discord.Interaction,button:DiscordButton):
        await interaction.response.send_modal(self.add_link_modal)
    
    async def _callback_add_link_modal(self,interaction:discord.Interaction,modal:DiscordModal):
        await interaction.response.defer(ephemeral=True)
        await self.ctx.edit_original_response(view=None)

        tag = modal.children[0].value
        api_token = modal.children[1].value
        
        if self.bot.user.id == 828838353977868368:
            verify = True
        else:
            try:
                verify = await self.bot.coc_client.verify_player_token(player_tag=tag,token=api_token)
            except (coc.NotFound) as exc:
                embed = await clash_embed(
                    context=self.ctx,
                    message=f"The tag {tag.upper()} doesn't seem to be valid.",
                    success=False,
                    view=None
                    )
                await interaction.edit_original_response(embed=embed,view=None)
                return
            except (coc.Maintenance,coc.GatewayError) as exc:
                raise ClashAPIError(exc) from exc

        try:
            self.add_link_account = await aPlayer.create(tag)
        except InvalidTag:
            embed = await clash_embed(
                context=self.ctx,
                message=f"The tag {tag.upper()} doesn't seem to be valid.",
                success=False
                )
            return await interaction.edit_original_response(embed=embed,view=None)
        
        if self.add_link_account.is_member:
            verify = False
            embed = await clash_embed(
                context=self.ctx,
                message=f"The account {self.add_link_account.tag} is already registered as a **Clan Member**, and cannot be relinked."
                    + f"\n\n**{self.add_link_account.title}**"
                    + f"\n{self.add_link_account.member_description}"
                    + (f"\n{self.add_link_account.discord_user_str}" if self.add_link_account.discord_user else "")
                    + f"\n{self.add_link_account.long_description}",
                success=False
                )
            await interaction.edit_original_response(embed=embed,view=None)
            return self.stop_menu()

        if verify:
            self.add_link_account.discord_user = self.user.id
            embed = await clash_embed(
                context=self.ctx,
                message=f"The account **{self.add_link_account.title}** is now linked to your Discord account!",
                success=True
                )
            await interaction.edit_original_response(embed=embed,view=None)
        else:
            embed = await clash_embed(
                context=self.ctx,
                message=f"The API Token provided is invalid. Please try again.",
                success=False,
                view=None
                )
            await interaction.edit_original_response(embed=embed,view=None)
        self.stop()

class DeleteLinkMenu(DefaultView):
    def __init__(self,
        context:discord.Interaction,
        member:aMember):

        self.is_active = True
        self.waiting_for = False

        self.member = member

        select_options = [discord.SelectOption(
            label=f"{account}",
            value=account.tag,
            description=account.member_description_no_emoji,
            emoji=account.town_hall.emoji)
            for account in self.member.accounts if not account.is_member
            ]
        self.remove_link_dropdown = DiscordSelectMenu(
            function=self._callback_remove_account,
            options=select_options,
            placeholder="Select an account to remove.",
            min_values=1,
            max_values=len(select_options)
            )
        
        super().__init__(context,timeout=120)
        self.add_item(self.remove_link_dropdown)
    
    ##################################################
    ### OVERRIDE BUILT IN METHODS
    ##################################################
    async def on_timeout(self):
        self.is_active = False
        self.remove_link_dropdown.placeholder = "Sorry, you timed out! Please try again."
        self.remove_link_dropdown.disabled = True
        await self.message.edit(view=self)
        self.stop_menu()

    ##################################################
    ### CALLBACK METHODS
    ################################################## 
    async def _start_delete_link(self):
        self.is_active = True
        embed = await clash_embed(
            context=self.ctx,
            message=f"Please select an account to unlink from your profile. Accounts that cannot be removed are not shown in the dropdown."
                + "\n\u200b",
            )
        embed.add_field(
            name="**Important Information**",
            value="- Accounts already registered as **Clan Members** cannot be unlinked."
                + f"\n- Link information is not shared with other Clash of Clans bots."
                + f"\n- Unlinking does not delete an account from the bot.",
            inline=False
            )
        self.message = await self.ctx.followup.send(embed=embed,view=self,ephemeral=True,wait=True)
        
    async def _callback_remove_account(self,interaction:discord.Interaction,menu:DiscordSelectMenu):
        await interaction.response.defer()
        remove_accounts = [account for account in self.member.accounts if account.tag in menu.values]

        for account in remove_accounts:
            account.discord_user = 0
        
        embed = await clash_embed(
            context=self.ctx,
            message=f"The following accounts have been unlinked from your profile:"
                + f"\n\u200b"
                + f"\n".join([f"**{account.title}**" for account in remove_accounts]),
            success=True
            )
        await interaction.edit_original_response(embed=embed,view=None)
        self.stop()