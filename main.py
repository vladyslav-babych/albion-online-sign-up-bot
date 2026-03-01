import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import comp_builder

load_dotenv()

token = os.getenv('DISCORD_TOKEN')

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('------')

@bot.command(name='create-comp')
async def create_comp_from_message(context, comp_message_id: int, source_channel_id: int = None):
    await context.message.delete()

    source_channel = bot.get_channel(source_channel_id)
    if source_channel_id is None:
        await context.send("You must provide a **Channel ID** as a second parameter.")
        return
    
    # fetch the source message by id
    try:
        source_message = await source_channel.fetch_message(comp_message_id)
    except Exception:
        await context.send("Could not fetch comp message. Make sure that **Channel ID** was inserted correctly.")
        return

    # parse parties from the message content and create posts+threads
    parties = source_message.content.strip().split('\n\n')
    for party in parties:
        m = await context.send(party)
        thread_name = party.split('\n')[0] + " thread"
        await m.create_thread(name=thread_name, auto_archive_duration=60, slowmode_delay=10)

bot.add_listener(comp_builder.on_message_in_thread, 'on_message')

@bot.command()
async def clear(context):
    if not comp_builder.has_manage_messages_permission(context.message):
        return
    
    await context.channel.purge()

bot.run(token, log_handler=handler, log_level=logging.DEBUG)