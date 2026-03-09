import discord
import albion_client as client
import google_sheets


async def sync_discord_nickname(member: discord.Member, albion_nickname: str):
    try:
        await member.edit(nick=albion_nickname, reason='Sync nickname after registration')
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


async def add_member_role(member: discord.Member, role_name: str = 'Member'):
    role = discord.utils.get(member.guild.roles, name=role_name)
    await member.add_roles(role, reason=f'Add {role_name} role after registration')


async def register_user(context, nickname: str, worksheet):
    target_guild_name = 'Federation'

    player_info = client.get_player_by_nickname(nickname)
    if player_info is None:
        await context.send(f"Player with nickname **{nickname}** was not found.")
        return

    discord_id = context.author.id
    player_id = player_info['Id']
    player_name = player_info['Name']
    player_guild = player_info['GuildName']

    if player_guild != target_guild_name:
        if player_guild:
            await context.send(
                f"Character **{player_name}** is in **{player_guild}**.\n"
                f"Only **{target_guild_name}** members can register."
            )
            return

        await context.send(
            f"Character **{player_name}** is not in a guild.\n"
            f"Only **{target_guild_name}** members can register."
        )
        return

    exists, conflict_field = google_sheets.registration_exists(worksheet, discord_id, player_name)
    if exists:
        if conflict_field == 'discord_id':
            await context.send(f"You are already registered with another character.")
            return

        await context.send(f"Character **{player_name}** is already registered.")
        return

    google_sheets.add_user_to_worksheet(worksheet, discord_id, player_id, player_name, silver=0)

    await sync_discord_nickname(context.author, player_name)
    await add_member_role(context.author, role_name='Fed')
    await context.send(f"**{player_name}** was registered successfully.")