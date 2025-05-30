import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import collections
import random
from collections import Counter

from keep_alive import keep_alive

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
OWNER = os.getenv("OWNER_ID")

keep_alive()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Define a reasonable timeout for the calculation (e.g., 10 seconds)
# You might need to adjust this based on your bot's resources and expected maximum input size.
CALCULATION_TIMEOUT = 15  # seconds
EXACT_CALC_THRESHOLD_BOX1 = 30  # Tune these values based on your server's performance
EXACT_CALC_THRESHOLD_BOX2 = (
    30  # For example, 20 bags might be your limit for exact calc
)


# Define a custom cooldown mapping for prefix commands
# This allows us to manually trigger and reset cooldowns
prefix_cooldowns = commands.CooldownMapping.from_cooldown(
    1, 10, commands.BucketType.user
)


async def calculate_exact_probabilities(box_def, num_draws):
    """
    Calculates the exact probability distribution of sums from a box using dynamic programming.
    Now an async function to allow for cancellation/timeout.

    Args:
        box_def (list of tuples): List of (value, probability) tuples.
        num_draws (int): Number of draws.

    Returns:
        dict: A dictionary where keys are sums and values are their exact probabilities.
    """
    current_probabilities = {0: 1.0}

    for _ in range(num_draws):
        # Allow the event loop to breathe to prevent blocking during long calculations
        # and to allow cancellation if a timeout occurs.
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
    # Calculate probabilities for Box 1 sums
    box1_sums_probs = await calculate_exact_probabilities(box1_def, draws_box1)

    # Calculate probabilities for Box 2 sums
    box2_sums_probs = await calculate_exact_probabilities(box2_def, draws_box2)

    # Combine probabilities from Box 1 and Box 2 draws
    combined_sums_probs = collections.defaultdict(float)
    for sum1, prob1 in box1_sums_probs.items():
        for sum2, prob2 in box2_sums_probs.items():
            # Allow the event loop to breathe during the combination step
            await asyncio.sleep(0)
            combined_sums_probs[sum1 + sum2] += prob1 * prob2

    # Calculate probability of sum >= target_sum
    prob_at_least_target = sum(
        prob for s, prob in combined_sums_probs.items() if s >= target_sum
    )

    # Get top 3 most likely sums
    # Convert to list of (sum, probability) and sort
    sorted_sums = sorted(
        combined_sums_probs.items(), key=lambda item: item[1], reverse=True
    )
    top_3_sums_with_probs = [(s, p) for s, p in sorted_sums[:3]]

    return (prob_at_least_target * 100, top_3_sums_with_probs)  # Convert to percentage


async def async_parser(num_draws_box1, num_draws_box2, target_sum_value):
    """
    An async version of the parser function to be used with asyncio.wait_for.
    """
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

    return await run_exact_calculation(
        box1_definition,
        box2_definition,
        num_draws_box1,
        num_draws_box2,
        target_sum_value,
    )


async def simulate_draws(box_def, num_draws):
    """Simulates one set of draws from a box."""
    total_sum = 0
    # Create a flat list of values for random.choice based on probabilities
    # This is a simple way, more robust ways exist if probabilities are very granular
    bag_values = [
        val for val, prob in box_def for _ in range(int(prob * 10000))
    ]  # Scale up for better representation
    if not bag_values:  # Should not happen with valid box_def
        return 0

    for _ in range(num_draws):
        total_sum += random.choice(bag_values)
    return total_sum


async def run_monte_carlo_simulation(
    box1_def, box2_def, draws_box1, draws_box2, target_sum, num_simulations=100000
):
    """
    Runs a Monte Carlo simulation for combined bag draws.
    num_simulations: How many times to simulate the entire process.
    """
    successful_outcomes = 0
    combined_sums = []  # To store all sums for top 3

    for i in range(num_simulations):
        # Allow the event loop to breathe
        if i % 1000 == 0:  # Yield every 1000 simulations
            await asyncio.sleep(0)

        sum1 = await simulate_draws(box1_def, draws_box1)
        sum2 = await simulate_draws(box2_def, draws_box2)
        total_sum = sum1 + sum2
        combined_sums.append(total_sum)

        if total_sum >= target_sum:
            successful_outcomes += 1

    prob_at_least_target = (successful_outcomes / num_simulations) * 100

    # Get top 3 most likely sums from simulations
    # Use Counter to count occurrences, then get most common
    sum_counts = Counter(combined_sums)
    top_3_sums = sum_counts.most_common(3)  # Returns list of (sum, count)

    # Convert counts to probabilities for display
    top_3_sums_with_probs = [(s, count / num_simulations) for s, count in top_3_sums]

    return prob_at_least_target, top_3_sums_with_probs


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged on as {bot.user}!")


