import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

import command_handlers
import comp_builder
import guild_settings
import role_reaction
import tickets


load_dotenv()


token = os.getenv('DISCORD_TOKEN_TEST')
BOT_RESTART_MESSAGE = os.getenv('BOT_RESTART_MESSAGE')
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)
slash_commands_synced = False


async def _send_restart_notifications() -> None:
    updates_channels = guild_settings.get_all_bot_updates_channels()

    for guild_id, channel_id in updates_channels.items():
        guild = bot.get_guild(guild_id)
        if guild is None:
            continue

        channel = guild.get_channel(channel_id)
        if channel is None:
            try:
                channel = await guild.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                continue

        if not isinstance(channel, discord.TextChannel):
            continue

        me = guild.me
        if me is not None and not channel.permissions_for(me).send_messages:
            continue

        try:
            await channel.send(BOT_RESTART_MESSAGE)
        except (discord.Forbidden, discord.HTTPException):
            logging.warning("Failed to send restart message in guild %s channel %s", guild_id, channel_id)


@bot.event
async def on_ready():
    global slash_commands_synced

    if not slash_commands_synced:
        tickets.register_persistent_views(bot)
        await bot.tree.sync()
        await _send_restart_notifications()
        slash_commands_synced = True

    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('------')


@bot.command(name='create-comp')
async def create_comp_from_message(context, comp_message_id: int, source_channel_id: int = None):
    await command_handlers.handle_create_comp_from_message(bot, context, comp_message_id, source_channel_id)


@bot.command(name='get-participants')
async def get_battle_participants(context, battle_ids: str):
    await command_handlers.handle_get_battle_participants(context, battle_ids)


@bot.tree.command(name='register', description='Register your Albion character')
async def register_slash(interaction: discord.Interaction, character_name: str):
    await command_handlers.handle_register_slash(interaction, character_name)


@bot.tree.command(name='bot-setup', description='Open setup modal for this server')
async def bot_setup_slash(interaction: discord.Interaction):
    await command_handlers.handle_bot_setup_slash(interaction)


@bot.tree.command(name='bot-link-google-sheet', description='Link Google credentials JSON to this server')
async def bot_link_google_sheet_slash(interaction: discord.Interaction):
    await command_handlers.handle_bot_link_google_sheet_slash(interaction)


@bot.tree.command(name='tickets-setup', description='Configure ticket panels for guild applications')
async def tickets_setup_slash(interaction: discord.Interaction):
    await tickets.handle_tickets_setup(bot, interaction)


@bot.tree.command(name='role-reaction-setup', description='Set up role reaction panels for this server')
async def role_reaction_setup_slash(interaction: discord.Interaction):
    await role_reaction.handle_role_reaction_setup(interaction)


@bot.tree.command(name='update-config', description='Update bot configuration values')
async def update_config_slash(interaction: discord.Interaction):
    await command_handlers.handle_update_config_slash(interaction)


@bot.tree.command(name='lootsplit', description='Distribute lootsplit and save history rows')
async def lootsplit_slash(
    interaction: discord.Interaction,
    battle_ids: str,
    officer: str,
    content_name: str,
    caller: str,
    participants: str,
    lootsplit_amount: str,
):
    await command_handlers.handle_lootsplit_slash(
        interaction,
        battle_ids,
        officer,
        content_name,
        caller,
        participants,
        lootsplit_amount,
    )


@bot.tree.command(name='bot-remove', description='Remove this server configuration from the bot')
async def bot_remove_slash(interaction: discord.Interaction):
    await command_handlers.handle_bot_remove_slash(interaction)


@bot.command(name='bal')
async def get_balance(context, nickname: str = None):
    await command_handlers.handle_get_balance(context, nickname)


@bot.tree.command(name='bal-add', description='Add silver balance to a player')
async def bal_add_slash(
    interaction: discord.Interaction,
    member: discord.Member,
    add_silver: str,
    reason: str = "Manual",
):
    await command_handlers.handle_bal_add_slash(interaction, member, add_silver, reason)


@bot.tree.command(name='bal-remove', description='Remove silver balance from a player')
async def bal_remove_slash(
    interaction: discord.Interaction,
    member: discord.Member,
    remove_silver: str,
    reason: str = "Payout",
):
    await command_handlers.handle_bal_remove_slash(interaction, member, remove_silver, reason)


bot.add_listener(comp_builder.on_message_in_thread, 'on_message')


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent) -> None:
    await role_reaction.handle_raw_reaction_add(bot, payload)


@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent) -> None:
    await role_reaction.handle_raw_reaction_remove(bot, payload)


@bot.command()
async def clear(context):
    await command_handlers.handle_clear(context)


bot.run(token, log_handler=handler, log_level=logging.DEBUG)
