import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import collections
import random
from collections import Counter
import math  # For math.sqrt
import numpy as np  # Added for potential future use or if simulate_single_bag_draws was used elsewhere efficiently

# You might need to install scipy for the normal approximation tier:
# pip install scipy
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

CALCULATION_TIMEOUT = 15  # seconds - Adjusted slightly based on your observation
# Define thresholds for switching calculation methods
# You will need to TUNE these based on actual performance on your host.
# Start conservative and increase if stable.
EXACT_CALC_THRESHOLD_BOX1 = 100  # Max draws for Box 1 using exact method
EXACT_CALC_THRESHOLD_BOX2 = 100  # Max draws for Box 2 using exact method


# --- NEW: Probability difference threshold for top sums output ---
# If the difference between the 1st and 3rd probabilities is less than this,
# the "top 3 sums" output will be suppressed.
# Tune this value: e.g., 0.001 (0.1%), 0.005 (0.5%)
PROB_DIFFERENCE_THRESHOLD = 0.001  # 0.1% difference


# Define a custom cooldown mapping for prefix commands
prefix_cooldowns = commands.CooldownMapping.from_cooldown(
    1, 10, commands.BucketType.user
)


async def calculate_exact_probabilities(box_def, num_draws):
    """
    Calculates the exact probability distribution of sums from a box using dynamic programming.
    Now an async function to allow for cancellation/timeout.
    """
    current_probabilities = {0: 1.0}

    for _ in range(num_draws):
        await asyncio.sleep(0)  # Yield control
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
        # Allow event loop to breathe during the potentially large combination step
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


# --- Monte Carlo Simulation Logic (No longer called by async_parser, but kept for reference) ---
# Optimized simulate_single_bag_draws using NumPy
def simulate_single_bag_draws(box_def, num_draws):  # Changed to sync function
    """Simulates drawing `num_draws` times from a single `box_def` using NumPy."""
    if not box_def or num_draws == 0:  # Handle empty box_def or zero draws
        return 0

    # Separate values and probabilities using NumPy arrays for efficiency
    values = np.array([val for val, prob in box_def])
    probabilities = np.array([prob for val, prob in box_def])

    # Normalize probabilities in case of floating point inaccuracies (good practice)
    probabilities /= probabilities.sum()

    # Use numpy's choice for vectorized drawing and sum the results
    # This avoids a Python loop for each draw
    total_sum = np.random.choice(values, size=num_draws, p=probabilities).sum()
    return int(total_sum)  # Ensure integer return


async def run_monte_carlo_simulation(  # This function is no longer called by async_parser
    box1_def, box2_def, draws_box1, draws_box2, target_sum, num_simulations
):
    """
    Runs a Monte Carlo simulation for combined bag draws.
    (Note: This function is currently not called by async_parser)
    """
    successful_outcomes = 0
    combined_sums_for_stats = []

    # Pre-process box definitions into NumPy arrays once
    values1 = np.array([val for val, prob in box1_def])
    probabilities1 = np.array([prob for val, prob in box1_def])
    probabilities1 /= probabilities1.sum()  # Normalize

    values2 = np.array([val for val, prob in box2_def])
    probabilities2 = np.array([prob for val, prob in box2_def])
    probabilities2 /= probabilities2.sum()  # Normalize

    # Determine a batch size for yielding control
    batch_size = max(
        1, num_simulations // 1000
    )  # Yield at least 1000 times over total simulations

    for i in range(num_simulations):
        if i % batch_size == 0:
            await asyncio.sleep(0)  # Keep yielding if this function *were* to be called

        # Now calling simulate_single_bag_draws as a synchronous numpy-based function
        sum1 = simulate_single_bag_draws(box1_def, draws_box1)
        sum2 = simulate_single_bag_draws(box2_def, draws_box2)

        total_sum = (
            sum1 + sum2
        )  # No await needed here anymore if simulate_single_bag_draws is sync
        combined_sums_for_stats.append(total_sum)

        if total_sum >= target_sum:
            successful_outcomes += 1

    prob_at_least_target = (successful_outcomes / num_simulations) * 100

    sum_counts = Counter(combined_sums_for_stats)
    top_3_raw = sum_counts.most_common(3)
    top_3_sums_with_probs = [(s, count / num_simulations) for s, count in top_3_raw]

    return prob_at_least_target, top_3_sums_with_probs


# --- Normal Approximation Logic ---
def get_bag_stats(box_def):
    """Calculates mean and variance for a single bag."""
    expected_value = sum(val * prob for val, prob in box_def)
    variance = sum((val - expected_value) ** 2 * prob for val, prob in box_def)
    return expected_value, variance


