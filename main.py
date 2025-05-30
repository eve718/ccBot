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

# Global variable to store the owner's display name
OWNER_DISPLAY_NAME = "Bot Owner"  # Default value in case fetching fails


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
    probabilities /= probabilities.sum()
    total_sum = np.random.choice(values, size=num_draws, p=probabilities).sum()
    return int(total_sum)


async def run_monte_carlo_simulation(
    box1_def, box2_def, draws_box1, draws_box2, target_sum, num_simulations
):
    successful_outcomes = 0
    combined_sums_for_stats = []
    values1 = np.array([val for val, prob in box1_def])
    probabilities1 = np.array([prob for val, prob in box1_def])
    probabilities1 /= probabilities1.sum()
    values2 = np.array([val for val, prob in box2_def])
    probabilities2 = np.array([prob for val, prob in box2_def])
    probabilities2 /= probabilities2.sum()
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
    variance = sum((val - expected_value) ** 2 * prob for val, prob in box_def)
    return expected_value, variance


def run_normal_approximation(box1_def, box2_def, draws_box1, draws_box2, target_sum):
    mean1, var1 = get_bag_stats(box1_def)
    mean2, var2 = get_bag_stats(box2_def)
    total_mean = (mean1 * draws_box1) + (mean2 * draws_box2)
    total_variance = (var1 * draws_box1) + (var2 * draws_box2)
    total_std_dev = math.sqrt(total_variance)
    z_score = (target_sum - 0.5 - total_mean) / total_std_dev
    prob_at_least_target = (1 - norm.cdf(z_score)) * 100
    return prob_at_least_target, []


async def async_parser(num_draws_box1, num_draws_box2, target_sum_value):
    box1_definition = [
        (1, 0.36),
        (2, 0.37),
        (5, 0.15),
        (10, 0.07),
        (20, 0.03),
        (30, 0.02),
    ]
    box2_definition = [
        (10, 0.46),
        (15, 0.27),
        (20, 0.17),
        (50, 0.05),
        (80, 0.03),
        (100, 0.02),
    ]

    if (
        num_draws_box1 <= EXACT_CALC_THRESHOLD_BOX1
        and num_draws_box2 <= EXACT_CALC_THRESHOLD_BOX2
    ):
        result_data = await run_exact_calculation(
            box1_definition,
            box2_definition,
            num_draws_box1,
            num_draws_box2,
            target_sum_value,
        )
        method = "exact"
    elif SCIPY_AVAILABLE:
        result_data = run_normal_approximation(
            box1_definition,
            box2_definition,
            num_draws_box1,
            num_draws_box2,
            target_sum_value,
        )
        method = "normal_approx"
    else:
        raise ValueError(
            "Cannot calculate for these inputs. SciPy library is not available for approximation."
        )
    return result_data, method


# --- Bot Events ---
@bot.event
async def on_ready():
    global OWNER_DISPLAY_NAME
    await bot.tree.sync()
    print(f"Logged on as {bot.user}!")

    # Attempt to fetch the owner's user object and set their display name
    try:
        owner_user = await bot.fetch_user(int(OWNER))
        OWNER_DISPLAY_NAME = (
            owner_user.display_name
            if hasattr(owner_user, "display_name")
            else owner_user.name
        )
    except (ValueError, discord.NotFound, discord.HTTPException) as e:
        print(f"Could not fetch owner's name: {e}. Using default 'Bot Owner'.")
        OWNER_DISPLAY_NAME = "Bot Owner"  # Fallback if owner not found or error


@bot.event
async def on_guild_join(guild):
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
        value="Type `/help` or `!help` for detailed command information and tips.",
        inline=False,
    )
    embed.set_footer(text=f"Bot developed by {OWNER_DISPLAY_NAME}")  # Updated footer

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

    embed.add_field(
        name="📈 Expected Average",
        value=f"Your average expected soulstones are: `{3.75*bag1+18.95*bag2:.2f}`",
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
    )  # Updated footer
    return embed


