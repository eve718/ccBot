import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger("discord_bot")


class OwnerCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="load", description="[Owner Only] Loads a cog.")
    @commands.is_owner()
    async def load_cog(self, ctx, extension: str):
        logger.info(f"Owner {ctx.author.id} called 'load' for {extension}.")
        try:
            await self.bot.load_extension(f"cogs.{extension}")
            await ctx.send(f"Cog `{extension}` loaded successfully.")
            logger.info(f"Successfully loaded cog: {extension}")
            # Consider syncing slash commands after loading if new ones are added
            # await self.bot.tree.sync()
        except commands.ExtensionAlreadyLoaded:
            await ctx.send(f"Cog `{extension}` is already loaded.")
            logger.warning(f"Attempted to load already loaded cog: {extension}")
        except commands.ExtensionNotFound:
            await ctx.send(f"Cog `{extension}` not found.")
            logger.error(f"Cog not found: {extension}")
        except Exception as e:
            await ctx.send(f"Failed to load cog `{extension}`: `{e}`")
            logger.error(f"Failed to load cog {extension}: {e}", exc_info=True)

    @commands.command(name="unload", description="[Owner Only] Unloads a cog.")
    @commands.is_owner()
    async def unload_cog(self, ctx, extension: str):
        logger.info(f"Owner {ctx.author.id} called 'unload' for {extension}.")
        try:
            await self.bot.unload_extension(f"cogs.{extension}")
            await ctx.send(f"Cog `{extension}` unloaded successfully.")
            logger.info(f"Successfully unloaded cog: {extension}")
            # Consider syncing slash commands after unloading if some were removed
            # await self.bot.tree.sync()
        except commands.ExtensionNotLoaded:
            await ctx.send(f"Cog `{extension}` is not loaded.")
            logger.warning(f"Attempted to unload not loaded cog: {extension}")
        except Exception as e:
            await ctx.send(f"Failed to unload cog `{extension}`: `{e}`")
            logger.error(f"Failed to unload cog {extension}: {e}", exc_info=True)

    @commands.command(name="reload", description="[Owner Only] Reloads a cog.")
    @commands.is_owner()
    async def reload_cog(self, ctx, extension: str):
        logger.info(f"Owner {ctx.author.id} called 'reload' for {extension}.")
        try:
            await self.bot.reload_extension(f"cogs.{extension}")
            await ctx.send(f"Cog `{extension}` reloaded successfully.")
            logger.info(f"Successfully reloaded cog: {extension}")
            # Always sync slash commands after reload as they might have changed
            await self.bot.tree.sync()
        except commands.ExtensionNotFound:
            await ctx.send(
                f"Cog `{extension}` not found. (Perhaps it was never loaded?)"
            )
            logger.error(f"Cog not found for reload: {extension}")
        except Exception as e:
            await ctx.send(f"Failed to reload cog `{extension}`: `{e}`")
            logger.error(f"Failed to reload cog {extension}: {e}", exc_info=True)

    # You can also add slash command versions for these for convenience:
    @app_commands.command(name="load_cog", description="[Owner Only] Loads a cog.")
    @app_commands.describe(
        extension="The name of the cog to load (e.g., 'general', 'bags')"
    )
    @commands.is_owner()
    async def load_cog_slash(self, interaction: discord.Interaction, extension: str):
        logger.info(
            f"Owner {interaction.user.id} called 'load_cog' slash for {extension}."
        )
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.load_extension(f"cogs.{extension}")
            await interaction.followup.send(
                f"Cog `{extension}` loaded successfully.", ephemeral=True
            )
            logger.info(f"Successfully loaded cog (slash): {extension}")
            await self.bot.tree.sync()  # Sync after loading new commands
        except commands.ExtensionAlreadyLoaded:
            await interaction.followup.send(
                f"Cog `{extension}` is already loaded.", ephemeral=True
            )
            logger.warning(f"Attempted to load already loaded cog (slash): {extension}")
        except commands.ExtensionNotFound:
            await interaction.followup.send(
                f"Cog `{extension}` not found.", ephemeral=True
            )
            logger.error(f"Cog not found (slash): {extension}")
        except Exception as e:
            await interaction.followup.send(
                f"Failed to load cog `{extension}`: `{e}`", ephemeral=True
            )
            logger.error(f"Failed to load cog (slash) {extension}: {e}", exc_info=True)

    @app_commands.command(name="unload_cog", description="[Owner Only] Unloads a cog.")
    @app_commands.describe(
        extension="The name of the cog to unload (e.g., 'general', 'bags')"
    )
    @commands.is_owner()
    async def unload_cog_slash(self, interaction: discord.Interaction, extension: str):
        logger.info(
            f"Owner {interaction.user.id} called 'unload_cog' slash for {extension}."
        )
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.unload_extension(f"cogs.{extension}")
            await interaction.followup.send(
                f"Cog `{extension}` unloaded successfully.", ephemeral=True
            )
            logger.info(f"Successfully unloaded cog (slash): {extension}")
            await self.bot.tree.sync()  # Sync after unloading commands
        except commands.ExtensionNotLoaded:
            await interaction.followup.send(
                f"Cog `{extension}` is not loaded.", ephemeral=True
            )
            logger.warning(f"Attempted to unload not loaded cog (slash): {extension}")
        except Exception as e:
            await interaction.followup.send(
                f"Failed to unload cog `{extension}`: `{e}`", ephemeral=True
            )
            logger.error(
                f"Failed to unload cog (slash) {extension}: {e}", exc_info=True
            )

    @app_commands.command(name="reload_cog", description="[Owner Only] Reloads a cog.")
    @app_commands.describe(
        extension="The name of the cog to reload (e.g., 'general', 'bags')"
    )
    @commands.is_owner()
    async def reload_cog_slash(self, interaction: discord.Interaction, extension: str):
        logger.info(
            f"Owner {interaction.user.id} called 'reload_cog' slash for {extension}."
        )
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.reload_extension(f"cogs.{extension}")
            await interaction.followup.send(
                f"Cog `{extension}` reloaded successfully.", ephemeral=True
            )
            logger.info(f"Successfully reloaded cog (slash): {extension}")
            await self.bot.tree.sync()  # Sync after reload
        except commands.ExtensionNotFound:
            await interaction.followup.send(
                f"Cog `{extension}` not found. (Perhaps it was never loaded?)",
                ephemeral=True,
            )
            logger.error(f"Cog not found for reload (slash): {extension}")
        except Exception as e:
            await interaction.followup.send(
                f"Failed to reload cog `{extension}`: `{e}`", ephemeral=True
            )
            logger.error(
                f"Failed to reload cog (slash) {extension}: {e}", exc_info=True
            )

    @commands.command(
        name="sync", description="[Owner Only] Syncs slash commands globally."
    )
    @commands.is_owner()
    async def sync_prefix(self, ctx):
        logger.info(f"Owner {ctx.author.id} called 'sync' prefix command.")
        await ctx.send("Syncing slash commands globally. This may take a moment...")
        try:
            await self.bot.tree.sync()
            await ctx.send("Slash commands synced successfully!")
            logger.info("Slash commands synced via owner prefix command.")
        except Exception as e:
            await ctx.send(f"Failed to sync slash commands: `{e}`")
            logger.error(f"Failed to sync slash commands via owner prefix command: {e}")

    @app_commands.command(
        name="sync", description="[Owner Only] Syncs slash commands globally."
    )
    @commands.is_owner()
    async def sync_slash(self, interaction: discord.Interaction):
        logger.info(f"Owner {interaction.user.id} called 'sync' slash command.")
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.tree.sync()
            await interaction.followup.send(
                "Slash commands synced successfully!", ephemeral=True
            )
            logger.info("Slash commands synced via owner slash command.")
        except Exception as e:
            await interaction.followup.send(
                f"Failed to sync slash commands: `{e}`", ephemeral=True
            )
            logger.error(f"Failed to sync slash commands via owner slash command: {e}")

    @commands.command(name="shutdown", description="[Owner Only] Shuts down the bot.")
    @commands.is_owner()
    async def shutdown_prefix(self, ctx):
        logger.warning(f"Owner {ctx.author.id} initiated bot shutdown.")
        await ctx.send("Shutting down the bot. Goodbye!")
        await self.bot.close()

    @app_commands.command(
        name="shutdown", description="[Owner Only] Shuts down the bot."
    )
    @commands.is_owner()
    async def shutdown_slash(self, interaction: discord.Interaction):
        logger.warning(
            f"Owner {interaction.user.id} initiated bot shutdown via slash command."
        )
        await interaction.response.send_message(
            "Shutting down the bot. Goodbye!", ephemeral=True
        )
        await self.bot.close()


async def setup(bot):
    await bot.add_cog(OwnerCommands(bot))
