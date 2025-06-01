# main.py

import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import logging
import datetime

# Import all constants from your new config.py
from config import (
    CALCULATION_TIMEOUT,
    EXACT_CALC_THRESHOLD_BOX1,
    EXACT_CALC_THRESHOLD_BOX2,
    PROB_DIFFERENCE_THRESHOLD,
    BAG_I_DEFINITION,
    BAG_II_DEFINITION,
)

# Conditional import for scipy
try:
    from scipy.stats import norm

    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    print("SciPy not found. Normal approximation will not be available.")

from keep_alive import keep_alive  # Assuming this is for uptime monitoring

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
OWNER = os.getenv("OWNER_ID")  # Keep OWNER for the owner commands cog

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s:%(levelname)s:%(name)s: %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),  # Log to a file
        logging.StreamHandler(),  # Also log to console
    ],
)
logger = logging.getLogger("discord_bot")


keep_alive()  # Call your uptime function


intents = discord.Intents.default()
intents.message_content = True  # Required for prefix commands to read messages

bot = commands.Bot(command_prefix="!", intents=intents)

# Store cooldown mapping directly on the bot object
bot.prefix_cooldowns = commands.CooldownMapping.from_cooldown(
    1, 10, commands.BucketType.user
)

# --- Assign constants from config.py to bot object ---
bot.CALCULATION_TIMEOUT = CALCULATION_TIMEOUT
bot.EXACT_CALC_THRESHOLD_BOX1 = EXACT_CALC_THRESHOLD_BOX1
bot.EXACT_CALC_THRESHOLD_BOX2 = EXACT_CALC_THRESHOLD_BOX2
bot.PROB_DIFFERENCE_THRESHOLD = PROB_DIFFERENCE_THRESHOLD
bot.SCIPY_AVAILABLE = SCIPY_AVAILABLE
bot.BAG_I_DEFINITION = BAG_I_DEFINITION
bot.BAG_II_DEFINITION = BAG_II_DEFINITION
# Assign scipy.stats.norm if available
if SCIPY_AVAILABLE:
    bot.norm = norm


# Remove default help command
bot.remove_command("help")


@bot.event
async def on_ready():
    logger.info(f"Logged on as {bot.user} (ID: {bot.user.id})")
    bot.bot_online_since = (
        discord.utils.utcnow()
    )  # Store start time directly on bot object

    # Set bot owner ID and fetch name
    if OWNER:
        bot.owner_id = int(OWNER)
        try:
            owner_user = await bot.fetch_user(bot.owner_id)
            # Assign the fetched owner's display name directly to the bot object
            bot.owner_display_name = (
                owner_user.display_name
                if hasattr(owner_user, "display_name")
                else owner_user.name
            )
            logger.info(f"Fetched owner display name: {bot.owner_display_name}")
        except (ValueError, discord.NotFound, discord.HTTPException) as e:
            logger.warning(
                f"Could not fetch owner's name (ID: {OWNER}): {e}. Using default 'Bot Owner'."
            )
            bot.owner_display_name = "Bot Owner"  # Fallback if fetch fails
    else:
        logger.warning(
            "OWNER_ID not set in .env. Owner-only commands may not work correctly."
        )
        bot.owner_display_name = "Bot Owner"  # Fallback if OWNER is not set

    # Load cogs
    initial_extensions = [
        "cogs.general",
        "cogs.bags",
        "cogs.owner_commands",
    ]

    for extension in initial_extensions:
        try:
            await bot.load_extension(extension)
            logger.info(f"Loaded extension: {extension}")
        except commands.ExtensionFailed as e:
            logger.error(
                f"Failed to load extension {extension}: {e.original}", exc_info=True
            )
        except commands.ExtensionNotFound:
            logger.error(f"Extension not found: {extension}")
        except Exception as e:
            logger.error(
                f"Unknown error loading extension {extension}: {e}", exc_info=True
            )

    try:
        # Sync slash commands after cogs are loaded
        # Consider `guild=discord.Object(id=YOUR_GUILD_ID)` for faster testing
        await bot.tree.sync()
        logger.info("Slash commands synced successfully.")
    except Exception as e:
        logger.error(f"Failed to sync slash commands: {e}", exc_info=True)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        # Provide more specific feedback for command not found
        embed = discord.Embed(
            title="🤔 Command Not Found",
            description=f"The command `{ctx.message.content.split()[0]}` doesn't exist. "
            f"Please check your spelling or try `/help` or `!menu` to see available commands.",
            color=discord.Color.orange(),
        )
        await ctx.send(embed=embed)
        logger.warning(f"Command not found: {ctx.message.content} by {ctx.author.id}")
    elif isinstance(error, commands.BadArgument):
        embed = discord.Embed(
            title="❌ Invalid Argument",
            description=f"You provided an invalid argument. Please check the command's usage.\n`{error}`",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)
        logger.warning(
            f"Bad argument for command {ctx.command}: {error} by {ctx.author.id}"
        )
    elif isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title="⚠️ Missing Argument",
            description=f"You're missing a required argument: `{error.param.name}`. "
            f"Please check the command's usage.",
            color=discord.Color.orange(),
        )
        await ctx.send(embed=embed)
        logger.warning(
            f"Missing argument for command {ctx.command}: {error} by {ctx.author.id}"
        )
    elif isinstance(error, commands.CommandOnCooldown):
        embed = discord.Embed(
            title="⏳ Cooldown",
            description=f"This command is on cooldown. Please try again in `{error.retry_after:.2f}` seconds.",
            color=discord.Color.orange(),
        )
        await ctx.send(embed=embed)
        logger.warning(
            f"Command on cooldown for {ctx.author.id}: {error.retry_after:.2f}s left."
        )
    elif isinstance(error, commands.NotOwner):
        embed = discord.Embed(
            title="🚫 Permission Denied",
            description="You don't have permission to use this command. This command is restricted to the bot owner.",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)
        logger.warning(
            f"Non-owner {ctx.author.id} attempted to use owner command: {ctx.command}"
        )
    elif isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(
            title="🚫 Missing Permissions",
            description=f"You need the following permissions to use this command: `{', '.join(error.missing_permissions)}`.",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)
        logger.warning(
            f"User {ctx.author.id} missing permissions for {ctx.command}: {error.missing_permissions}"
        )
    elif isinstance(error, commands.BotMissingPermissions):
        embed = discord.Embed(
            title="🚫 Bot Missing Permissions",
            description=f"I need the following permissions to run this command: `{', '.join(error.missing_permissions)}`.",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)
        logger.error(
            f"Bot missing permissions for {ctx.command}: {error.missing_permissions}"
        )
    elif isinstance(error, commands.CommandInvokeError):
        # CommandInvokeError wraps exceptions thrown inside the command itself
        original_error = error.original
        logger.error(
            f"Error in command '{ctx.command}': {original_error}", exc_info=True
        )
        embed = discord.Embed(
            title="💥 Error Executing Command",
            description=f"An unexpected error occurred while running this command: `{original_error}`.\n"
            "The developer has been notified.",
            color=discord.Color.dark_red(),
        )
        await ctx.send(embed=embed)
    else:
        logger.error(f"Unhandled prefix command error: {error}", exc_info=True)
        embed = discord.Embed(
            title="🐛 Unhandled Error",
            description=f"An unhandled error occurred: `{error}`. The developer has been notified.",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)