@bot.command(
    name="bags",
    description="Will calc the chance to obtain at least [ss] soulstones from [bag1] bags I plus [bag2] bags II",
)
async def bags_prefix(ctx, bag1: int, bag2: int, ss: int):
    """
    Calculates soulstone probabilities for prefix command !bags.
    """
    # Check cooldown BEFORE performing calculation or input validation
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

    if bag1 < 0 or bag2 < 0 or ss < 0:
        # If input is invalid, we don't want to apply cooldown, so we "refund" the charge
        bucket.reset()  # This resets the cooldown for this bucket
        embed = discord.Embed(
            title="",
            description="Wrong input. Numbers of bags and soulstones goal must be non-negative.",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)
        return

    # Determine if exact calculation or simulation is needed
    use_exact_calculation = (
        bag1 <= EXACT_CALC_THRESHOLD_BOX1 and bag2 <= EXACT_CALC_THRESHOLD_BOX2
    )

    initial_message_text = (
        "Calculating (exact method)... This might take a moment."
        if use_exact_calculation
        else "Calculating (simulation method)... This might take a moment."
    )
    initial_message = await ctx.send(initial_message_text)

    try:
        if use_exact_calculation:
            prob_at_least_target, top_sums = await asyncio.wait_for(
                async_parser(bag1, bag2, ss), timeout=CALCULATION_TIMEOUT
            )
        else:
            # For simulation, you might want a longer timeout or no timeout for the simulation itself
            # as it's designed to complete based on num_simulations, not combinatorial size.
            # But keep the overall timeout for the bot's response.
            prob_at_least_target, top_sums = await asyncio.wait_for(
                run_monte_carlo_simulation(
                    [
                        (1, 0.36),
                        (2, 0.37),
                        (5, 0.15),
                        (10, 0.07),
                        (20, 0.03),
                        (30, 0.02),
                    ],
                    [
                        (10, 0.46),
                        (15, 0.27),
                        (20, 0.17),
                        (50, 0.05),
                        (80, 0.03),
                        (100, 0.02),
                    ],
                    bag1,
                    bag2,
                    ss,
                ),
                timeout=CALCULATION_TIMEOUT,
            )
    except asyncio.TimeoutError:
        embed = discord.Embed(
            title="Calculation Timeout",
            description=f"The calculation took too long (>{CALCULATION_TIMEOUT} seconds) and was cancelled. Please try with smaller bag numbers.",
            color=discord.Color.orange(),
        )
        await initial_message.edit(
            content=None, embed=embed
        )  # Edit the original message
        return
    except Exception as e:
        # Catch any other unexpected errors during calculation
        embed = discord.Embed(
            title="Calculation Error",
            description=f"An unexpected error occurred during calculation: {e}",
            color=discord.Color.red(),
        )
        await initial_message.edit(content=None, embed=embed)
        return

    if not top_sums:
        embed = discord.Embed(
            title="",
            description="Something went wrong during calculation.",
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
    embed.add_field(
        name="--- Pre-results ---",
        value=f"Average Soulstones Expected: {3.75*bag1+18.95*bag2}",
        inline=False,
    )
    # Modify the embed description to indicate approximation if applicable
    result_description = ""
    if not use_exact_calculation:
        result_description += (
            f"(Results are approximate based on 100000 simulations)\n\n"
        )
    result_description += (
        f"Probability of Soulstones being at least {ss}: {prob_at_least_target:.4f}%"
    )
    embed.add_field(
        name="--- Results ---",
        value=result_description,
        inline=False,
    )
    embed.add_field(
        name="--- Three Most Likely Total Soulstones Count and Their Chances ---",
        value=(
            f" 1. Total Soulstones: {top_sums[0][0]}, Chance: {top_sums[0][1]*100:.4f}%\n"
            f" 2. Total Soulstones: {top_sums[1][0]}, Chance: {top_sums[1][1]*100:.4f}%\n"
            f" 3. Total Soulstones: {top_sums[2][0]}, Chance: {top_sums[2][1]*100:.4f}%"
        ),
        inline=False,
    )
    embed.add_field(
        name="",
        value=f"Bot made by <@{OWNER}>",
        inline=False,
    )
    await initial_message.edit(content=None, embed=embed)  # Edit the original message


@bags_prefix.error
async def bags_prefix_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        embed = discord.Embed(
            title="",
            description=f"This command is on cooldown. Please try again after {error.retry_after:.2f} seconds.",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)
    elif isinstance(error, commands.MissingRequiredArgument):
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
        # For any other unhandled errors
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
    """
    Calculates soulstone probabilities for slash command /bags.
    """

    await interaction.response.defer(thinking=True)  # Defer the response immediately

    if bag1 < 0 or bag2 < 0 or ss < 0:
        embed = discord.Embed(
            title="",
            description="Numbers of bags and soulstones goal must be non-negative.",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Determine if exact calculation or simulation is needed
    use_exact_calculation = (
        bag1 <= EXACT_CALC_THRESHOLD_BOX1 and bag2 <= EXACT_CALC_THRESHOLD_BOX2
    )

    try:
        if use_exact_calculation:
            prob_at_least_target, top_sums = await asyncio.wait_for(
                async_parser(bag1, bag2, ss), timeout=CALCULATION_TIMEOUT
            )
        else:
            # For simulation, you might want a longer timeout or no timeout for the simulation itself
            # as it's designed to complete based on num_simulations, not combinatorial size.
            # But keep the overall timeout for the bot's response.
            prob_at_least_target, top_sums = await asyncio.wait_for(
                run_monte_carlo_simulation(
                    [
                        (1, 0.36),
                        (2, 0.37),
                        (5, 0.15),
                        (10, 0.07),
                        (20, 0.03),
                        (30, 0.02),
                    ],
                    [
                        (10, 0.46),
                        (15, 0.27),
                        (20, 0.17),
                        (50, 0.05),
                        (80, 0.03),
                        (100, 0.02),
                    ],
                    bag1,
                    bag2,
                    ss,
                ),
                timeout=CALCULATION_TIMEOUT,
            )
    except asyncio.TimeoutError:
        embed = discord.Embed(
            title="Calculation Timeout",
            description=f"The calculation took too long (>{CALCULATION_TIMEOUT} seconds) and was cancelled. Please try with smaller bag numbers.",
            color=discord.Color.orange(),
        )
        await interaction.followup.send(embed=embed)
        return
    except Exception as e:
        # Catch any other unexpected errors during calculation
        embed = discord.Embed(
            title="Calculation Error",
            description=f"An unexpected error occurred during calculation: {e}",
            color=discord.Color.red(),
        )
        await interaction.followup.send(embed=embed)
        return

    if not top_sums:
        embed = discord.Embed(
            title="",
            description="Something went wrong during calculation.",
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
        value=f"Average Soulstones Expected: {3.75*bag1+18.95*bag2}",
        inline=False,
    )
    # Modify the embed description to indicate approximation if applicable
    result_description = ""
    if not use_exact_calculation:
        result_description += (
            f"(Results are approximate based on 100000 simulations)\n\n"
        )
    result_description += (
        f"Probability of Soulstones being at least {ss}: {prob_at_least_target:.4f}%"
    )
    embed.add_field(
        name="--- Results ---",
        value=result_description,
        inline=False,
    )
    embed.add_field(
        name="--- Three Most Likely Total Soulstones Count and Their Chances ---",
        value=(
            f" 1. Total Soulstones: {top_sums[0][0]}, Chance: {top_sums[0][1]*100:.4f}%\n"
            f" 2. Total Soulstones: {top_sums[1][0]}, Chance: {top_sums[1][1]*100:.4f}%\n"
            f" 3. Total Soulstones: {top_sums[2][0]}, Chance: {top_sums[2][1]*100:.4f}%"
        ),
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
    else:
        # Handle other potential errors for slash commands if needed
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

    # Attempt to send to the system channel, fall back to the first text channel if system channel is None
    if guild.system_channel:
        await guild.system_channel.send(embed=embed)
    else:
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                await channel.send(embed=embed)
                break


bot.run(TOKEN)
