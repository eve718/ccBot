import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import collections
import random
from collections import Counter
import math
import numpy as np
import logging

try:
    from scipy.stats import norm

    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    print("SciPy not found. Normal approximation will not be available.")

from keep_alive import keep_alive

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
OWNER = os.getenv("OWNER_ID")

keep_alive()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

bot.remove_command("help")

CALCULATION_TIMEOUT = 15
EXACT_CALC_THRESHOLD_BOX1 = 100
EXACT_CALC_THRESHOLD_BOX2 = 100
PROB_DIFFERENCE_THRESHOLD = 0.001

prefix_cooldowns = commands.CooldownMapping.from_cooldown(
    1, 10, commands.BucketType.user
)

bot_online_since = None


# Global variable to store the owner's display name
OWNER_DISPLAY_NAME = "Bot Owner"

# --- Global Bag Definitions (Castle Clash Data) ---
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()],
)
logger = logging.getLogger("discord_bot")

# --- Command Menu Definition ---
COMMAND_MENU = {
    "bags": {
        "description": "Calculates soulstone probabilities from bag draws.",
        "usage_prefix": "`!bags <bag I count> <bag II count> <target soulstones>`",
        "usage_slash": "`/bags bag1:<count> bag2:<count> ss:<target>`",
        "emoji": "💎",
        "has_args": True,  # Requires arguments
    },
    "baginfo": {
        "description": "Displays information about Bag I and Bag II contents and their average values.",
        "usage_prefix": "`!baginfo`",
        "usage_slash": "`/baginfo`",
        "emoji": "🛍️",
        "has_args": False,  # No arguments
    },
    "ping": {
        "description": "Checks the bot's latency.",
        "usage_prefix": "`!ping`",
        "usage_slash": "`/ping`",
        "emoji": "🏓",
        "has_args": False,  # No arguments
    },
    "info": {
        "description": "Displays general information about the bot.",
        "usage_prefix": "`!info`",
        "usage_slash": "`/info`",
        "emoji": "ℹ️",
        "has_args": False,  # No arguments
    },
    "menu": {
        "description": "Displays this command menu.",
        "usage_prefix": "`!menu`",
        "usage_slash": "`/menu`",
        "emoji": "📚",
        "has_args": False,  # No arguments
    },
}


async def calculate_exact_probabilities(box_def, num_draws):
    current_probabilities = {0: 1.0}
    for _ in range(num_draws):
        await asyncio.sleep(0)
        next_probabilities = collections.defaultdict(float)
        for prev_sum, prev_prob in current_probabilities.items():
            for value, prob_of_value in box_def:
                new_sum = prev_sum + value
                new_prob = prev_prob * prob_of_value
                next_probabilities[new_sum] += new_prob
        current_probabilities = next_probabilities
    return current_probabilities


async def run_exact_calculation(box1_def, box2_def, draws_box1, draws_box2, target_sum):
    box1_sums_probs = await calculate_exact_probabilities(box1_def, draws_box1)
    box2_sums_probs = await calculate_exact_probabilities(box2_def, draws_box2)

    combined_sums_probs = collections.defaultdict(float)
    for sum1, prob1 in box1_sums_probs.items():
        await asyncio.sleep(0)
        for sum2, prob2 in box2_sums_probs.items():
            combined_sums_probs[sum1 + sum2] += prob1 * prob2

    prob_at_least_target = sum(
        prob for s, prob in combined_sums_probs.items() if s >= target_sum
    )
    prob_exact_target = combined_sums_probs.get(target_sum, 0.0)

    sorted_sums = sorted(
        combined_sums_probs.items(), key=lambda item: item[1], reverse=True
    )
    top_3_sums_with_probs = [(s, p) for s, p in sorted_sums[:3]]
    return (prob_at_least_target * 100, top_3_sums_with_probs, prob_exact_target * 100)


def simulate_single_bag_draws(box_def, num_draws):
    if not box_def or num_draws == 0:
        return 0
    values = np.array([val for val, prob in box_def])
    probabilities = np.array([prob for val, prob in box_def])
    probabilities /= probabilities.sum()
    total_sum = np.random.choice(values, size=num_draws, p=probabilities).sum()
    return int(total_sum)


