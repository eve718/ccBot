import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import collections
import random  # This import is not used in the current version, can be removed if not planning to use it.
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

bot.remove_command("help")  # Keep this line to remove default help, we'll make our own

CALCULATION_TIMEOUT = 15
EXACT_CALC_THRESHOLD_BOX1 = 100
EXACT_CALC_THRESHOLD_BOX2 = 100
PROB_DIFFERENCE_THRESHOLD = 0.001

prefix_cooldowns = commands.CooldownMapping.from_cooldown(
    1, 10, commands.BucketType.user
)

# Global variable to store the owner's display name
OWNER_DISPLAY_NAME = "Bot Owner"  # Default value in case fetching fails

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
    sorted_sums = sorted(
        combined_sums_probs.items(), key=lambda item: item[1], reverse=True
    )
    top_3_sums_with_probs = [(s, p) for s, p in sorted_sums[:3]]
    return (prob_at_least_target * 100, top_3_sums_with_probs)


def simulate_single_bag_draws(box_def, num_draws):
    if not box_def or num_draws == 0:
        return 0
    values = np.array([val for val, prob in box_def])
    probabilities = np.array([prob for val, prob in box_def])
    probabilities /= probabilities.sum()  # Ensure probabilities sum to 1
    total_sum = np.random.choice(values, size=num_draws, p=probabilities).sum()
    return int(total_sum)


