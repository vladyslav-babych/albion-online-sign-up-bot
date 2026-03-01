import discord
import re

# Sign up and sign out logic
def has_manage_messages_permission(context):
    return context.channel.permissions_for(context.author).manage_messages

def is_party_thread(channel: discord.abc.Messageable) -> bool:
	return isinstance(channel, discord.Thread) and channel.name.startswith("Party ") and channel.name.endswith(" thread")

async def get_starter_message(channel: discord.Thread):
	return channel.starter_message

def parse_roles(comp_text: str) -> list:
	return comp_text.split('\n') if comp_text else []

def find_role_index_by_number(roles: list, number: int):
	for idx, role in enumerate(roles):
		if role.startswith(f"{number}. "):
			return idx
	return None

def find_first_mention(role_line: str):
	mention = re.search(r'(<@!?[0-9]+>)', role_line)
	return mention.group(1) if mention else None

async def update_comp_text(original_comp_text, roles):
	await original_comp_text.edit(content='\n'.join(roles))

async def officer_forced_signout(message, roles, original_comp_text, role_number: int):
	member = message.author
	if not has_manage_messages_permission(message):
		return
	idx = find_role_index_by_number(roles, role_number)
	if idx is None:
		return
	mention = find_first_mention(roles[idx])
	if not mention:
		return
	role_name = roles[idx].split(f"{role_number}. ")[1].split(f" {mention}")[0].strip()
	roles[idx] = roles[idx].replace(f" {mention}", "")
	await update_comp_text(original_comp_text, roles)
	await message.reply(f"{mention} was signed out from **{role_name}**")

async def sign_up_user(message, roles, original_comp_text, role_number: int, member=None):
	idx = find_role_index_by_number(roles, role_number)
	if idx is None:
		return
	if member is None:
		member = message.author

	# Check if the role is already taken
	is_role_talen = find_first_mention(roles[idx])
	if is_role_talen:
		if is_role_talen == member.mention:
			return
		await message.reply("This role is already taken.")
		return
	
	role_name = roles[idx].split(f"{role_number}. ")[1].split(f" {member.mention}")[0].strip()
	roles[idx] = roles[idx] + f" {member.mention}"
	await update_comp_text(original_comp_text, roles)
	await message.reply(f"{member.mention} was signed up as **{role_name}**")

async def sign_out_self(message, roles, original_comp_text):
	for idx, role in enumerate(roles):
		if message.author.mention in role:
			role_name = role.split('. ')[1].split(f" {message.author.mention}")[0].strip()
			roles[idx] = role.replace(f" {message.author.mention}", "")
			await update_comp_text(original_comp_text, roles)
			await message.reply(f"{message.author.mention} was signed out from **{role_name}**")
			return

async def on_message_in_thread(message):
	if message.author.bot:
		return
	if not is_party_thread(message.channel):
		return

	user_text = message.content.strip()
	original_comp_text = await get_starter_message(message.channel)
	if original_comp_text is None:
		return
	roles = parse_roles(original_comp_text.content)

	# Officer forced sign-out
	if user_text.startswith('-') and user_text[1:].isdigit():
		await officer_forced_signout(message, roles, original_comp_text, int(user_text[1:]))
		return

	# Sign up by number
	if user_text.isdigit():
		await sign_up_user(message, roles, original_comp_text, int(user_text))
		return

	# Officer forced sign-up with mention
	if has_manage_messages_permission(message):
		match = re.search(r'(<@!?[0-9]+>)\s+(\d+)', user_text)
		if match:
			mention = match.group(1)
			role_number = int(match.group(2))
			user_id = int(mention[2:-1].lstrip('!'))
			member = message.guild.get_member(user_id)
			if member:
				await sign_up_user(message, roles, original_comp_text, role_number, member)
				return

	# Sign out self
	if user_text == '-':
		await sign_out_self(message, roles, original_comp_text)
		return