async def run_monte_carlo_simulation(
    box1_def, box2_def, draws_box1, draws_box2, target_sum, num_simulations
):
    successful_outcomes = 0
    combined_sums_for_stats = []

    batch_size = max(1, num_simulations // 1000)

    for i in range(num_simulations):
        if i % batch_size == 0:
            await asyncio.sleep(0)
        sum1 = simulate_single_bag_draws(box1_def, draws_box1)
        sum2 = simulate_single_bag_draws(box2_def, draws_box2)
        total_sum = sum1 + sum2
        combined_sums_for_stats.append(total_sum)
        if total_sum >= target_sum:
            successful_outcomes += 1

    prob_at_least_target = (successful_outcomes / num_simulations) * 100
    sum_counts = Counter(combined_sums_for_stats)
    top_3_raw = sum_counts.most_common(3)
    top_3_sums_with_probs = [(s, count / num_simulations) for s, count in top_3_raw]
    return prob_at_least_target, top_3_sums_with_probs


def get_bag_stats(box_def):
    expected_value = sum(val * prob for val, prob in box_def)
    total_prob = sum(prob for val, prob in box_def)
    if total_prob != 0:
        expected_value /= total_prob
    else:
        expected_value = 0

    variance = sum((val - expected_value) ** 2 * prob for val, prob in box_def)
    if total_prob != 0:
        variance /= total_prob
    else:
        variance = 0
    return expected_value, variance


def run_normal_approximation(box1_def, box2_def, draws_box1, draws_box2, target_sum):
    mean1, var1 = get_bag_stats(box1_def)
    mean2, var2 = get_bag_stats(box2_def)
    total_mean = (mean1 * draws_box1) + (mean2 * draws_box2)
    total_variance = (var1 * draws_box1) + (var2 * draws_box2)
    total_std_dev = math.sqrt(total_variance)

    if total_std_dev == 0:
        if target_sum <= total_mean:
            return (
                100.0,
                [],
            )
        else:
            return 0.0, []

    z_score = (target_sum - 0.5 - total_mean) / total_std_dev
    prob_at_least_target = (1 - norm.cdf(z_score)) * 100
    return prob_at_least_target, []


async def async_parser(num_draws_box1, num_draws_box2, target_sum_value):
    box1_def_normalized = [
        (val, prob / sum(p for v, p in BAG_I_DEFINITION))
        for val, prob in BAG_I_DEFINITION
    ]
    box2_def_normalized = [
        (val, prob / sum(p for v, p in BAG_II_DEFINITION))
        for val, prob in BAG_II_DEFINITION
    ]

    if (
        num_draws_box1 <= EXACT_CALC_THRESHOLD_BOX1
        and num_draws_box2 <= EXACT_CALC_THRESHOLD_BOX2
    ):
        result_data = await run_exact_calculation(
            box1_def_normalized,
            box2_def_normalized,
            num_draws_box1,
            num_draws_box2,
            target_sum_value,
        )
        method = "exact"
    elif SCIPY_AVAILABLE:
        result_data = run_normal_approximation(
            box1_def_normalized,
            box2_def_normalized,
            num_draws_box1,
            num_draws_box2,
            target_sum_value,
        )
        result_data = (
            result_data[0],
            result_data[1],
            0.0,
        )  # Normal approx doesn't have exact prob
        method = "normal_approx"
    else:
        raise ValueError(
            "Inputs are too large for exact calculation, and the SciPy library is not available for approximation. Please contact the bot owner if you believe this is an error or need SciPy installed."
        )
    return result_data, method


# --- Bot Events ---
@bot.event
async def on_ready():
    global OWNER_DISPLAY_NAME
    global bot_online_since  # Declare it global here
    logger.info(f"Logged on as {bot.user}!")
    bot_online_since = discord.utils.utcnow()  # Store the current UTC time

    try:
        await bot.tree.sync()
        logger.info("Slash commands synced successfully.")
    except Exception as e:
        logger.error(f"Failed to sync slash commands: {e}")

    try:
        owner_user = await bot.fetch_user(int(OWNER))
        OWNER_DISPLAY_NAME = (
            owner_user.display_name
            if hasattr(owner_user, "display_name")
            else owner_user.name
        )
        logger.info(f"Fetched owner display name: {OWNER_DISPLAY_NAME}")
    except (ValueError, discord.NotFound, discord.HTTPException) as e:
        logger.warning(f"Could not fetch owner's name: {e}. Using default 'Bot Owner'.")
        OWNER_DISPLAY_NAME = "Bot Owner"


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
            "**Example:** `/bags bag1:10 bag2:5 ss:200`\n"
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
    embed.set_footer(text=f"Bot developed by {OWNER_DISPLAY_NAME}")

    if guild.system_channel:
        await guild.system_channel.send(embed=embed)
    else:
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                await channel.send(embed=embed)
                break


# --- Global slash command error handler ---
@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
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
    elif isinstance(error, commands.MissingRequiredArgument):
        logger.warning(
            f"Missing argument for slash command: {error.param.name} in command {interaction.command.name} by {interaction.user.id}."
        )
        embed = discord.Embed(
            title="❌ Missing Argument",
            description=f"You're missing a required argument: `{error.param.display_name or error.param.name}`.",
            color=discord.Color.red(),
        )
        embed.set_footer(text="Please provide all necessary arguments.")
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
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


async def create_info_embed(bot_instance: commands.Bot):
    """Creates the embed for the /info command."""
    embed = discord.Embed(
        title="ℹ️ Bot Information",
        description="I am a Discord bot designed to calculate soulstone probabilities for Castle Clash bag draws.",
        color=discord.Color.blurple(),
    )
    if bot_instance.user and bot_instance.user.display_avatar:
        embed.set_thumbnail(url=bot_instance.user.display_avatar.url)

    embed.add_field(name="Developer", value=OWNER_DISPLAY_NAME, inline=True)
    embed.add_field(name="Library", value="discord.py", inline=True)
    embed.add_field(
        name="Source Code (If Available)",
        value="[GitHub](https://github.com/your-repo-link)",  # Make sure this is your actual link!
        inline=False,
    )
    online_time_formatted = "Unknown"
    if bot_online_since:
        try:
            online_time_formatted = discord.utils.format_dt(bot_online_since, "R")
        except Exception as e:
            logger.error(f"Error formatting bot_online_since: {e}")
            online_time_formatted = "Error formatting time"
    # Note: We're keeping the full footer for now, as the test for simplifying it was not applied.
    embed.set_footer(text=f"Bot Version: 1.0.0 | Online since: {online_time_formatted}")
    return embed


async def create_ping_embed(bot_instance: commands.Bot):
    """Creates the embed for the /ping command."""
    latency_ms = round(bot_instance.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latency: {latency_ms}ms",
        color=discord.Color.green(),
    )
    return embed


async def create_baginfo_embed(
    bot_instance: commands.Bot,
):  # Added bot_instance to pass for thumbnail
    """Creates the embed for the /baginfo command, restoring original content and improving row separation."""
    bag1_exp, _ = get_bag_stats(BAG_I_DEFINITION)
    bag2_exp, _ = get_bag_stats(BAG_II_DEFINITION)

    embed = discord.Embed(
        title="🛍️ Bag Information",
        description="Details about the soulstone contents, average values, and calculation thresholds for Bag I and Bag II.",
        color=discord.Color.gold(),
    )
    # Re-adding bot thumbnail for consistency with other embed creators
    if bot_instance.user and bot_instance.user.display_avatar:
        embed.set_thumbnail(url=bot_instance.user.display_avatar.url)

    # --- Bag I Details ---
    bag1_contents_text = ""
    for val, prob in BAG_I_DEFINITION:
        bag1_contents_text += f"`{val}` Soulstones: `{prob*100:.2f}%`\n"
    embed.add_field(
        name="Bag I Contents & Averages",
        value=(
            f"**Individual Probabilities:**\n{bag1_contents_text}"
            f"**Average Expected per draw:** `{bag1_exp:.2f}` Soulstones\n"
            f"**Exact Calculation Threshold:** Up to `{EXACT_CALC_THRESHOLD_BOX1}` draws"
        ),
        inline=False,  # Ensures this field takes its own row
    )

    # --- Bag II Details ---
    bag2_contents_text = ""
    for val, prob in BAG_II_DEFINITION:
        bag2_contents_text += f"`{val}` Soulstones: `{prob*100:.2f}%`\n"
    embed.add_field(
        name="Bag II Contents & Averages",
        value=(
            f"**Individual Probabilities:**\n{bag2_contents_text}"
            f"**Average Expected per draw:** `{bag2_exp:.2f}` Soulstones\n"
            f"**Exact Calculation Threshold:** Up to `{EXACT_CALC_THRESHOLD_BOX2}` draws"
        ),
        inline=False,  # Ensures this field takes its own row
    )

    # --- General Accuracy Note (retained from my previous suggestion) ---
    embed.add_field(
        name="General Accuracy Note",
        value="Normal approximation accuracy improves with more draws. For precise results on smaller draws, use values within the exact calculation thresholds.",
        inline=False,
    )

    embed.set_footer(text=f"Information provided by Castle Clash")
    return embed


async def create_welcome_embed():
    """Creates a default welcome/main menu embed."""
    embed = discord.Embed(
        title="Welcome to rngBot!",
        description="Select a command from the menu below to learn more or perform an action.",
        color=discord.Color.blue(),
    )
    # You can add more general info here if you like
    return embed


# --- Embed Generation Function to ensure identical embeds ---
async def create_bags_embed(
    bag1, bag2, ss, prob_at_least_target, top_sums, method_used, prob_exact_target=None
):
    embed = discord.Embed(
        title="📊 Soulstone Probability Results",
        description="Here are the calculation results for your bag draws:",
        color=(
            discord.Color.green() if prob_at_least_target > 0 else discord.Color.red()
        ),
    )
    if bot.user and bot.user.display_avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)

    embed.add_field(
        name="🔢 Input Parameters",
        value=f"**Bag I Draws:** `{bag1}`\n**Bag II Draws:** `{bag2}`\n**Target Soulstones (at least):** `{ss}`",
        inline=False,
    )

    box1_exp_val, _ = get_bag_stats(BAG_I_DEFINITION)
    box2_exp_val, _ = get_bag_stats(BAG_II_DEFINITION)

    embed.add_field(
        name="📈 Expected Average",
        value=f"Your average expected soulstones are: `{box1_exp_val*bag1 + box2_exp_val*bag2:.2f}`",
        inline=False,
    )

    calculation_method_note = ""
    if method_used == "normal_approx":
        calculation_method_note = (
            "\n*(Result is an approximation based on Normal Distribution)*"
        )
    elif method_used == "exact":
        calculation_method_note = "\n*(Result is exact)*"

    prob_result_text = f"**Probability of Soulstones being at least `{ss}`:** `{prob_at_least_target:.4f}%`"
    if method_used == "exact" and prob_exact_target is not None:
        prob_result_text += f"\n**Probability of Soulstones being exactly `{ss}`:** `{prob_exact_target:.4f}%`"

    prob_result_text += f"{calculation_method_note}\n"
    prob_result_text += f"*Calculation Method: {method_used.replace('_', ' ').title()}*"

    embed.add_field(
        name="✅ Probability Result",
        value=prob_result_text,
        inline=False,
    )

    if method_used == "exact":
        top_sums_text = ""
        padded_top_sums = top_sums + [(0, 0.0)] * (3 - len(top_sums))

        if (
            len(top_sums) >= 3
            and abs(padded_top_sums[0][1] - padded_top_sums[2][1])
            < PROB_DIFFERENCE_THRESHOLD
        ):
            top_sums_text = f"Top sums are too close in probability (difference between 1st and 3rd < `{PROB_DIFFERENCE_THRESHOLD*100:.2f}%`) to be meaningfully distinct."
        elif len(top_sums) < 1 or (len(top_sums) >= 1 and padded_top_sums[0][1] == 0.0):
            top_sums_text = "No prominent sums found or calculated."
        else:
            for i, (s, p) in enumerate(padded_top_sums[:3]):
                if p > 0:
                    top_sums_text += (
                        f" `{i+1}`. Total Soulstones: `{s}`, Chance: `{p*100:.4f}%`\n"
                    )
            if not top_sums_text:
                top_sums_text = "No prominent sums found or calculated."

        embed.add_field(
            name="🥇🥈🥉 Top 3 Most Likely Total Soulstones Counts",
            value=top_sums_text.strip(),
            inline=False,
        )

    embed.set_footer(
        text=f"Calculated by {bot.user.name} • {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')} | Made by {OWNER_DISPLAY_NAME}"
    )
    return embed