async def run_monte_carlo_simulation(  # Not currently used, but kept for future use if needed
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
    # Re-normalize to avoid issues if initial probabilities don't sum to exactly 1.0
    total_prob = sum(prob for val, prob in box_def)
    if total_prob != 0:
        expected_value /= total_prob
    else:  # Handle case where total_prob is 0 to prevent division by zero
        expected_value = 0

    variance = sum((val - expected_value) ** 2 * prob for val, prob in box_def)
    if total_prob != 0:
        variance /= total_prob  # Also normalize variance
    else:
        variance = 0  # Handle case where total_prob is 0
    return expected_value, variance


# --- Re-added run_normal_approximation ---
def run_normal_approximation(box1_def, box2_def, draws_box1, draws_box2, target_sum):
    mean1, var1 = get_bag_stats(box1_def)
    mean2, var2 = get_bag_stats(box2_def)
    total_mean = (mean1 * draws_box1) + (mean2 * draws_box2)
    total_variance = (var1 * draws_box1) + (var2 * draws_box2)
    total_std_dev = math.sqrt(total_variance)

    if total_std_dev == 0:  # Avoid division by zero for constant sums
        if target_sum <= total_mean:
            return (
                100.0,
                [],
            )  # If target is less than or equal to the fixed sum, prob is 100%
        else:
            return 0.0, []  # Otherwise, prob is 0%

    z_score = (
        target_sum - 0.5 - total_mean
    ) / total_std_dev  # Apply continuity correction
    prob_at_least_target = (1 - norm.cdf(z_score)) * 100
    return prob_at_least_target, []


async def async_parser(num_draws_box1, num_draws_box2, target_sum_value):
    # Use global definitions
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
    logger.info(f"Logged on as {bot.user}!")
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
        value="Type `/help` or `!help` for detailed command information and tips, or `/info` for general bot info.",
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


# --- Embed Generation Function to ensure identical embeds ---
async def create_bags_embed(
    bag1, bag2, ss, prob_at_least_target, top_sums, method_used
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

    # Use global definitions for expected values
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

    embed.add_field(
        name="✅ Probability Result",
        value=(
            f"**Probability of Soulstones being at least `{ss}`:** `{prob_at_least_target:.4f}%`"
            f"{calculation_method_note}\n"
            f"*Calculation Method: {method_used.replace('_', ' ').title()}*"
        ),
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


# --- Prefix Commands ---
@bot.command(name="bags", aliases=["bag", "sscalc", "calculate"])  # Added aliases
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
        bucket.reset()  # Reset cooldown if input is invalid
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
        (prob_at_least_target, top_sums), method_used = await asyncio.wait_for(
            async_parser(bag1, bag2, ss), timeout=CALCULATION_TIMEOUT
        )
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
        )  # Use exception for full traceback
        return

    final_embed = await create_bags_embed(
        bag1, bag2, ss, prob_at_least_target, top_sums, method_used
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


# --- New Commands ---


# Ping Command
@bot.command(name="ping", description="Checks the bot's latency.")
async def ping_prefix(ctx):
    logger.info(f"Prefix command 'ping' called by {ctx.author} ({ctx.author.id}).")
    latency_ms = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Bot latency: `{latency_ms}ms`",
        color=discord.Color.blue(),
    )
    await ctx.send(embed=embed)


# Info Command
@bot.command(name="info", description="Shows general information about the bot.")
async def info_prefix(ctx):
    logger.info(f"Prefix command 'info' called by {ctx.author} ({ctx.author.id}).")
    embed = discord.Embed(
        title="ℹ️ Soulstone Calculator Bot Info",
        description="I'm a Discord bot designed to calculate soulstone probabilities from two types of bags.",
        color=discord.Color.purple(),
    )
    if bot.user and bot.user.display_avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)

    embed.add_field(
        name="🌐 Version", value="1.0.0 (Enhanced)", inline=True
    )  # You can update your version
    embed.add_field(name="🛠️ Developer", value=OWNER_DISPLAY_NAME, inline=True)
    embed.add_field(
        name="📅 Created On",
        value=f"<t:{int(bot.user.created_at.timestamp())}:D>",
        inline=True,
    )
    embed.add_field(
        name="🔗 Invite Me",
        value="[Click Here](https://discord.com/oauth2/authorize?client_id=1376302750056579112&permissions=8&integration_type=0&scope=bot)",  # REPLACE with your bot's invite link
        inline=False,
    )
    embed.add_field(
        name="⚙️ Calculation Methods",
        value=(
            f"• **Exact:** For up to {EXACT_CALC_THRESHOLD_BOX1} Bag I and {EXACT_CALC_THRESHOLD_BOX2} Bag II draws.\n"
            f"• **Normal Approximation:** For larger draws (requires SciPy, currently {'Available' if SCIPY_AVAILABLE else 'Not Available'})."
        ),
        inline=False,
    )
    embed.set_footer(text=f"Powered by Discord.py | Bot ID: {bot.user.id}")
    await ctx.send(embed=embed)


# Bag Info Command
@bot.command(
    name="baginfo",
    description="Shows the definitions and expected values of Bag I and Bag II.",
)
async def baginfo_prefix(ctx):
    logger.info(f"Prefix command 'baginfo' called by {ctx.author} ({ctx.author.id}).")

    bag1_exp_val, _ = get_bag_stats(BAG_I_DEFINITION)
    bag2_exp_val, _ = get_bag_stats(BAG_II_DEFINITION)

    embed = discord.Embed(
        title="🛍️ Soulstone Bag Definitions (Castle Clash)",
        description="Here are the contents and probabilities for each soulstone bag from Castle Clash:",
        color=discord.Color.gold(),
    )
    if bot.user and bot.user.display_avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)

    # Bag I
    bag1_text = ""
    for val, prob in BAG_I_DEFINITION:
        bag1_text += f"`{val}` Soulstones: `{prob*100:.2f}%`\n"
    bag1_text += f"**Expected Value per Draw:** `{bag1_exp_val:.2f}`"
    embed.add_field(
        name="Bag I", value=bag1_text, inline=False
    )  # Changed title to "Bag I"

    # Bag II
    bag2_text = ""
    for val, prob in BAG_II_DEFINITION:
        bag2_text += f"`{val}` Soulstones: `{prob*100:.2f}%`\n"
    bag2_text += f"**Expected Value per Draw:** `{bag2_exp_val:.2f}`"
    embed.add_field(
        name="Bag II", value=bag2_text, inline=False
    )  # Changed title to "Bag II"

    embed.set_footer(text=f"Data provided by Castle Clash")
    await ctx.send(embed=embed)


