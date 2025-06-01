import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import collections
import math
import numpy as np
import logging
from collections import Counter

logger = logging.getLogger("discord_bot")

# Assuming SCIPY_AVAILABLE is a global boolean on the bot instance
# Assuming BAG_I_DEFINITION, BAG_II_DEFINITION are global lists on the bot instance
# Assuming CALCULATION_TIMEOUT, EXACT_CALC_THRESHOLD_BOX1, EXACT_CALC_THRESHOLD_BOX2, PROB_DIFFERENCE_THRESHOLD are on the bot instance


# Helper functions for calculations (can be in a separate 'calc_helpers.py' if complex)
async def calculate_exact_probabilities(box_def, num_draws):
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
        await asyncio.sleep(0)  # Yield control
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


def run_normal_approximation(
    box1_def, box2_def, draws_box1, draws_box2, target_sum, scipy_available
):
    if not scipy_available:
        # This check is crucial if you are calling this function directly.
        # However, async_parser should already handle this.
        raise ImportError("SciPy not available for normal approximation.")
    from scipy.stats import norm  # Import here if needed specifically by this func

    mean1, var1 = get_bag_stats(box1_def)
    mean2, var2 = get_bag_stats(box2_def)
    total_mean = (mean1 * draws_box1) + (mean2 * draws_box2)
    total_variance = (var1 * draws_box1) + (var2 * draws_box2)
    total_std_dev = math.sqrt(total_variance)

    if total_std_dev == 0:
        return (100.0, []) if target_sum <= total_mean else (0.0, [])

    z_score = (target_sum - 0.5 - total_mean) / total_std_dev
    prob_at_least_target = (1 - norm.cdf(z_score)) * 100
    return prob_at_least_target, []


async def async_parser(bot_instance, num_draws_box1, num_draws_box2, target_sum_value):
    # Access definitions and thresholds from bot_instance
    box1_def_normalized = [
        (val, prob / sum(p for v, p in bot_instance.BAG_I_DEFINITION))
        for val, prob in bot_instance.BAG_I_DEFINITION
    ]
    box2_def_normalized = [
        (val, prob / sum(p for v, p in bot_instance.BAG_II_DEFINITION))
        for val, prob in bot_instance.BAG_II_DEFINITION
    ]

    if (
        num_draws_box1 <= bot_instance.EXACT_CALC_THRESHOLD_BOX1
        and num_draws_box2 <= bot_instance.EXACT_CALC_THRESHOLD_BOX2
    ):
        result_data = await run_exact_calculation(
            box1_def_normalized,
            box2_def_normalized,
            num_draws_box1,
            num_draws_box2,
            target_sum_value,
        )
        method = "exact"
    elif bot_instance.SCIPY_AVAILABLE:
        result_data = run_normal_approximation(
            box1_def_normalized,
            box2_def_normalized,
            num_draws_box1,
            num_draws_box2,
            target_sum_value,
            bot_instance.SCIPY_AVAILABLE,  # Pass this explicitly
        )
        result_data = (
            result_data[0],
            result_data[1],
            0.0,
        )
        method = "normal_approx"
    else:
        raise ValueError(
            "Inputs are too large for exact calculation, and the SciPy library is not available for approximation. Please contact the bot owner if you believe this is an error or need SciPy installed."
        )
    return result_data, method