def run_normal_approximation(box1_def, box2_def, draws_box1, draws_box2, target_sum):
    """
    Calculates probability using Normal Approximation (Central Limit Theorem).
    This is highly accurate for many draws.
    """
    mean1, var1 = get_bag_stats(box1_def)
    mean2, var2 = get_bag_stats(box2_def)

    total_mean = (mean1 * draws_box1) + (mean2 * draws_box2)
    total_variance = (var1 * draws_box1) + (
        var2 * draws_box2
    )  # Assumes independent draws
    total_std_dev = math.sqrt(total_variance)

    # Use continuity correction for discrete sums (subtract 0.5)
    z_score = (target_sum - 0.5 - total_mean) / total_std_dev

    prob_at_least_target = (1 - norm.cdf(z_score)) * 100

    # Normal approximation doesn't directly give "top 3 most likely sums" easily.
    # We return an empty list for top_sums in this case as per the request.
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

    # Decide which calculation method to use
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
    elif (
        SCIPY_AVAILABLE
    ):  # If exact is not feasible, and SciPy is available, use Normal Approximation
        result_data = (
            run_normal_approximation(  # NO AWAIT needed as it's a sync function
                box1_definition,
                box2_definition,
                num_draws_box1,
                num_draws_box2,
                target_sum_value,
            )
        )
        method = "normal_approx"
    else:
        # This branch is hit if:
        # 1. Inputs exceed EXACT_CALC_THRESHOLDs
        # 2. SCIPY_AVAILABLE is False
        # As Monte Carlo caused timeouts, we raise an error here.
        raise ValueError(
            "Cannot calculate for these inputs. SciPy library is not available for approximation."
        )

    return result_data, method


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged on as {bot.user}!")


@bot.command(name="bags")
async def bags_prefix(ctx, bag1: int, bag2: int, ss: int):
    # Cooldown check
    bucket = prefix_cooldowns.get_bucket(ctx.message)
    retry_after = bucket.update_rate_limit()

    if retry_after:
        embed = discord.Embed(
            title="",
            description=f"This command is on cooldown. Please try again after {retry_after:.2f} seconds.",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)
        return

    # Input validation
    if bag1 < 0 or bag2 < 0 or ss < 0:
        bucket.reset()
        embed = discord.Embed(
            title="",
            description="Wrong input. Numbers of bags and soulstones goal must be non-negative.",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)
        return

    calculation_method_display = "Calculating..."
    if bag1 <= EXACT_CALC_THRESHOLD_BOX1 and bag2 <= EXACT_CALC_THRESHOLD_BOX2:
        calculation_method_display = "Calculating (exact method)..."
    elif SCIPY_AVAILABLE:
        calculation_method_display = "Calculating (Normal Approximation)..."
    else:  # Fallback message if SciPy is not available for large inputs
        calculation_method_display = (
            "Inputs too large; approximation not available. Calculation may fail."
        )

    initial_message = await ctx.send(
        f"{calculation_method_display} This might take a moment."
    )

    try:
        (prob_at_least_target, top_sums), method_used = await asyncio.wait_for(
            async_parser(bag1, bag2, ss), timeout=CALCULATION_TIMEOUT
        )
    except asyncio.TimeoutError:
        bucket.reset()
        embed = discord.Embed(
            title="Calculation Timeout",
            description=f"The calculation took too long (>{CALCULATION_TIMEOUT} seconds) and was cancelled. Please try with smaller bag numbers or be aware that very large inputs may take a long time to compute even with approximations.",
            color=discord.Color.orange(),
        )
        await initial_message.edit(content=None, embed=embed)
        return
    except ValueError as e:  # Catch the specific ValueError from async_parser
        bucket.reset()
        embed = discord.Embed(
            title="Calculation Error",
            description=f"Input error: {e}",
            color=discord.Color.red(),
        )
        await initial_message.edit(content=None, embed=embed)
        return
    except Exception as e:
        bucket.reset()
        embed = discord.Embed(
            title="Calculation Error",
            description=f"An unexpected error occurred during calculation: {e}",
            color=discord.Color.red(),
        )
        await initial_message.edit(content=None, embed=embed)
        return

    embed = discord.Embed(
        title="",
        description="",
        color=discord.Color.red(),
    )
    embed.add_field(
        name="--- Parameters ---",
        value=f"Bag I Draws: {bag1}\nBag II Draws: {bag2}\nTarget Soulstones (at least): {ss}",
        inline=False,
    )

    # Pre-results (Average is always exact)
    embed.add_field(
        name="--- Pre-results ---",
        value=f"Average Soulstones Expected: {3.75*bag1+18.95*bag2:.2f}",
        inline=False,
    )

    # Main results - dynamically add approximation notice
    results_value = (
        f"Probability of Soulstones being at least {ss}: {prob_at_least_target:.4f}%"
    )
    if method_used == "normal_approx":  # Only check for normal_approx
        results_value += "\n*(Result is an approximation based on Normal Distribution)*"
    results_value += f"\n*Calculation Method: {method_used.replace('_', ' ').title()}*"

    embed.add_field(
        name="--- Results ---",
        value=results_value,
        inline=False,
    )

    # Conditionally add the "Top 3 sums" field (only for exact method)
    if method_used == "exact":
        top_sums_text = ""
        # Ensure there are enough elements in top_sums before accessing them
        padded_top_sums = top_sums + [(0, 0.0)] * (3 - len(top_sums))
        # Check if there are at least 3 sums and if the difference between the 1st and 3rd is too small
        if (
            len(top_sums) >= 3
            and abs(padded_top_sums[0][1] - padded_top_sums[2][1])
            < PROB_DIFFERENCE_THRESHOLD
        ):
            top_sums_text = f"Top sums are too close in probability (difference between 1st and 3rd < {PROB_DIFFERENCE_THRESHOLD*100:.2f}%) to be meaningfully distinct."
        elif (
            len(top_sums) < 1 or padded_top_sums[0][1] == 0.0
        ):  # No sums found or 0 probability
            top_sums_text = "No prominent sums found or calculated."
        else:
            # If the condition above isn't met, display the top sums
            for i, (s, p) in enumerate(padded_top_sums[:3]):
                if p > 0:  # Only show meaningful entries
                    top_sums_text += (
                        f" {i+1}. Total Soulstones: {s}, Chance: {p*100:.4f}%\n"
                    )
            if (
                not top_sums_text
            ):  # Fallback if for some reason the loop above didn't produce text
                top_sums_text = "No prominent sums found or calculated."

        embed.add_field(
            name="--- Three Most Likely Total Soulstones Count and Their Chances ---",
            value=top_sums_text.strip(),
            inline=False,
        )

    embed.add_field(
        name="",
        value=f"Bot made by <@{OWNER}>",
        inline=False,
    )
    await initial_message.edit(content=None, embed=embed)


