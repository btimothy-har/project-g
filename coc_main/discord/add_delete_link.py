import coc
import discord

from typing import *

from ..api_client import BotClashClient, ClashAPIError, InvalidTag
from ..cog_coc_client import ClashOfClansClient, BasicPlayer

from .member import aMember

from ..utils.components import DefaultView, DiscordSelectMenu, DiscordButton, DiscordModal, clash_embed
from ..utils.constants.coc_emojis import EmojisTownHall

bot_client = BotClashClient()

class AddLinkMenu(DefaultView):
    def __init__(self,
        context:discord.Interaction,
        member:aMember):

        self.m_id = 0
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
        
    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
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
        self.m_id = interaction.message.id
        await interaction.response.send_modal(self.add_link_modal)
    
    async def _callback_add_link_modal(self,interaction:discord.Interaction,modal:DiscordModal):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.edit_message(self.m_id,view=None)

        o_tag = modal.children[0].value
        api_token = modal.children[1].value

        if not coc.utils.is_valid_tag(o_tag):
            raise InvalidTag(o_tag)
        
        tag = coc.utils.correct_tag(o_tag)
        
        if self.bot.user.id == 828838353977868368:
            verify = True
        else:
            try:
                verify = await bot_client.coc.verify_player_token(player_tag=tag,token=api_token)
            except (coc.NotFound) as exc:
                raise InvalidTag(tag) from exc
            except (coc.Maintenance,coc.GatewayError) as exc:
                raise ClashAPIError(exc) from exc

        self.add_link_account = await bot_client.coc.get_player(tag)

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
            await interaction.followup.edit_message(self.m_id,embed=embed,view=None)
            return self.stop_menu()

        if verify:
            await BasicPlayer.set_discord_link(self.add_link_account.tag,interaction.user.id)
            embed = await clash_embed(
                context=self.ctx,
                message=f"The account **{self.add_link_account.tag}** is now linked to your Discord account!",
                success=True
                )
            await interaction.followup.edit_message(self.m_id,embed=embed,view=None)
        else:
            embed = await clash_embed(
                context=self.ctx,
                message=f"The API Token provided is invalid. Please try again.",
                success=False
                )
            await interaction.followup.edit_message(self.m_id,embed=embed,view=None)
        self.stop()

class DeleteLinkMenu(DefaultView):
    def __init__(self,
        context:discord.Interaction,
        member:aMember):

        self.is_active = True
        self.waiting_for = False

        self.member = member

        super().__init__(context,timeout=120)

    @property
    def client(self) -> ClashOfClansClient:
        return bot_client.bot.get_cog("ClashOfClansClient")
    
    ##################################################
    ### OVERRIDE BUILT IN METHODS
    ##################################################
    async def on_timeout(self):
        self.is_active = False
        if getattr(self,'remove_link_dropdown',None):
            self.remove_link_dropdown.placeholder = "Sorry, you timed out! Please try again."
            self.remove_link_dropdown.disabled = True
        await self.message.edit(view=self)
        self.stop_menu()

    ##################################################
    ### CALLBACK METHODS
    ################################################## 
    async def _start_delete_link(self):
        await self.member.load()
        m_accounts = [p async for p in bot_client.coc.get_players(self.member.account_tags)]
        m_accounts.sort(key=lambda x:(x.town_hall_level,x.exp_level,x.clean_name),reverse=True)

        select_options = [discord.SelectOption(
            label=f"{account}",
            value=account.tag,
            description=account.member_description_no_emoji,
            emoji=EmojisTownHall.get(account.town_hall_level))
            for account in m_accounts if not account.is_member
            ]
        if len(select_options) > 0:
            remove_link_dropdown = DiscordSelectMenu(
                function=self._callback_remove_account,
                options=select_options,
                placeholder="Select an account to remove.",
                min_values=1,
                max_values=len(select_options)
                )        
            self.add_item(remove_link_dropdown)

        self.is_active = True
        embed = await clash_embed(
            context=self.ctx,
            message=f"Please select an account to unlink from your profile. Accounts that cannot be removed are not shown in the dropdown. If you have no eligible accounts, the dropdown is not shown."
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
        remove_accounts = [p async for p in bot_client.coc.get_players(menu.values)]

        for account in remove_accounts:
            await BasicPlayer.set_discord_link(account.tag,0)
        
        embed = await clash_embed(
            context=self.ctx,
            message=f"The following accounts have been unlinked from your profile:"
                + f"\n\u200b"
                + f"\n".join([f"**{account.title}**" for account in remove_accounts]),
            success=True
            )
        await interaction.edit_original_response(embed=embed,view=None)
        self.stop()