# Embed generation functions for this cog
async def create_baginfo_embed(bot_instance: commands.Bot):
    bag1_exp, _ = get_bag_stats(bot_instance.BAG_I_DEFINITION)
    bag2_exp, _ = get_bag_stats(bot_instance.BAG_II_DEFINITION)

    embed = discord.Embed(
        title="🛍️ Bag Information",
        description="Details about the soulstone contents, average values, and calculation thresholds for Bag I and Bag II.",
        color=discord.Color.gold(),
    )
    if bot_instance.user and bot_instance.user.display_avatar:
        embed.set_thumbnail(url=bot_instance.user.display_avatar.url)

    bag1_contents_text = ""
    for val, prob in bot_instance.BAG_I_DEFINITION:
        bag1_contents_text += f"`{val}` Soulstones: `{prob*100:.2f}%`\n"
    embed.add_field(
        name="Bag I Contents & Averages",
        value=(
            f"**Individual Probabilities:**\n{bag1_contents_text}"
            f"**Average Expected per draw:** `{bag1_exp:.2f}` Soulstones\n"
            f"**Exact Calculation Threshold:** Up to `{bot_instance.EXACT_CALC_THRESHOLD_BOX1}` draws"
        ),
        inline=False,
    )

    bag2_contents_text = ""
    for val, prob in bot_instance.BAG_II_DEFINITION:
        bag2_contents_text += f"`{val}` Soulstones: `{prob*100:.2f}%`\n"
    embed.add_field(
        name="Bag II Contents & Averages",
        value=(
            f"**Individual Probabilities:**\n{bag2_contents_text}"
            f"**Average Expected per draw:** `{bag2_exp:.2f}` Soulstones\n"
            f"**Exact Calculation Threshold:** Up to `{bot_instance.EXACT_CALC_THRESHOLD_BOX2}` draws"
        ),
        inline=False,
    )

    embed.add_field(
        name="General Accuracy Note",
        value="Normal approximation accuracy improves with more draws. For precise results on smaller draws, use values within the exact calculation thresholds.",
        inline=False,
    )
    embed.set_footer(text=f"Information provided by Castle Clash")
    return embed


async def create_bags_embed(
    bot_instance,
    bag1,
    bag2,
    ss,
    prob_at_least_target,
    top_sums,
    method_used,
    prob_exact_target=None,
):
    embed = discord.Embed(
        title="📊 Soulstone Probability Results",
        description="Here are the calculation results for your bag draws:",
        color=(
            discord.Color.green() if prob_at_least_target > 0 else discord.Color.red()
        ),
    )
    if bot_instance.user and bot_instance.user.display_avatar:
        embed.set_thumbnail(url=bot_instance.user.display_avatar.url)

    embed.add_field(
        name="🔢 Input Parameters",
        value=f"**Bag I Draws:** `{bag1}`\n**Bag II Draws:** `{bag2}`\n**Target Soulstones (at least):** `{ss}`",
        inline=False,
    )

    box1_exp_val, _ = get_bag_stats(bot_instance.BAG_I_DEFINITION)
    box2_exp_val, _ = get_bag_stats(bot_instance.BAG_II_DEFINITION)

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
            < bot_instance.PROB_DIFFERENCE_THRESHOLD
        ):
            top_sums_text = f"Top sums are too close in probability (difference between 1st and 3rd < `{bot_instance.PROB_DIFFERENCE_THRESHOLD*100:.2f}%`) to be meaningfully distinct."
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
        text=f"Calculated by {bot_instance.user.name} • {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')} | Made by {bot_instance.OWNER_DISPLAY_NAME}"
    )
    return embed