@bags_prefix.error
async def bags_prefix_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title="",
            description="Wrong input. It should be like this:",
            color=discord.Color.red(),
        )
        embed.add_field(
            name="!bags [number of bags I] [number of bags II] [soulstones goal]",
            value="Example: !bags 10 5 200",
        )
        await ctx.send(embed=embed)
    elif isinstance(error, commands.BadArgument):
        embed = discord.Embed(
            title="",
            description="Wrong input. Please ensure bag numbers and soulstone goal are valid integers.",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="",
            description=f"An unexpected error occurred: {error}",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)


@bot.tree.command(
    name="bags",
    description=f"Will calc the chance to obtain at least [ss] soulstones from [bag1] bags I plus [bag2] bags II",
)
@app_commands.describe(
    bag1="Number of Bag I draws",
    bag2="Number of Bag II draws",
    ss="Target Soulstones (at least)",
)
@app_commands.checks.cooldown(
    1, 10, key=lambda i: i.user.id
)  # 1 use per 10 seconds per user
async def bags_slash(interaction: discord.Interaction, bag1: int, bag2: int, ss: int):
    await interaction.response.defer(thinking=True)

    if bag1 < 0 or bag2 < 0 or ss < 0:
        embed = discord.Embed(
            title="",
            description="Numbers of bags and soulstones goal must be non-negative.",
            color=discord.Color.red(),
        )
        await interaction.followup.send(embed=embed)
        return

    calculation_method_display = "Calculating..."
    if bag1 <= EXACT_CALC_THRESHOLD_BOX1 and bag2 <= EXACT_CALC_THRESHOLD_BOX2:
        calculation_method_display = "Calculating (exact method)..."
    elif SCIPY_AVAILABLE:
        calculation_method_display = "Calculating (Normal Approximation)..."
    else:  # Fallback message if SciPy is not available for large inputs
        calculation_method_display = (
            "Inputs too large; approximation not available. Calculation may fail."
        )

    await interaction.followup.send(f"{calculation_method_display}", ephemeral=True)

    try:
        (prob_at_least_target, top_sums), method_used = await asyncio.wait_for(
            async_parser(bag1, bag2, ss), timeout=CALCULATION_TIMEOUT
        )
    except asyncio.TimeoutError:
        embed = discord.Embed(
            title="Calculation Timeout",
            description=f"The calculation took too long (>{CALCULATION_TIMEOUT} seconds) and was cancelled. Please try with smaller bag numbers or be aware that very large inputs may take a long time to compute even with approximations.",
            color=discord.Color.orange(),
        )
        await interaction.followup.send(embed=embed)
        return
    except ValueError as e:  # Catch the specific ValueError from async_parser
        embed = discord.Embed(
            title="Calculation Error",
            description=f"Input error: {e}",
            color=discord.Color.red(),
        )
        await interaction.followup.send(embed=embed)
        return
    except Exception as e:
        embed = discord.Embed(
            title="Calculation Error",
            description=f"An unexpected error occurred during calculation: {e}",
            color=discord.Color.red(),
        )
        await interaction.followup.send(embed=embed)
        return

    embed = discord.Embed(
        title="",
        description="",
        color=discord.Color.red(),
    )
    embed.add_field(
        name="--- Parameters ---",
        value=f"Bag I Draws: {bag1}\nBag II Draws: {bag2}\nTarget Soulstones (at least): {ss}",
        inline=False,
    )
    embed.add_field(
        name="--- Pre-results ---",
        value=f"Average Soulstones Expected: {3.75*bag1+18.95*bag2:.2f}",
        inline=False,
    )

    results_value = (
        f"Probability of Soulstones being at least {ss}: {prob_at_least_target:.4f}%"
    )
    if method_used == "normal_approx":  # Only check for normal_approx
        results_value += "\n*(Result is an approximation based on Normal Distribution)*"
    results_value += f"\n*Calculation Method: {method_used.replace('_', ' ').title()}*"

    embed.add_field(
        name="--- Results ---",
        value=results_value,
        inline=False,
    )

    # Conditionally add the "Top 3 sums" field (only for exact method)
    if method_used == "exact":
        top_sums_text = ""
        padded_top_sums = top_sums + [(0, 0.0)] * (3 - len(top_sums))
        # Check if there are at least 3 sums AND if the difference between the 1st and 3rd is too small
        # Also handle cases where less than 3 sums are available or the probabilities are 0.
        if len(top_sums) < 3 or (
            len(top_sums) >= 3
            and abs(padded_top_sums[0][1] - padded_top_sums[2][1])
            < PROB_DIFFERENCE_THRESHOLD
        ):
            if len(top_sums) < 1 or padded_top_sums[0][1] == 0.0:
                top_sums_text = "No prominent sums found or calculated."
            else:
                top_sums_text = f"Top sums are too close in probability (difference between 1st and 3rd < {PROB_DIFFERENCE_THRESHOLD*100:.2f}%) to be meaningfully distinct."
        else:
            # If the condition above isn't met, display the top sums
            for i, (s, p) in enumerate(padded_top_sums[:3]):
                if p > 0:
                    top_sums_text += (
                        f" {i+1}. Total Soulstones: {s}, Chance: {p*100:.4f}%\n"
                    )

        embed.add_field(
            name="--- Three Most Likely Total Soulstones Count and Their Chances ---",
            value=top_sums_text.strip(),
            inline=False,
        )

    embed.add_field(
        name="",
        value=f"Bot made by <@{OWNER}>",
        inline=False,
    )
    await interaction.followup.send(embed=embed)