# --- Help Commands ---
@bot.command(name="help")
async def help_command_prefix(ctx):
    logger.info(f"Prefix command 'help' called by {ctx.author} ({ctx.author.id}).")
    embed = discord.Embed(
        title="📚 Soulstone Calculator Help",
        description="Here's how to use me to calculate your soulstone probabilities:",
        color=discord.Color.blue(),
    )
    if bot.user and bot.user.display_avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)

    embed.add_field(
        name="💎 Main Command: `/bags` or `!bags`",
        value="Calculates the probability of obtaining at least a target amount of soulstones from two types of bags.",
        inline=False,
    )
    embed.add_field(
        name="Usage for `/bags` (Slash Command):",
        value="`/bags bag1:<number> bag2:<number> ss:<target_sum>`\n"
        "Example: `/bags bag1:10 bag2:5 ss:200`\n"
        "*(This is the recommended way to use the bot!)*",
        inline=False,
    )
    embed.add_field(
        name="Usage for `!bags` (Prefix Command):",
        value="`!bags <number of bag I> <number of bag II> <soulstones goal>`\n"
        "Example: `!bags 10 5 200`",
        inline=False,
    )
    embed.add_field(
        name="✨ Key Features:",
        value=(
            "• Automatically selects the best calculation method (exact for smaller inputs, Normal Approximation for larger).\n"
            "• Provides the average expected soulstones.\n"
            "• Displays the top 3 most likely sums for exact calculations (if distinct enough).\n"
            "• Cooldown of `10 seconds` per user to prevent spam.\n"
            "• Use `/baginfo` or `!baginfo` to see bag contents.\n"
            "• Use `/info` or `!info` for general bot information."
        ),
        inline=False,
    )
    embed.set_footer(
        text=f"Bot made by {OWNER_DISPLAY_NAME} | Use /help for slash command version"
    )
    await ctx.send(embed=embed)