class Bags(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="bags", aliases=["bag", "sscalc", "calculate"])
    async def bags_prefix(self, ctx, bag1: int, bag2: int, ss: int):
        logger.info(
            f"Prefix command 'bags' called by {ctx.author} ({ctx.author.id}) with args: bag1={bag1}, bag2={bag2}, ss={ss}"
        )
        # Access cooldowns from bot_instance
        bucket = self.bot.prefix_cooldowns.get_bucket(ctx.message)
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
        if (
            bag1 <= self.bot.EXACT_CALC_THRESHOLD_BOX1
            and bag2 <= self.bot.EXACT_CALC_THRESHOLD_BOX2
        ):
            calculation_method_display = "Calculating (Exact Method)..."
        elif self.bot.SCIPY_AVAILABLE:
            calculation_method_display = "Calculating (Normal Approximation)..."
        else:
            calculation_method_display = "Inputs too large; approximation library (SciPy) not available. Calculation may fail."

        initial_message = await ctx.send(
            f"{calculation_method_display} This might take a moment. Please wait..."
        )

        try:
            result_data, method_used = await asyncio.wait_for(
                async_parser(self.bot, bag1, bag2, ss),
                timeout=self.bot.CALCULATION_TIMEOUT,
            )
            prob_at_least_target, top_sums, prob_exact_target = result_data
            logger.info(
                f"Calculation for {ctx.author.id} successful (method: {method_used})."
            )
        except asyncio.TimeoutError:
            bucket.reset()
            embed = discord.Embed(
                title="⏰ Calculation Timeout",
                description=f"The calculation took too long (more than `{self.bot.CALCULATION_TIMEOUT}` seconds) and was cancelled. Please try with smaller bag numbers.",
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
            logger.error(
                f"Value error for {ctx.author.id} in 'bags' prefix command: {e}"
            )
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
            self.bot,
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
    async def bags_prefix_error(self, ctx, error):
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

    @app_commands.command(
        name="bags", description="Calculates soulstone probabilities."
    )
    @app_commands.describe(
        bag1="Number of Bag I draws",
        bag2="Number of Bag II draws",
        ss="Target soulstones (at least)",
    )
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: (i.guild_id, i.user.id))
    async def bags_slash(
        self, interaction: discord.Interaction, bag1: int, bag2: int, ss: int
    ):
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

        await interaction.response.defer(ephemeral=False)

        calculation_method_display = "Calculating..."
        if (
            bag1 <= self.bot.EXACT_CALC_THRESHOLD_BOX1
            and bag2 <= self.bot.EXACT_CALC_THRESHOLD_BOX2
        ):
            calculation_method_display = "Calculating (Exact Method)..."
        elif self.bot.SCIPY_AVAILABLE:
            calculation_method_display = "Calculating (Normal Approximation)..."
        else:
            calculation_method_display = "Inputs too large; approximation library (SciPy) not available. Calculation may fail."

        try:
            result_data, method_used = await asyncio.wait_for(
                async_parser(self.bot, bag1, bag2, ss),
                timeout=self.bot.CALCULATION_TIMEOUT,
            )
            prob_at_least_target, top_sums, prob_exact_target = result_data
            logger.info(
                f"Calculation for {interaction.user.id} successful (method: {method_used})."
            )

            final_embed = await create_bags_embed(
                self.bot,
                bag1,
                bag2,
                ss,
                prob_at_least_target,
                top_sums,
                method_used,
                prob_exact_target,
            )
            await interaction.followup.edit_original_response(
                content=None, embed=final_embed
            )
        except asyncio.TimeoutError:
            embed = discord.Embed(
                title="⏰ Calculation Timeout",
                description=f"The calculation took too long (more than `{self.bot.CALCULATION_TIMEOUT}` seconds) and was cancelled. Please try with smaller bag numbers.",
                color=discord.Color.orange(),
            )
            await interaction.followup.edit_original_response(content=None, embed=embed)
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
            await interaction.followup.edit_original_response(content=None, embed=embed)
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
            await interaction.followup.edit_original_response(content=None, embed=embed)
            logger.exception(
                f"Unexpected error for {interaction.user.id} in 'bags' slash command."
            )
            return

    @commands.command(
        name="baginfo",
        aliases=["bagdetails"],
        description="Displays information about Bag I and Bag II contents and their average values.",
    )
    async def baginfo_prefix(self, ctx):
        logger.info(
            f"Prefix command 'baginfo' called by {ctx.author} ({ctx.author.id})."
        )
        async with ctx.typing():
            embed = await create_baginfo_embed(self.bot)
            await ctx.send(embed=embed)
            logger.info(f"Sent baginfo response to {ctx.author.id}.")

    @app_commands.command(
        name="baginfo", description="Displays information about Bag I and Bag II."
    )
    async def baginfo_slash(self, interaction: discord.Interaction):
        logger.info(
            f"Slash command 'baginfo' called by {interaction.user} ({interaction.user.id})."
        )
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=True)
        embed = await create_baginfo_embed(self.bot)
        await interaction.followup.send(embed=embed)
        logger.info(f"Sent baginfo response to {interaction.user.id}.")


async def setup(bot):
    await bot.add_cog(Bags(bot))
