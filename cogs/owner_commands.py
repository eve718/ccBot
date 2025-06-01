# cogs/owner_commands.py

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
            # await self.bot.tree.sync() # Uncomment if you want immediate sync
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
            if extension == "owner_commands":  # Prevent unloading self
                await ctx.send("Cannot unload the owner_commands cog itself.")
                logger.warning(
                    f"Owner {ctx.author.id} attempted to unload owner_commands cog."
                )
                return

            await self.bot.unload_extension(f"cogs.{extension}")
            await ctx.send(f"Cog `{extension}` unloaded successfully.")
            logger.info(f"Successfully unloaded cog: {extension}")
        except commands.ExtensionNotLoaded:
            await ctx.send(f"Cog `{extension}` is not loaded.")
            logger.warning(f"Attempted to unload not loaded cog: {extension}")
        except commands.ExtensionNotFound:
            await ctx.send(f"Cog `{extension}` not found.")
            logger.error(f"Cog not found: {extension}")
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
            # Consider syncing slash commands after reloading if new ones are added
            # await self.bot.tree.sync() # Uncomment if you want immediate sync
        except commands.ExtensionNotLoaded:
            await ctx.send(f"Cog `{extension}` is not loaded.")
            logger.warning(f"Attempted to reload not loaded cog: {extension}")
        except commands.ExtensionNotFound:
            await ctx.send(f"Cog `{extension}` not found.")
            logger.error(f"Cog not found: {extension}")
        except Exception as e:
            await ctx.send(f"Failed to reload cog `{extension}`: `{e}`")
            logger.error(f"Failed to reload cog {extension}: {e}", exc_info=True)

    @commands.command(
        name="sync", description="[Owner Only] Syncs slash commands globally."
    )
    @commands.is_owner()
    async def sync_prefix(self, ctx):
        logger.info(f"Owner {ctx.author.id} called 'sync' prefix command.")
        async with ctx.typing():  # Show typing indicator
            try:
                await self.bot.tree.sync()  # Sync all commands
                await ctx.send("Slash commands synced successfully!")
                logger.info("Slash commands synced via owner prefix command.")
            except Exception as e:
                await ctx.send(f"Failed to sync slash commands: `{e}`")
                logger.error(
                    f"Failed to sync slash commands via owner prefix command: {e}",
                    exc_info=True,
                )

    @app_commands.command(
        name="sync", description="[Owner Only] Syncs slash commands globally."
    )
    @commands.is_owner()
    async def sync_slash(self, interaction: discord.Interaction):
        logger.info(f"Owner {interaction.user.id} called 'sync' slash command.")
        await interaction.response.defer(
            ephemeral=True, thinking=True
        )  # Defer immediately with thinking
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
            logger.error(
                f"Failed to sync slash commands via owner slash command: {e}",
                exc_info=True,
            )

    @commands.command(name="shutdown", description="[Owner Only] Shuts down the bot.")
    @commands.is_owner()
    async def shutdown_prefix(self, ctx):
        logger.warning(f"Owner {ctx.author.id} initiated bot shutdown.")
        # --- Suggestion: Add a confirmation step here ---
        # Example: await ctx.send("Are you sure you want to shut down? Reply 'yes' to confirm.")
        # Then, wait for ctx.author's response.
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
        # --- Suggestion: Add a confirmation step here ---
        # Example: await interaction.response.send_message("Are you sure you want to shut down?", view=ConfirmationView(), ephemeral=True)
        # Then, handle the confirmation interaction.
        await interaction.response.send_message(
            "Shutting down the bot. Goodbye!", ephemeral=True
        )
        await self.bot.close()


async def setup(bot):
    await bot.add_cog(OwnerCommands(bot))