# --- New: Interactive Menu View ---
# Modify your existing CommandMenuView class:


class CommandMenuView(discord.ui.View):
    def __init__(self, bot_instance: commands.Bot, timeout=300):
        super().__init__(timeout=timeout)
        self.bot_instance = bot_instance
        self.message = (
            None  # IMPORTANT: Initialize message to None for later assignment
        )

    # Define each button using the @discord.ui.button decorator.
    # Each button will have its own callback method that then calls the shared _handle_button_click.
    @discord.ui.button(
        label="Info", custom_id="menu_button_info", style=discord.ButtonStyle.primary
    )
    async def info_button_callback(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Call the central handler for all button logic
        await self._handle_button_click(interaction, button)

    @discord.ui.button(
        label="Bag Info",
        custom_id="menu_button_baginfo",
        style=discord.ButtonStyle.primary,
    )
    async def baginfo_button_callback(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Call the central handler for all button logic
        await self._handle_button_click(interaction, button)

    @discord.ui.button(
        label="Bags (Input Args)",
        custom_id="menu_button_bags",
        style=discord.ButtonStyle.secondary,
    )
    async def bags_button_callback(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Call the central handler for all button logic
        await self._handle_button_click(interaction, button)

    @discord.ui.button(
        label="Ping", custom_id="menu_button_ping", style=discord.ButtonStyle.primary
    )
    async def ping_button_callback(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Call the central handler for all button logic
        await self._handle_button_click(interaction, button)

    # This is the new central handler for all button click logic.
    # It receives 'interaction' and 'button' correctly from the decorated methods above.
    async def _handle_button_click(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        try:
            # Always defer the interaction as the very first step in the try block
            await interaction.response.defer(ephemeral=False, thinking=True)

            command_name = button.custom_id.replace("menu_button_", "")
            logger.info(f"User {interaction.user.id} clicked '{command_name}' button.")

            content_embed = None
            current_view = self

            if command_name == "info":
                content_embed = await create_info_embed(self.bot_instance)
            elif command_name == "ping":
                content_embed = await create_ping_embed(self.bot_instance)
            elif command_name == "baginfo":
                content_embed = await create_baginfo_embed(self.bot_instance)
            elif command_name == "bags":
                content_embed = discord.Embed(
                    title=f"Usage for /{command_name}",
                    description=f"The `/{command_name}` command requires arguments. Please type `/{command_name}` and follow the prompts.",
                    color=discord.Color.yellow(),
                )
            else:
                content_embed = discord.Embed(
                    title="Command Not Found",
                    description="This command is not recognized or not yet implemented in the interactive menu.",
                    color=discord.Color.red(),
                )

            # --- CRITICAL CHANGE HERE ---
            # Instead of interaction.edit_original_response, use self.message.edit()
            # This explicitly targets the message object that was sent when the menu was first opened.
            if self.message:  # Ensure self.message has been set
                await self.message.edit(embed=content_embed, view=current_view)
                logger.info(f"Edited menu embed for command '{command_name}'.")
            else:
                # Fallback if self.message somehow isn't available (shouldn't happen if setup is correct)
                logger.warning(
                    f"Failed to edit menu embed for '{command_name}': self.message was not set."
                )
                await interaction.followup.send(embed=content_embed, ephemeral=True)

            #    Since self.message.edit() already updated the main message, we just need to tell
            #    Discord that the *deferred button interaction* is complete.
            #    Sending a very short-lived ephemeral followup message is a common way to do this.
            await interaction.followup.send(
                "...", ephemeral=True, delete_after=0.1
            )  # Sends a tiny, invisible message that immediately disappears
            logger.info(
                f"Dismissed 'Bot is thinking...' for '{command_name}' button click."
            )

        except Exception as e:
            logger.error(
                f"UNCAUGHT ERROR during menu button click (custom_id: {button.custom_id}): {e}",
                exc_info=True,
            )

            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "An unexpected error occurred while processing your request. The bot owner has been notified.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "An unexpected error occurred after starting your request. The bot owner has been notified.",
                    ephemeral=True,
                )

    async def on_timeout(self):
        # This method remains unchanged
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
                logger.info("Menu view timed out and buttons disabled.")
            except discord.NotFound:
                logger.warning(
                    "Tried to edit timed-out menu message, but it was not found."
                )
            except Exception as e:
                logger.error(f"Error editing timed-out menu message: {e}")
        else:
            logger.warning(
                "Menu view timed out but message attribute was not set, cannot disable buttons."
            )


# --- Embed Generation Function for Menu ---
async def create_menu_embed():
    embed = discord.Embed(
        title="📚 Bot Commands Menu",
        description="Click a button below to learn more about a command or run it directly (if it has no arguments).",
        color=discord.Color.purple(),
    )
    if bot.user and bot.user.display_avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)

    for cmd_name, cmd_details in COMMAND_MENU.items():
        description = cmd_details.get("description", "No description available.")
        usage_prefix = cmd_details.get("usage_prefix", "N/A")
        usage_slash = cmd_details.get("usage_slash", "N/A")
        emoji = cmd_details.get("emoji", "")

        embed.add_field(
            name=f"{emoji} {cmd_name.capitalize()} Command",
            value=(
                f"{description}\n"
                f"**Prefix Usage:** {usage_prefix}\n"
                f"**Slash Usage:** {usage_slash}"
            ),
            inline=False,
        )

    embed.set_footer(text=f"Interact below! | Made by {OWNER_DISPLAY_NAME}")
    return embed


# --- Prefix Commands ---
@bot.command(name="bags", aliases=["bag", "sscalc", "calculate"])
async def bags_prefix(ctx, bag1: int, bag2: int, ss: int):
    logger.info(
        f"Prefix command 'bags' called by {ctx.author} ({ctx.author.id}) with args: bag1={bag1}, bag2={bag2}, ss={ss}"
    )
    bucket = prefix_cooldowns.get_bucket(ctx.message)
    retry_after = bucket.update_rate_limit()
    if retry_after:
        embed = discord.Embed(
            title="⚠️ Cooldown Active",
            description=f"This command is on cooldown. Please try again after `{retry_after:.2f}` seconds.",
            color=discord.Color.orange(),
        )
        await ctx.send(embed=embed)
        logger.info(f"User {ctx.author.id} hit cooldown for 'bags' prefix command.")
        return

    if bag1 < 0 or bag2 < 0 or ss < 0:
        bucket.reset()
        embed = discord.Embed(
            title="❌ Invalid Input",
            description="Numbers of bags and soulstones goal must be non-negative integers.",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)
        logger.warning(
            f"Invalid input from {ctx.author.id} for 'bags' prefix command: Negative numbers."
        )
        return

    calculation_method_display = "Calculating..."
    if bag1 <= EXACT_CALC_THRESHOLD_BOX1 and bag2 <= EXACT_CALC_THRESHOLD_BOX2:
        calculation_method_display = "Calculating (Exact Method)..."
    elif SCIPY_AVAILABLE:
        calculation_method_display = "Calculating (Normal Approximation)..."
    else:
        calculation_method_display = "Inputs too large; approximation library (SciPy) not available. Calculation may fail."

    initial_message = await ctx.send(
        f"{calculation_method_display} This might take a moment. Please wait..."
    )

    try:
        result_data, method_used = await asyncio.wait_for(
            async_parser(bag1, bag2, ss), timeout=CALCULATION_TIMEOUT
        )
        prob_at_least_target, top_sums, prob_exact_target = result_data
        logger.info(
            f"Calculation for {ctx.author.id} successful (method: {method_used})."
        )
    except asyncio.TimeoutError:
        bucket.reset()
        embed = discord.Embed(
            title="⏰ Calculation Timeout",
            description=f"The calculation took too long (more than `{CALCULATION_TIMEOUT}` seconds) and was cancelled. Please try with smaller bag numbers.",
            color=discord.Color.orange(),
        )
        await initial_message.edit(content=None, embed=embed)
        logger.warning(
            f"Calculation for {ctx.author.id} timed out for 'bags' prefix command."
        )
        return
    except ValueError as e:
        bucket.reset()
        embed = discord.Embed(
            title="❌ Calculation Error",
            description=f"Input error: {e}",
            color=discord.Color.red(),
        )
        await initial_message.edit(content=None, embed=embed)
        logger.error(f"Value error for {ctx.author.id} in 'bags' prefix command: {e}")
        return
    except Exception as e:
        bucket.reset()
        embed = discord.Embed(
            title="⚠️ Unexpected Error",
            description=f"An unexpected error occurred during calculation: `{e}`",
            color=discord.Color.red(),
        )
        await initial_message.edit(content=None, embed=embed)
        logger.exception(
            f"Unexpected error for {ctx.author.id} in 'bags' prefix command."
        )
        return

    final_embed = await create_bags_embed(
        bag1,
        bag2,
        ss,
        prob_at_least_target,
        top_sums,
        method_used,
        prob_exact_target,
    )
    await initial_message.edit(content=None, embed=final_embed)


@bags_prefix.error
async def bags_prefix_error(ctx, error):
    logger.error(f"Error in 'bags' prefix command by {ctx.author.id}: {error}")
    if isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title="❌ Missing Arguments",
            description="You're missing some information! Please use the command like this:",
            color=discord.Color.red(),
        )
        embed.add_field(
            name="Usage:",
            value="`!bags <number of bags I> <number of bags II> <soulstones goal>`\n"
            "Example: `!bags 10 5 200`",
            inline=False,
        )
        await ctx.send(embed=embed)
    elif isinstance(error, commands.BadArgument):
        embed = discord.Embed(
            title="❌ Invalid Input Type",
            description="Please ensure bag numbers and soulstone goal are valid **integers**.",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="⚠️ Error",
            description=f"An unexpected error occurred: `{error}`",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)


# --- Slash Commands ---
@bot.tree.command(name="bags", description="Calculates soulstone probabilities.")
@app_commands.describe(
    bag1="Number of Bag I draws",
    bag2="Number of Bag II draws",
    ss="Target soulstones (at least)",
)
@app_commands.checks.cooldown(
    1, 10.0, key=lambda i: (i.guild_id, i.user.id)
)  # Per user, per guild cooldown
async def bags_slash(interaction: discord.Interaction, bag1: int, bag2: int, ss: int):
    logger.info(
        f"Slash command 'bags' called by {interaction.user} ({interaction.user.id}) with args: bag1={bag1}, bag2={bag2}, ss={ss}"
    )

    if bag1 < 0 or bag2 < 0 or ss < 0:
        embed = discord.Embed(
            title="❌ Invalid Input",
            description="Numbers of bags and soulstones goal must be non-negative integers.",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.warning(
            f"Invalid input from {interaction.user.id} for 'bags' slash command: Negative numbers."
        )
        return

    calculation_method_display = "Calculating..."
    if bag1 <= EXACT_CALC_THRESHOLD_BOX1 and bag2 <= EXACT_CALC_THRESHOLD_BOX2:
        calculation_method_display = "Calculating (Exact Method)..."
    elif SCIPY_AVAILABLE:
        calculation_method_display = "Calculating (Normal Approximation)..."
    else:
        calculation_method_display = "Inputs too large; approximation library (SciPy) not available. Calculation may fail."

    # Defer the response immediately to avoid interaction timeout
    await interaction.response.send_message(
        f"{calculation_method_display} This might take a moment. Please wait...",
        ephemeral=False,
    )

    try:
        result_data, method_used = await asyncio.wait_for(
            async_parser(bag1, bag2, ss), timeout=CALCULATION_TIMEOUT
        )
        prob_at_least_target, top_sums, prob_exact_target = result_data
        logger.info(
            f"Calculation for {interaction.user.id} successful (method: {method_used})."
        )
    except asyncio.TimeoutError:
        embed = discord.Embed(
            title="⏰ Calculation Timeout",
            description=f"The calculation took too long (more than `{CALCULATION_TIMEOUT}` seconds) and was cancelled. Please try with smaller bag numbers.",
            color=discord.Color.orange(),
        )
        await interaction.followup.send(content=None, embed=embed, ephemeral=False)
        logger.warning(
            f"Calculation for {interaction.user.id} timed out for 'bags' slash command."
        )
        return
    except ValueError as e:
        embed = discord.Embed(
            title="❌ Calculation Error",
            description=f"Input error: {e}",
            color=discord.Color.red(),
        )
        await interaction.followup.send(content=None, embed=embed, ephemeral=False)
        logger.error(
            f"Value error for {interaction.user.id} in 'bags' slash command: {e}"
        )
        return
    except Exception as e:
        embed = discord.Embed(
            title="⚠️ Unexpected Error",
            description=f"An unexpected error occurred during calculation: `{e}`",
            color=discord.Color.red(),
        )
        await interaction.followup.send(content=None, embed=embed, ephemeral=False)
        logger.exception(
            f"Unexpected error for {interaction.user.id} in 'bags' slash command."
        )
        return

    final_embed = await create_bags_embed(
        bag1,
        bag2,
        ss,
        prob_at_least_target,
        top_sums,
        method_used,
        prob_exact_target,
    )
    await interaction.followup.send(content=None, embed=final_embed)


# --- Commands (Prefix & Slash) - Continued from previous sections ---
@bot.command(name="ping", description="Checks the bot's latency.")
async def ping_prefix(ctx):
    logger.info(f"Prefix command 'ping' called by {ctx.author} ({ctx.author.id}).")
    async with ctx.typing():
        embed = await create_ping_embed(bot)  # Use the new helper function
        await ctx.send(embed=embed)
        logger.info(f"Sent ping response to {ctx.author.id}.")


@bot.tree.command(name="ping", description="Checks the bot's latency.")
async def ping_slash(interaction: discord.Interaction):
    logger.info(
        f"Slash command 'ping' called by {interaction.user} ({interaction.user.id})."
    )
    # Defer if not already responded to
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=False, thinking=True)

    embed = await create_ping_embed(bot)  # Use the new helper function

    # Always use followup.send
    await interaction.followup.send(embed=embed)
    logger.info(f"Sent ping response to {interaction.user.id}.")


@bot.command(name="info", description="Displays general information about the bot.")
async def info_prefix(ctx):
    logger.info(f"Prefix command 'info' called by {ctx.author} ({ctx.author.id}).")
    async with ctx.typing():
        embed = await create_info_embed(bot)  # Use the new helper function
        await ctx.send(embed=embed)
        logger.info(f"Sent info response to {ctx.author.id}.")


@bot.tree.command(
    name="info", description="Displays general information about the bot."
)
async def info_slash(interaction: discord.Interaction):
    logger.info(
        f"Slash command 'info' called by {interaction.user} ({interaction.user.id})."
    )
    # Defer if not already responded to (e.g., if called directly, not via button)
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=False, thinking=True)

    embed = await create_info_embed(bot)  # Use the new helper function

    # Always use followup.send for the actual message
    await interaction.followup.send(embed=embed)
    logger.info(f"Sent info response to {interaction.user.id}.")


@bot.command(
    name="baginfo",
    aliases=["bagdetails"],
    description="Displays information about Bag I and Bag II contents and their average values.",
)
async def baginfo_prefix(ctx):
    logger.info(f"Prefix command 'baginfo' called by {ctx.author} ({ctx.author.id}).")
    async with ctx.typing():
        embed = await create_baginfo_embed(bot)  # Use the new helper function
        await ctx.send(embed=embed)
        logger.info(f"Sent baginfo response to {ctx.author.id}.")


@bot.tree.command(
    name="baginfo", description="Displays information about Bag I and Bag II."
)
async def baginfo_slash(interaction: discord.Interaction):
    logger.info(
        f"Slash command 'baginfo' called by {interaction.user} ({interaction.user.id})."
    )
    # Defer if not already responded to
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=False, thinking=True)

    embed = await create_baginfo_embed(bot)  # Use the new helper function

    # Always use followup.send
    await interaction.followup.send(embed=embed)
    logger.info(f"Sent baginfo response to {interaction.user.id}.")


