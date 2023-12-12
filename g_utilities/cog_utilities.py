import discord
import xml.etree.ElementTree as ET

from typing import *
from redbot.core import commands, app_commands
from redbot.core.commands import Context
from redbot.core.bot import Red

from timestamps.timestamps import DateConverter

def administrator_check(ctx:Union[discord.Interaction,commands.Context]):
    """Check if the user is an administrator."""
    if isinstance(ctx,commands.Context):
        return ctx.author.guild_permissions.administrator
    elif isinstance(ctx,discord.Interaction):
        return ctx.user.guild_permissions.administrator
    else:
        return False

class GuildUtility(commands.Cog):
    """Guild Utility Commands."""

    def __init__(self,bot:Red):
        self.bot: Red = bot
    
    ############################################################
    ############################################################
    #####
    ##### COUNTING UTILITIES
    #####
    ############################################################
    ############################################################
    @commands.command(name="unlockcounting")
    @commands.guild_only()
    @commands.check(administrator_check)
    async def release_counting_lock(self,ctx:commands.Context):

        counting_channel = ctx.bot.get_channel(808387496819687494)
        await counting_channel.set_permissions(
            counting_channel.guild.default_role,
            send_messages=None
            )

        embed = discord.Embed(
            description=f"Counting has been unlocked.",
            color=await self.bot.get_embed_color(counting_channel))
        embed.set_footer(text=ctx.guild.name,icon_url=ctx.guild.icon if ctx.guild.icon else self.bot.user.display_avatar)
        return await counting_channel.send(embed=embed)
    
    @commands.Cog.listener("on_message")
    async def counting_listener(self,message:discord.Message):

        if not message.guild:
            return
        
        if message.author.bot and message.author.id == 510016054391734273 and message.channel.id == 808387496819687494:
            if all(substring in message.content for substring in ['You have used','guild save']):

                await message.channel.set_permissions(message.channel.guild.default_role,send_messages=False)
                embed = discord.Embed(
                    title="Guild Save Used!",
                    description=f"Counting has been locked until a <@&733023831366697080> releases the lock."
                        + f"\n\nTo release the lock, run the `unlockcounting` command.",
                    color=0xFF0000)
                embed.set_footer(text=message.guild.name,icon_url=message.guild.icon if message.guild.icon else self.bot.user.display_avatar)
                return await message.channel.send(embed=embed)
    
    ############################################################
    ############################################################
    #####
    ##### ASSISTANT UTILS
    #####
    ############################################################
    ############################################################ 
    @commands.Cog.listener()
    async def on_assistant_cog_add(self,cog:commands.Cog):
        schema = [
            {
                "name": "_assistant_create_thread",
                "description": "Creates a private thread to have a private conversation with a user. Use this if the user has requested to speak with you privately, or if you need to speak with them privately. Remember to let the user know why you are creating the thread.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "description": "The reason you created this thread.",
                            "type": "string",
                            },
                        },
                    "required": ["reason"],
                    },
                },
            {
                "name": "_assistant_wikipedia_search",
                "description": "Searches Wikipedia for results. Returns paginated information. Submit repeated requests with the page_num parameter to view more pages.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "description": "The query to search Wikipedia for. As Wikipedia uses strict search, you may need to try different queries to find the result you're looking for. It may help to search for a broad subject and scroll through results. For example, instead of searching for 'Jollibee History', search for 'Jollibee' and review the results. ",
                            "type": "string",
                            },
                        "page_num": {
                            "description": "The result page you'd like to retrieve.",
                            "type": "string",
                            },
                        },
                    "required": ["query","page_num"],
                    },
                },
            {
                "name": "_assistant_wolfram_query",
                "description": "Submits a query to WolframAlpha. This can be used to source for factual information outside your existing training model.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "description": "The question or query to search Wolfram for.",
                            "type": "string",
                            },
                        },
                    "required": ["question"],
                    },
                }
            ]
        await cog.register_functions(cog_name="GuildUtility", schemas=schema)

    async def _assistant_create_thread(self,
        user:discord.Member,
        channel:Union[discord.TextChannel,discord.Thread,discord.ForumChannel],
        reason:str,
        *args,**kwargs) -> str:
    
        if not isinstance(channel,discord.TextChannel):
            return "You are already chatting in a thread."
        
        thread = await channel.create_thread(
            name=f"Chat with {user.display_name}",
            reason=reason
            )
        await thread.send(f"{user.mention}, please note that to chat with me here, you will need to either reply or mention me in your message.")

        return f"Created a thread with {user.display_name}. Let the user know to continue the conversation there."

    async def _assistant_wikipedia_search(self,bot:Red,query:str,page_num:int=1,*args,**kwargs) -> str:
        wikipedia_cog = bot.get_cog("Wikipedia")
        
        get_result, a = await wikipedia_cog.perform_search(query)
        num_of_results = len(get_result)

        if len(get_result) < 1:
            return "Could not find a response in Wikipedia."

        if page_num > num_of_results:
            return f"You've exceeded the number of available pages. There are only {len(num_of_results)} pages. The last page is: {get_result[-1].to_dict()}."
        
        page = get_result[page_num-1]
        return f"There are {num_of_results} pages. Returning page {page_num}.\n\n{page.to_dict()}"
    
    async def _assistant_wolfram_query(self,bot:Red,question:str,*args,**kwargs) -> str:
        wolfram_cog = bot.get_cog("Wolfram")
        api_key = await wolfram_cog.config.WOLFRAM_API_KEY()
        if not api_key:
            return "No API key set for Wolfram Alpha."

        url = "http://api.wolframalpha.com/v2/query?"
        query = question
        payload = {"input": query, "appid": api_key}
        headers = {"user-agent": "Red-cog/2.0.0"}

        async with wolfram_cog.session.get(url, params=payload, headers=headers) as r:
            result = await r.text()
        
        root = ET.fromstring(result)
        a = []
        for pt in root.findall(".//plaintext"):
            if pt.text:
                a.append(pt.text.capitalize())
        if len(a) < 1:
            message = "Could not find a response in WolframAlpha."
        else:
            message = "\n".join(a[0:3])
            if "Current geoip location" in message:
                message = "Could not find a response in WolframAlpha."
        return message
    
    ############################################################
    ############################################################
    #####
    ##### SLASH WRAPPER
    #####
    ############################################################
    ############################################################    
    @app_commands.command(name="away",
        description="Tell the bot you're away or back.")
    @app_commands.guild_only()
    @app_commands.describe(
        status="Only reply when you're set to this status on Discord.",
        message="[Optional] The custom message to display when you're mentioned."        
        )
    @app_commands.choices(status=[
        app_commands.Choice(name="Always",value=0),
        app_commands.Choice(name="Do Not Disturb",value=1),
        app_commands.Choice(name="Gaming",value=2),
        app_commands.Choice(name="Idle",value=3),
        app_commands.Choice(name="Listening",value=4),
        app_commands.Choice(name="Offline",value=5)
        ])
    async def app_command_away_(self,interaction:discord.Interaction,status:int,message:Optional[str]=None):

        command_dict = {
            0: "away",
            1: "dnd",
            2: "gaming",
            3: "idle",
            4: "listening",
            5: "offline"
            }
    
        context = await Context.from_interaction(interaction)
        command = command_dict.get(status,"away")
        await context.invoke(self.bot.get_command(command),delete_after=30,message=message)
        
    @app_commands.command(name="remindme",
        description="Never forget! Create a reminder with optional text.")
    @app_commands.describe(
        time="When to be reminded (e.g. 1h, 15mins)",
        message="What would you like to be reminded of?",
        repeat="How often to repeat this reminder? (e.g. 1h, 1 day)")
    async def app_command_remindme_(self,interaction:discord.Interaction,time:str,message:str,repeat:Optional[str]=None):
        
        context = await Context.from_interaction(interaction)
        text = f"in {time} to {message}"
        if repeat:
            text += f" every {repeat}"
        await context.invoke(self.bot.get_command("remindme"),time_and_optional_text=text)
    
    @app_commands.command(name="reminders",
        description="Show a list of all of your reminders.")
    async def app_command_reminders_(self,interaction:discord.Interaction):
        
        context = await Context.from_interaction(interaction)        
        await context.invoke(self.bot.get_command("reminder list"))

    @app_commands.command(name="timestamp",
        description="Produce a Discord timestamp. For more details, use `$help timestamp`.")
    @app_commands.describe(
        datetime="The datetime to convert. e.g. 1 October 2021 10:00AM UTC+3")
    async def app_command_timestamps_(self,interaction:discord.Interaction,datetime:str):
        
        context = await Context.from_interaction(interaction)
        await context.invoke(
            self.bot.get_command("timestamp"),
            dti=await DateConverter().convert(context,datetime)
            )    

    @app_commands.command(name="dadjoke",
        description="Gets a random dad joke.")
    async def app_command_dadjoke_(self,interaction:discord.Interaction):
        
        context = await Context.from_interaction(interaction)
        await context.invoke(
            self.bot.get_command("dadjoke")
            )        

    @app_commands.command(name="uwu",
        description="Uwu-ize the last message in this channel, or your own message.")
    @app_commands.describe(
        text="Text to uwu-ize.")
    async def app_command_uwu_(self,interaction:discord.Interaction,text:Optional[str]=None):        
        await interaction.response.defer()
        context = await Context.from_interaction(interaction)
        await context.invoke(
            self.bot.get_command("uwu"),
            text=text
            )
        await interaction.delete_original_response()
    
    @app_commands.command(name="gif",
        description="Retrieve a gif from Giphy search result.")
    @app_commands.describe(
        keywords="The keywords used to search Giphy.",
        random="Retrieve a random gif instead of the first search result.")
    @app_commands.choices(random=[
        app_commands.Choice(name="Yes",value=1),
        app_commands.Choice(name="No",value=0)])
    async def app_command_gif_(self,interaction:discord.Interaction,keywords:str,random:Optional[int]=0):

        await interaction.response.defer()
        context = await Context.from_interaction(interaction)
        
        command_dict = {
            0: "gif",
            1: "gifr"
            }
        
        await context.invoke(
            self.bot.get_command(command_dict.get(random,0)),
            keywords=keywords
            )
    
    app_command_group_dictionary = app_commands.Group(
        name="dictionary",
        description="Group for Dictionary commands."
        )
    
    @app_command_group_dictionary.command(
        name="antonym",
        description="Displays antonyms for a given word.")
    @app_commands.describe(
        word="The word to find antonyms for.")
    async def app_command_dictionary_antonym_(self,interaction:discord.Interaction,word:str):            
        context = await Context.from_interaction(interaction)
        await context.invoke(
            self.bot.get_command("antonym"),
            word=word
            )
    
    @app_command_group_dictionary.command(
        name="synonym",
        description="Displays synonyms for a given word.")
    @app_commands.describe(
        word="The word to find synonyms for.")
    async def app_command_dictionary_synonym_(self,interaction:discord.Interaction,word:str):
        context = await Context.from_interaction(interaction)
        await context.invoke(
            self.bot.get_command("synonym"),
            word=word
            )
    
    @app_command_group_dictionary.command(
        name="define",
        description="Displays definitions for a given word.")
    @app_commands.describe(
        word="The word to find definitions for.")
    async def app_command_dictionary_define_(self,interaction:discord.Interaction,word:str):
        context = await Context.from_interaction(interaction)
        await context.invoke(
            self.bot.get_command("define"),
            word=word
            )

    app_command_group_wolfram = app_commands.Group(
        name="wolfram",
        description="Ask Wolfram Alpha any question."
        )
    
    @app_command_group_wolfram.command(
        name="ask",
        description="Ask Wolfram Alpha any question.")
    @app_commands.describe(
        question="The question to ask.")
    async def app_command_dictionary_wolfram_ask_(self,interaction:discord.Interaction,question:str):
        context = await Context.from_interaction(interaction)
        await context.invoke(
            self.bot.get_command("wolframimage"),
            arguments=question
            )
        
    @app_command_group_wolfram.command(
        name="solve",
        description="Ask Wolfram Alpha any math question. Returns step by step answers.")
    @app_commands.describe(
        question="The question to ask.")
    async def app_command_dictionary_wolfram_solve_(self,interaction:discord.Interaction,question:str):
        context = await Context.from_interaction(interaction)
        await context.invoke(
            self.bot.get_command("wolframsolve"),
            query=question
            )