# main.py

import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import logging
import datetime
import discord.utils  # Added for utcnow()

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

keep_alive()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

bot.remove_command("help")

# --- Global Constants (Still fine in main.py, or move to a config.py) ---
# These are moved to config.py and imported. No need to define them here again
# unless they are bot-specific defaults.
# CALCULATION_TIMEOUT = 15
# EXACT_CALC_THRESHOLD_BOX1 = 100
# EXACT_CALC_THRESHOLD_BOX2 = 100
# PROB_DIFFERENCE_THRESHOLD = 0.001

# Global variable for bot online time and owner display name
# bot_online_since will be an attribute of bot
# OWNER_DISPLAY_NAME will be an attribute of bot


@bot.event
async def on_ready():
    bot.bot_online_since = discord.utils.utcnow()  # Fixed: Assign to bot object
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    logger.info(
        f"Bot online since: {bot.bot_online_since.strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )

    # Set OWNER_DISPLAY_NAME from fetched owner info
    try:
        owner_user = await bot.fetch_user(int(os.getenv("OWNER_ID")))
        bot.OWNER_DISPLAY_NAME = owner_user.display_name
        logger.info(f"Owner display name set to: {bot.OWNER_DISPLAY_NAME}")
    except Exception as e:
        logger.error(f"Could not fetch owner user to set display name: {e}")
        bot.OWNER_DISPLAY_NAME = "Bot Owner"  # Fallback if fetching fails

    # Load cogs
    for cog_file in os.listdir("./cogs"):
        if cog_file.endswith(".py") and not cog_file.startswith("_"):
            try:
                await bot.load_extension(f"cogs.{cog_file[:-3]}")
                logger.info(f"Loaded cog: cogs.{cog_file[:-3]}")
            except commands.ExtensionError as e:
                logger.error(f"Failed to load cog {cog_file[:-3]}: {e}", exc_info=True)

    # Make global variables available to cogs through the bot object
    bot.CALCULATION_TIMEOUT = CALCULATION_TIMEOUT
    bot.EXACT_CALC_THRESHOLD_BOX1 = EXACT_CALC_THRESHOLD_BOX1
    bot.EXACT_CALC_THRESHOLD_BOX2 = EXACT_CALC_THRESHOLD_BOX2
    bot.PROB_DIFFERENCE_THRESHOLD = PROB_DIFFERENCE_THRESHOLD
    bot.SCIPY_AVAILABLE = SCIPY_AVAILABLE
    bot.BAG_I_DEFINITION = BAG_I_DEFINITION
    bot.BAG_II_DEFINITION = BAG_II_DEFINITION
    # bot.OWNER_DISPLAY_NAME and bot.bot_online_since are already set in on_ready

    logger.info("Bot is ready and cogs loaded.")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        # Ignore CommandNotFound errors to avoid spamming logs for invalid commands
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing arguments. Usage: `{ctx.command.usage}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(
            "Bad argument. Please check your input types (e.g., numbers for counts)."
        )
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(
            f"This command is on cooldown! Try again in `{error.retry_after:.2f}s`."
        )
    elif isinstance(error, commands.NotOwner):
        await ctx.send("You do not have permission to use this command.")
    else:
        logger.error(f"Ignoring exception in command {ctx.command}:", exc_info=True)
        await ctx.send(f"An error occurred: `{error}`")


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
    if isinstance(error, app_commands.CommandOnCooldown):
        error_message = (
            f"This command is on cooldown! Try again in `{error.retry_after:.2f}s`."
        )
        embed = discord.Embed(
            title="⏳ Cooldown",
            description=error_message,
            color=discord.Color.orange(),
        )
    elif isinstance(error, app_commands.MissingPermissions):
        error_message = "You don't have the necessary permissions to use this command."
        embed = discord.Embed(
            title="🚫 Missing Permissions",
            description=error_message,
            color=discord.Color.red(),
        )
    elif isinstance(error, app_commands.MissingRole):
        error_message = f"You need the '{error.missing_role}' role to use this command."
        embed = discord.Embed(
            title="🚫 Missing Role",
            description=error_message,
            color=discord.Color.red(),
        )
    elif isinstance(error, app_commands.BotMissingPermissions):
        error_message = f"I am missing permissions to run this command: `{', '.join(error.missing_permissions)}`."
        embed = discord.Embed(
            title="🤖 Bot Missing Permissions",
            description=error_message,
            color=discord.Color.red(),
        )
    elif isinstance(error, app_commands.CheckFailure):
        # Generic check failure, often includes is_owner()
        error_message = "You are not authorized to use this command."
        embed = discord.Embed(
            title="⛔ Authorization Failed",
            description=error_message,
            color=discord.Color.dark_red(),
        )
    elif isinstance(error, app_commands.CommandInvokeError):
        # This wraps exceptions raised in the command's code
        original_error = error.original
        logger.error(
            f"Error in application command '{interaction.command.name}': {original_error}",
            exc_info=True,
        )
        if isinstance(original_error, asyncio.TimeoutError):
            error_message = (
                "The command timed out. This might happen with complex calculations "
                "or if the bot is experiencing high load. Please try again or with simpler inputs."
            )
            embed = discord.Embed(
                title="⏰ Command Timeout",
                description=error_message,
                color=discord.Color.orange(),
            )
        elif isinstance(original_error, ValueError):
            error_message = f"Invalid input provided: `{original_error}`. Please check your arguments."
            embed = discord.Embed(
                title="❌ Invalid Input",
                description=error_message,
                color=discord.Color.red(),
            )
        else:
            error_message = (
                f"An unexpected error occurred while running this command: `{original_error}`.\n"
                "The developer has been notified."
            )
            embed = discord.Embed(
                title="💥 Error Executing Command",
                description=error_message,
                color=discord.Color.dark_red(),
            )
    else:
        logger.error(f"Unhandled application command error: {error}", exc_info=True)
        error_message = (
            f"An unhandled error occurred: `{error}`. "
            "The developer has been notified."
        )
        embed = discord.Embed(
            title="🐛 Unhandled Error",
            description=error_message,
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


# Make global variables available to cogs through the bot object
bot.CALCULATION_TIMEOUT = CALCULATION_TIMEOUT
bot.EXACT_CALC_THRESHOLD_BOX1 = EXACT_CALC_THRESHOLD_BOX1
bot.EXACT_CALC_THRESHOLD_BOX2 = EXACT_CALC_THRESHOLD_BOX2
bot.PROB_DIFFERENCE_THRESHOLD = PROB_DIFFERENCE_THRESHOLD
bot.SCIPY_AVAILABLE = SCIPY_AVAILABLE
bot.BAG_I_DEFINITION = BAG_I_DEFINITION
bot.BAG_II_DEFINITION = BAG_II_DEFINITION
# bot.OWNER_DISPLAY_NAME and bot.bot_online_since are already set in on_ready

bot.run(TOKEN)