@bot.command(name="menu", description="Displays a list of available commands.")
async def menu_prefix(ctx):
    logger.info(f"Prefix command 'menu' called by {ctx.author} ({ctx.author.id}).")
    async with ctx.typing():
        initial_embed = await create_welcome_embed()  # Use the new welcome embed helper
        view = CommandMenuView(bot_instance=bot)
        # Store the message sent by the bot for the view to edit later
        message = await ctx.send(embed=initial_embed, view=view)
        view.message = message  # Pass the message object to the view for editing
        logger.info(f"Sent menu response to {ctx.author.id}.")


@bot.tree.command(name="menu", description="Displays a list of available commands.")
async def menu_slash(interaction: discord.Interaction):
    logger.info(
        f"Slash command 'menu' called by {interaction.user} ({interaction.user.id})."
    )
    # Defer if not already responded to
    if not interaction.response.is_done():
        await interaction.response.defer(
            ephemeral=False, thinking=True
        )  # Keep ephemeral=False for menu

    # Initial embed for the menu (e.g., a welcome message)
    initial_embed = await create_welcome_embed()  # Use the new welcome embed helper
    view = CommandMenuView(bot_instance=bot)

    # This line is crucial for the view to know which message to edit and timeout
    message = await interaction.followup.send(embed=initial_embed, view=view)
    view.message = message
    logger.info(f"Sent menu response to {interaction.user.id}.")