@bot.event
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
    if isinstance(error, app_commands.CommandOnCooldown):
        embed = discord.Embed(
            title="⏳ Cooldown",
            description=f"This command is on cooldown. Please try again in `{error.retry_after:.2f}` seconds.",
            color=discord.Color.orange(),
        )
    elif isinstance(error, app_commands.MissingPermissions):
        embed = discord.Embed(
            title="🚫 Missing Permissions",
            description=f"You need the following permissions to use this command: `{', '.join(error.missing_permissions)}`.",
            color=discord.Color.red(),
        )
    elif isinstance(error, app_commands.BotMissingPermissions):
        embed = discord.Embed(
            title="🚫 Bot Missing Permissions",
            description=f"I need the following permissions to run this command: `{', '.join(error.missing_permissions)}`.",
            color=discord.Color.red(),
        )
    elif isinstance(error, app_commands.NotOwner):
        embed = discord.Embed(
            title="🚫 Permission Denied",
            description="You don't have permission to use this command. This command is restricted to the bot owner.",
            color=discord.Color.red(),
        )
    elif isinstance(error, app_commands.CommandInvokeError):
        original_error = error.original
        logger.error(
            f"Error in slash command '{interaction.command.name}': {original_error}",
            exc_info=True,
        )
        embed = discord.Embed(
            title="💥 Error Executing Command",
            description=f"An unexpected error occurred while running this command: `{original_error}`.\n"
            "The developer has been notified.",
            color=discord.Color.dark_red(),
        )
    else:
        logger.error(f"Unhandled application command error: {error}", exc_info=True)
        embed = discord.Embed(
            title="🐛 Unhandled Error",
            description=f"An unhandled error occurred: `{error}`. The developer has been notified.",
            color=discord.Color.red(),
        )

    # Attempt to send the error message ephemerally, handling deferral status
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            # If not deferred or already sent a message, use send_message
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.InteractionResponded:
        # This might happen if a response was sent just before the error handling
        logger.warning(
            f"Could not send ephemeral error response for {interaction.command.name} to {interaction.user.id} "
            f"because interaction was already responded to/deferred. Error: {error}"
        )
    except Exception as e:
        logger.error(
            f"Failed to send error message for {interaction.command.name} to {interaction.user.id}: {e}",
            exc_info=True,
        )


bot.run(TOKEN)
