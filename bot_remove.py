import discord

import globals
import google_sheet_credentials_store
import guild_settings


class BotRemoveConfirmView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id

    async def _ensure_owner(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Only the admin who started this action can use these controls.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="YES, remove", style=discord.ButtonStyle.danger)
    async def confirm_remove(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._ensure_owner(interaction):
            return

        if interaction.guild is None:
            await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
            return

        removed_guild_name = guild_settings.remove_target_guild(interaction.guild.id)
        if not removed_guild_name:
            await interaction.response.edit_message(
                embed=discord.Embed(title="Bot Remove", description="This server is not set up."),
                view=None,
            )
            return

        google_sheet_credentials_store.remove_google_sheet_credentials(interaction.guild.id)

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Bot Remove",
                description=(
                    f"Setup removed. Discord server ID **{interaction.guild.id}** and "
                    f"guild **{removed_guild_name}** were deleted."
                ),
            ),
            view=None,
        )

    @discord.ui.button(label="NO, keep", style=discord.ButtonStyle.success)
    async def cancel_remove(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._ensure_owner(interaction):
            return
        await interaction.response.edit_message(
            embed=discord.Embed(title="Bot Remove", description="Removal cancelled. Configuration was kept."),
            view=None,
        )


async def handle_bot_remove_slash(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
        return

    if not isinstance(interaction.user, discord.Member) or not await globals.is_admin(interaction.user):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    configured_guild_name = guild_settings.get_target_guild(interaction.guild.id)
    if not configured_guild_name:
        await interaction.response.send_message("This server is not set up.", ephemeral=True)
        return

    await interaction.response.send_message(
        embed=discord.Embed(
            title="Bot Remove",
            description=(
                f" ## :warning: Warning: this will delete setup for this server (guild {configured_guild_name})\n"
                "Choose an action below."
            ),
        ),
        view=BotRemoveConfirmView(interaction.user.id),
    )