# --- Owner Only Commands ---
@bot.command(name="sync", description="[Owner Only] Syncs slash commands globally.")
@commands.is_owner()
async def sync_prefix(ctx):
    logger.info(f"Owner {ctx.author.id} called 'sync' prefix command.")
    await ctx.send("Syncing slash commands globally. This may take a moment...")
    try:
        await bot.tree.sync()
        await ctx.send("Slash commands synced successfully!")
        logger.info("Slash commands synced via owner prefix command.")
    except Exception as e:
        await ctx.send(f"Failed to sync slash commands: `{e}`")
        logger.error(f"Failed to sync slash commands via owner prefix command: {e}")


@bot.tree.command(
    name="sync", description="[Owner Only] Syncs slash commands globally."
)
@commands.is_owner()
async def sync_slash(interaction: discord.Interaction):
    logger.info(f"Owner {interaction.user.id} called 'sync' slash command.")
    await interaction.response.defer(ephemeral=True)  # Defer immediately
    try:
        await bot.tree.sync()
        await interaction.followup.send(
            "Slash commands synced successfully!", ephemeral=True
        )
        logger.info("Slash commands synced via owner slash command.")
    except Exception as e:
        await interaction.followup.send(
            f"Failed to sync slash commands: `{e}`", ephemeral=True
        )
        logger.error(f"Failed to sync slash commands via owner slash command: {e}")


@bot.command(name="shutdown", description="[Owner Only] Shuts down the bot.")
@commands.is_owner()
async def shutdown_prefix(ctx):
    logger.warning(f"Owner {ctx.author.id} initiated bot shutdown.")
    await ctx.send("Shutting down the bot. Goodbye!")
    await bot.close()


@bot.tree.command(name="shutdown", description="[Owner Only] Shuts down the bot.")
@commands.is_owner()
async def shutdown_slash(interaction: discord.Interaction):
    logger.warning(
        f"Owner {interaction.user.id} initiated bot shutdown via slash command."
    )
    await interaction.response.send_message(
        "Shutting down the bot. Goodbye!", ephemeral=True
    )
    await bot.close()


bot.run(TOKEN)