# --- Prefix Commands ---
@bot.command(name="bags")
async def bags_prefix(ctx, bag1: int, bag2: int, ss: int):
    bucket = prefix_cooldowns.get_bucket(ctx.message)
    retry_after = bucket.update_rate_limit()

    if retry_after:
        embed = discord.Embed(
            title="⚠️ Cooldown Active",
            description=f"This command is on cooldown. Please try again after `{retry_after:.2f}` seconds.",
            color=discord.Color.orange(),
        )
        await ctx.send(embed=embed)
        return

    if bag1 < 0 or bag2 < 0 or ss < 0:
        bucket.reset()
        embed = discord.Embed(
            title="❌ Invalid Input",
            description="Numbers of bags and soulstones goal must be non-negative integers.",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)
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
    except asyncio.TimeoutError:
        bucket.reset()
        embed = discord.Embed(
            title="⏰ Calculation Timeout",
            description=f"The calculation took too long (more than `{CALCULATION_TIMEOUT}` seconds) and was cancelled. Please try with smaller bag numbers.",
            color=discord.Color.orange(),
        )
        await initial_message.edit(content=None, embed=embed)
        return
    except ValueError as e:
        bucket.reset()
        embed = discord.Embed(
            title="❌ Calculation Error",
            description=f"Input error: {e}",
            color=discord.Color.red(),
        )
        await initial_message.edit(content=None, embed=embed)
        return
    except Exception as e:
        bucket.reset()
        embed = discord.Embed(
            title="⚠️ Unexpected Error",
            description=f"An unexpected error occurred during calculation: `{e}`",
            color=discord.Color.red(),
        )
        await initial_message.edit(content=None, embed=embed)
        return

    final_embed = await create_bags_embed(
        bag1, bag2, ss, prob_at_least_target, top_sums, method_used
    )
    await initial_message.edit(content=None, embed=final_embed)


@bags_prefix.error
async def bags_prefix_error(ctx, error):
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


# --- Help Commands ---
@bot.command(name="help")
async def help_command_prefix(ctx):
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
            "• Cooldown of `10 seconds` per user to prevent spam."
        ),
        inline=False,
    )
    embed.set_footer(
        text=f"Bot made by {OWNER_DISPLAY_NAME} | Use /help for slash command version"
    )  # Updated footer
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
    await interaction.response.defer(thinking=True, ephemeral=True)

    if bag1 < 0 or bag2 < 0 or ss < 0:
        embed = discord.Embed(
            title="❌ Invalid Input",
            description="Numbers of bags and soulstones goal must be non-negative integers.",
            color=discord.Color.red(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    calculation_method_display = "Calculating..."
    if bag1 <= EXACT_CALC_THRESHOLD_BOX1 and bag2 <= EXACT_CALC_THRESHOLD_BOX2:
        calculation_method_display = "Calculating (Exact Method)..."
    elif SCIPY_AVAILABLE:
        calculation_method_display = "Calculating (Normal Approximation)..."
    else:
        calculation_method_display = "Inputs too large; approximation library (SciPy) not available. Calculation may fail."

    await interaction.followup.send(
        f"{calculation_method_display} Please wait...", ephemeral=True
    )

    try:
        (prob_at_least_target, top_sums), method_used = await asyncio.wait_for(
            async_parser(bag1, bag2, ss), timeout=CALCULATION_TIMEOUT
        )
    except asyncio.TimeoutError:
        embed = discord.Embed(
            title="⏰ Calculation Timeout",
            description=f"The calculation took too long (more than `{CALCULATION_TIMEOUT}` seconds) and was cancelled. Please try with smaller bag numbers.",
            color=discord.Color.orange(),
        )
        await interaction.followup.send(embed=embed, ephemeral=False)
        return
    except ValueError as e:
        embed = discord.Embed(
            title="❌ Calculation Error",
            description=f"Input error: {e}",
            color=discord.Color.red(),
        )
        await interaction.followup.send(embed=embed, ephemeral=False)
        return
    except Exception as e:
        embed = discord.Embed(
            title="⚠️ Unexpected Error",
            description=f"An unexpected error occurred during calculation: `{e}`",
            color=discord.Color.red(),
        )
        await interaction.followup.send(embed=embed, ephemeral=False)
        return

    final_embed = await create_bags_embed(
        bag1, bag2, ss, prob_at_least_target, top_sums, method_used
    )
    await interaction.followup.send(embed=final_embed, ephemeral=False)


@bags_slash.error
async def bags_slash_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
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
            description=f"An unexpected error occurred: `{error}`",
            color=discord.Color.red(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(
    name="help", description="Shows information about the bot and its commands."
)
async def help_command_slash(interaction: discord.Interaction):
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
            "• Cooldown of `10 seconds` per user to prevent spam."
        ),
        inline=False,
    )
    embed.set_footer(text=f"Bot made by {OWNER_DISPLAY_NAME}")  # Updated footer
    await interaction.response.send_message(embed=embed, ephemeral=False)


bot.run(TOKEN)
