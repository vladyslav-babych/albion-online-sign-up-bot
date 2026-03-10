import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import comp_builder
import google_sheets
import registration
import balance

load_dotenv()

token = os.getenv('DISCORD_TOKEN')
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)
worksheet = google_sheets.get_worksheet()


async def is_admin(member):
    return any(role.permissions.administrator for role in member.roles)


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


@bot.command(name='register')
async def register(context, nickname: str):
    await registration.register_user(context, nickname, worksheet)


@bot.command(name='bal')
async def get_balance(context, nickname: str = None):
    await balance.get_balance(context, worksheet, nickname)


@bot.command(name='bal-add')
async def add_balance(context, nickname: str, amount: str):
    if not await is_admin(context.author):
        await context.reply("You don't have permission to use this command.")
        return
    try:
        amount_int = int(amount)
    except ValueError:
        await context.reply("Amount must be an integer.")
        return

    if amount_int < 0:
        await context.reply("Amount must be >= 0.")
        return

    await balance.add_balance(context, worksheet, nickname, amount_int)


@bot.command(name='bal-remove')
async def remove_balance(context, nickname: str, amount: str):
    if not await is_admin(context.author):
        await context.reply("You don't have permission to use this command.")
        return
    try:
        amount_int = int(amount)
    except ValueError:
        await context.reply("Amount must be an integer.")
        return

    if amount_int < 0:
        await context.reply("Amount must be >= 0.")
        return

    await balance.remove_balance(context, worksheet, nickname, amount_int)


bot.add_listener(comp_builder.on_message_in_thread, 'on_message')


@bot.command()
async def clear(context):
    if not await is_admin(context.author):
        await context.reply("You don't have permission to use this command.")
        return
    
    await context.channel.purge()


bot.run(token, log_handler=handler, log_level=logging.DEBUG)