@bags_slash.error
async def bags_slash_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
    if isinstance(error, app_commands.CommandOnCooldown):
        embed = discord.Embed(
            title="",
            description=f"This command is on cooldown. Please try again after {error.retry_after:.2f} seconds.",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )
    elif isinstance(error, app_commands.BadArgument):
        embed = discord.Embed(
            title="",
            description="Invalid input. Please ensure bag numbers and soulstone goal are valid integers.",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        embed = discord.Embed(
            title="",
            description=f"An unexpected error occurred: {error}",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.event
async def on_guild_join(guild):
    embed = discord.Embed(
        title="",
        description="",
        color=discord.Color.red(),
    )
    embed.add_field(
        name="",
        value="Hi there! Below are the available commands",
        inline=False,
    )
    embed.add_field(
        name=" 1. !bags [number of bags I] [number of bags II] [soulstones goal]",
        value="This will calc the chance to obtain at least [soulstones goal] soulstones from [number of bags I] bags I plus [number of bags II] bags II",
        inline=False,
    )
    embed.add_field(
        name=" 2. /bags bag1:[bag1] bag2:[bag2] ss:[ss]",
        value="This will calc the chance to obtain at least [ss] soulstones from [bag1] bags I plus [bag2] bags II",
        inline=False,
    )

    if guild.system_channel:
        await guild.system_channel.send(embed=embed)
    else:
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                await channel.send(embed=embed)
                break


bot.run(TOKEN)