# --- Slash Commands ---
@bot.tree.command(
    name="bags",
    description=f"Calculates the chance to obtain at least [ss] soulstones from [bag1] bags I and [bag2] bags II.",
)
@app_commands.describe(
    bag1="Number of Bag I draws",
    bag2="Number of Bag II draws",
    ss="Target Soulstones (at least)",
)
@app_commands.checks.cooldown(1, 10, key=lambda i: i.user.id)
async def bags_slash(interaction: discord.Interaction, bag1: int, bag2: int, ss: int):
    logger.info(
        f"Slash command 'bags' called by {interaction.user} ({interaction.user.id}) with args: bag1={bag1}, bag2={bag2}, ss={ss}"
    )
    await interaction.response.defer(
        thinking=True, ephemeral=True
    )  # Defer as ephemeral initially

    if bag1 < 0 or bag2 < 0 or ss < 0:
        embed = discord.Embed(
            title="❌ Invalid Input",
            description="Numbers of bags and soulstones goal must be non-negative integers.",
            color=discord.Color.red(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)  # Ephemeral
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

    await interaction.followup.send(
        f"{calculation_method_display} Please wait...", ephemeral=True  # Ephemeral
    )

    try:
        (prob_at_least_target, top_sums), method_used = await asyncio.wait_for(
            async_parser(bag1, bag2, ss), timeout=CALCULATION_TIMEOUT
        )
        logger.info(
            f"Calculation for {interaction.user.id} successful (method: {method_used})."
        )
    except asyncio.TimeoutError:
        embed = discord.Embed(
            title="⏰ Calculation Timeout",
            description=f"The calculation took too long (more than `{CALCULATION_TIMEOUT}` seconds) and was cancelled. Please try with smaller bag numbers.",
            color=discord.Color.orange(),
        )
        await interaction.followup.send(
            embed=embed, ephemeral=False
        )  # Not ephemeral, as this is a core error.
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
        await interaction.followup.send(
            embed=embed, ephemeral=False
        )  # Not ephemeral, as this is a core error.
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
        await interaction.followup.send(
            embed=embed, ephemeral=False
        )  # Not ephemeral, as this is a core error.
        logger.exception(
            f"Unexpected error for {interaction.user.id} in 'bags' slash command."
        )  # Use exception for full traceback
        return

    final_embed = await create_bags_embed(
        bag1, bag2, ss, prob_at_least_target, top_sums, method_used
    )
    await interaction.followup.send(
        embed=final_embed, ephemeral=False
    )  # Final result should be public


@bags_slash.error
async def bags_slash_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
    logger.error(f"Error in 'bags' slash command by {interaction.user.id}: {error}")
    if isinstance(error, app_commands.CommandOnCooldown):
        embed = discord.Embed(
            title="⚠️ Cooldown Active",
            description=f"This command is on cooldown for you. Please try again after `{error.retry_after:.2f}` seconds.",
            color=discord.Color.orange(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
    elif isinstance(error, app_commands.BadArgument):
        embed = discord.Embed(
            title="❌ Invalid Input Type",
            description="Invalid input. Please ensure bag numbers and soulstone goal are valid **integers**.",
            color=discord.Color.red(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        embed = discord.Embed(
            title="⚠️ Error",
            description=f"An unexpected error occurred with the slash command: `{error}`",
            color=discord.Color.red(),
        )
        await interaction.followup.send(
            embed=embed, ephemeral=True
        )  # Keep generic errors ephemeral


# --- New Slash Commands ---


# Ping Slash Command
@bot.tree.command(name="ping", description="Checks the bot's latency.")
async def ping_slash(interaction: discord.Interaction):
    logger.info(
        f"Slash command 'ping' called by {interaction.user} ({interaction.user.id})."
    )
    latency_ms = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Bot latency: `{latency_ms}ms`",
        color=discord.Color.blue(),
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# Info Slash Command
@bot.tree.command(name="info", description="Shows general information about the bot.")
async def info_slash(interaction: discord.Interaction):
    logger.info(
        f"Slash command 'info' called by {interaction.user} ({interaction.user.id})."
    )
    embed = discord.Embed(
        title="ℹ️ Soulstone Calculator Bot Info",
        description="I'm a Discord bot designed to calculate soulstone probabilities from two types of bags.",
        color=discord.Color.purple(),
    )
    if bot.user and bot.user.display_avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)

    embed.add_field(name="🌐 Version", value="1.0.0 (Enhanced)", inline=True)
    embed.add_field(name="🛠️ Developer", value=OWNER_DISPLAY_NAME, inline=True)
    embed.add_field(
        name="📅 Created On",
        value=f"<t:{int(bot.user.created_at.timestamp())}:D>",
        inline=True,
    )
    embed.add_field(
        name="🔗 Invite Me",
        value="[Click Here](https://discord.com/api/oauth2/authorize?client_id=YOUR_BOT_CLIENT_ID&permissions=YOUR_PERMISSIONS&scope=bot%20applications.commands)",  # REPLACE with your bot's invite link
        inline=False,
    )
    embed.add_field(
        name="⚙️ Calculation Methods",
        value=(
            f"• **Exact:** For up to {EXACT_CALC_THRESHOLD_BOX1} Bag I and {EXACT_CALC_THRESHOLD_BOX2} Bag II draws.\n"
            f"• **Normal Approximation:** For larger draws (requires SciPy, currently {'Available' if SCIPY_AVAILABLE else 'Not Available'})."
        ),
        inline=False,
    )
    embed.set_footer(text=f"Powered by Discord.py | Bot ID: {bot.user.id}")
    await interaction.response.send_message(embed=embed, ephemeral=False)


# Bag Info Slash Command
@bot.tree.command(
    name="baginfo",
    description="Shows the definitions and expected values of Bag I and Bag II.",
)
async def baginfo_slash(interaction: discord.Interaction):
    logger.info(
        f"Slash command 'baginfo' called by {interaction.user} ({interaction.user.id})."
    )

    bag1_exp_val, _ = get_bag_stats(BAG_I_DEFINITION)
    bag2_exp_val, _ = get_bag_stats(BAG_II_DEFINITION)

    embed = discord.Embed(
        title="🛍️ Soulstone Bag Definitions (Castle Clash)",
        description="Here are the contents and probabilities for each soulstone bag from Castle Clash:",
        color=discord.Color.gold(),
    )
    if bot.user and bot.user.display_avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)

    # Bag I
    bag1_text = ""
    for val, prob in BAG_I_DEFINITION:
        bag1_text += f"`{val}` Soulstones: `{prob*100:.2f}%`\n"
    bag1_text += f"**Expected Value per Draw:** `{bag1_exp_val:.2f}`"
    embed.add_field(name="Bag I", value=bag1_text, inline=False)

    # Bag II
    bag2_text = ""
    for val, prob in BAG_II_DEFINITION:
        bag2_text += f"`{val}` Soulstones: `{prob*100:.2f}%`\n"
    bag2_text += f"**Expected Value per Draw:** `{bag2_exp_val:.2f}`"
    embed.add_field(name="Bag II", value=bag2_text, inline=False)

    embed.set_footer(text=f"Data provided by Castle Clash")
    await interaction.response.send_message(embed=embed, ephemeral=False)


@bot.tree.command(
    name="help", description="Shows information about the bot and its commands."
)
async def help_command_slash(interaction: discord.Interaction):
    logger.info(
        f"Slash command 'help' called by {interaction.user} ({interaction.user.id})."
    )
    embed = discord.Embed(
        title="📚 Soulstone Calculator Help",
        description="Here's how to use me to calculate your soulstone probabilities:",
        color=discord.Color.blue(),
    )
    if bot.user and bot.user.display_avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)

    embed.add_field(
        name="💎 Main Command: `/bags`",
        value="Calculates the probability of obtaining at least a target amount of soulstones from two types of bags.",
        inline=False,
    )
    embed.add_field(
        name="Usage:",
        value="`/bags bag1:<number> bag2:<number> ss:<target_sum>`\n"
        "Example: `/bags bag1:10 bag2:5 ss:200`\n"
        "*(This is the recommended way to use the bot!)*",
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
        name="✨ Key Features:",
        value=(
            "• Automatically selects the best calculation method (exact for smaller inputs, Normal Approximation for larger).\n"
            "• Provides the average expected soulstones.\n"
            "• Displays the top 3 most likely sums for exact calculations (if distinct enough).\n"
            "• Cooldown of `10 seconds` per user to prevent spam.\n"
            "• Use `/baginfo` or `!baginfo` to see bag contents.\n"
            "• Use `/info` or `!info` for general bot information."
        ),
        inline=False,
    )
    embed.set_footer(text=f"Bot made by {OWNER_DISPLAY_NAME}")
    await interaction.response.send_message(embed=embed, ephemeral=False)


# --- Owner-Only Commands ---
@bot.command(name="sync", description="[Owner Only] Syncs slash commands globally.")
@commands.is_owner()
async def sync_prefix(ctx):
    logger.info(f"Owner {ctx.author.id} called 'sync' prefix command.")
    await ctx.send("Syncing slash commands globally. This may take a moment...")
    try:
        await bot.tree.sync()  # Syncs all global commands
        await ctx.send("Slash commands synced successfully!")
        logger.info("Slash commands synced via owner command.")
    except Exception as e:
        await ctx.send(f"Failed to sync slash commands: `{e}`")
        logger.error(f"Failed to sync slash commands via owner command: {e}")


@bot.tree.command(
    name="sync", description="[Owner Only] Syncs slash commands globally."
)
@app_commands.is_owner()
async def sync_slash(interaction: discord.Interaction):
    logger.info(f"Owner {interaction.user.id} called 'sync' slash command.")
    await interaction.response.send_message(
        "Syncing slash commands globally. This may take a moment...", ephemeral=True
    )
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
@app_commands.is_owner()
async def shutdown_slash(interaction: discord.Interaction):
    logger.warning(
        f"Owner {interaction.user.id} initiated bot shutdown via slash command."
    )
    await interaction.response.send_message(
        "Shutting down the bot. Goodbye!", ephemeral=True
    )
    await bot.close()


bot.run(TOKEN)
