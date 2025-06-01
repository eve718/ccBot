import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import logging
import datetime

# Conditional import for scipy (remains in main as it's a global dependency check)
try:
    from scipy.stats import norm

    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    print("SciPy not found. Normal approximation will not be available.")

from keep_alive import keep_alive  # Assuming this is for replit/uptime

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
OWNER = os.getenv("OWNER_ID")  # Keep OWNER for the owner commands cog

keep_alive()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

bot.remove_command("help")

# --- Global Constants (Still fine in main.py, or move to a config.py) ---
CALCULATION_TIMEOUT = 15
EXACT_CALC_THRESHOLD_BOX1 = 100
EXACT_CALC_THRESHOLD_BOX2 = 100
PROB_DIFFERENCE_THRESHOLD = 0.001

# Global variable for bot online time and owner display name
bot_online_since = None
OWNER_DISPLAY_NAME = "Bot Owner"  # Default, will be updated on_ready

# Configure logging (can also be in a separate logging_config.py)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()],
)
logger = logging.getLogger("discord_bot")

# --- Global Bag Definitions (Castle Clash Data) ---
# It's okay to keep these in main.py if they are truly global and constant,
# or you could move them to a separate 'constants.py' or 'config.py' file
# and import them into your cogs. For now, let's assume they are imported
# into cogs that need them.
BAG_I_DEFINITION = [
    (1, 0.36),
    (2, 0.37),
    (5, 0.15),
    (10, 0.07),
    (20, 0.03),
    (30, 0.02),
]
BAG_II_DEFINITION = [
    (10, 0.46),
    (15, 0.27),
    (20, 0.17),
    (50, 0.05),
    (80, 0.03),
    (100, 0.02),
]


# --- Bot Events (Reduced in main.py) ---
@bot.event
async def on_ready():
    global OWNER_DISPLAY_NAME
    global bot_online_since
    logger.info(f"Logged on as {bot.user}!")
    bot_online_since = discord.utils.utcnow()

    # Set bot owner ID and fetch name
    if OWNER:
        bot.owner_id = int(OWNER)  # Set owner_id for is_owner() check
        try:
            owner_user = await bot.fetch_user(bot.owner_id)
            OWNER_DISPLAY_NAME = (
                owner_user.display_name
                if hasattr(owner_user, "display_name")
                else owner_user.name
            )
            logger.info(f"Fetched owner display name: {OWNER_DISPLAY_NAME}")
        except (ValueError, discord.NotFound, discord.HTTPException) as e:
            logger.warning(
                f"Could not fetch owner's name: {e}. Using default 'Bot Owner'."
            )
            OWNER_DISPLAY_NAME = "Bot Owner"
    else:
        logger.warning(
            "OWNER_ID not set in .env. Owner-only commands may not work correctly."
        )

    # Load cogs here
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
            logger.error(f"Failed to load extension {extension}: {e.original}")
        except commands.ExtensionNotFound:
            logger.error(f"Extension not found: {extension}")
        except Exception as e:
            logger.error(f"Unknown error loading extension {extension}: {e}")

    try:
        # Sync slash commands after cogs are loaded
        await bot.tree.sync()
        logger.info("Slash commands synced successfully.")
    except Exception as e:
        logger.error(f"Failed to sync slash commands: {e}")


@bot.event
async def on_guild_join(guild):
    logger.info(f"Joined guild: {guild.name} ({guild.id})")
    embed = discord.Embed(
        title="🎉 Thanks for inviting me!",
        description="Hello! I'm your friendly Soulstone Probability Calculator bot. I can help you determine the chances of getting specific soulstone totals from your bag draws.",
        color=discord.Color.blue(),
    )
    if bot.user and bot.user.display_avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)

    embed.add_field(
        name="🚀 Getting Started",
        value="You can use either **slash commands** (preferred) or **prefix commands**.",
        inline=False,
    )
    embed.add_field(
        name="✨ Main Command: `/bags`",
        value=(
            "Calculates the probability of getting at least a target amount of soulstones.\n"
            "**Usage:** `/bags bag1:<number> bag2:<number> ss:<target_sum>`\n"
            "**Example:** `/bags 10 5 200`\n"
            "*(This is the recommended way to use the bot!)*"
        ),
        inline=False,
    )
    embed.add_field(
        name="💡 Prefix Command (Alternative): `!bags`",
        value=(
            "**Usage:** `!bags <number of bag I> <number of bag II> <soulstones goal>`\n"
            "**Example:** `!bags 10 5 200`"
        ),
        inline=False,
    )
    embed.add_field(
        name="❓ Need More Help?",
        value="Type `/menu` or `!menu` for a list of all commands.",
        inline=False,
    )
    # Use the global OWNER_DISPLAY_NAME here
    embed.set_footer(text=f"Bot developed by {OWNER_DISPLAY_NAME}")

    if guild.system_channel:
        await guild.system_channel.send(embed=embed)
    else:
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                await channel.send(embed=embed)
                break


# Global slash command error handler (stays in main.py)
@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
    # This handler can often stay in main.py, or you can have specific ones in cogs
    # for cog-specific errors and let this catch the rest.
    if isinstance(error, app_commands.CommandOnCooldown):
        embed = discord.Embed(
            title="⚠️ Cooldown Active",
            description=f"This command is on cooldown. Please try again after `{error.retry_after:.2f}` seconds.",
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info(
            f"User {interaction.user.id} hit cooldown for slash command '{interaction.command.name}'."
        )
    elif isinstance(error, app_commands.CommandInvokeError):
        original_error = error.original
        logger.error(
            f"Command '{interaction.command.name}' raised an exception: {original_error}",
            exc_info=True,
        )
        error_message = (
            f"An unexpected error occurred: `{original_error}`. "
            "The developer has been notified."
        )
        embed = discord.Embed(
            title="💥 Error Executing Command",
            description=error_message,
            color=discord.Color.dark_red(),
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
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
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


# Make global variables available to cogs through the bot object
bot.CALCULATION_TIMEOUT = CALCULATION_TIMEOUT
bot.EXACT_CALC_THRESHOLD_BOX1 = EXACT_CALC_THRESHOLD_BOX1
bot.EXACT_CALC_THRESHOLD_BOX2 = EXACT_CALC_THRESHOLD_BOX2
bot.PROB_DIFFERENCE_THRESHOLD = PROB_DIFFERENCE_THRESHOLD
bot.SCIPY_AVAILABLE = SCIPY_AVAILABLE
bot.BAG_I_DEFINITION = BAG_I_DEFINITION
bot.BAG_II_DEFINITION = BAG_II_DEFINITION
bot.OWNER_DISPLAY_NAME = OWNER_DISPLAY_NAME  # This will be updated on_ready
bot.bot_online_since = bot_online_since  # This will be updated on_ready
bot.prefix_cooldowns = commands.CooldownMapping.from_cooldown(
    1, 10, commands.BucketType.user
)


bot.run(TOKEN)
