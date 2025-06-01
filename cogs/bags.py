# cogs/bags.py

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import collections
import logging

# Import calculation helpers from your new utility file
from utils.bags_calculations import async_parser, get_bag_stats

logger = logging.getLogger("discord_bot")


async def create_bags_embed(
    bot_instance,  # This is the bot object, which holds owner_display_name and constants
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
        # Pad top_sums to ensure at least 3 elements for indexing, then filter out 0.0 prob
        padded_top_sums = list(top_sums.items()) + [(0, 0.0)] * (3 - len(top_sums))

        # Sort again to ensure consistency after padding, prioritizing probability, then sum
        padded_top_sums.sort(key=lambda item: (item[1], item[0]), reverse=True)

        # Filter out entries with 0 probability for display
        display_top_sums = [item for item in padded_top_sums if item[1] > 0][:3]

        if (
            len(display_top_sums) >= 3
            and abs(display_top_sums[0][1] - display_top_sums[2][1])
            < bot_instance.PROB_DIFFERENCE_THRESHOLD
        ):
            top_sums_text = f"Top sums are too close in probability (difference between 1st and 3rd < `{bot_instance.PROB_DIFFERENCE_THRESHOLD*100:.2f}%`) to be meaningfully distinct."
        elif not display_top_sums:  # If display_top_sums is empty after filtering
            top_sums_text = "No prominent sums found or calculated."
        else:
            for i, (s, p) in enumerate(display_top_sums):
                top_sums_text += (
                    f" `{i+1}`. Total Soulstones: `{s}`, Chance: `{p*100:.4f}%`\n"
                )

        embed.add_field(
            name="🥇🥈🥉 Top 3 Most Likely Total Soulstones Counts",
            value=top_sums_text.strip(),
            inline=False,
        )

    # Use bot.owner_display_name for the footer
    owner_name = getattr(
        bot_instance, "owner_display_name", "Bot Owner"
    )  # Use owner_display_name
    embed.set_footer(
        text=f"Calculated by {bot_instance.user.name} • {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')} | Made by {owner_name}"
    )
    return embed


async def create_baginfo_embed(bot_instance):  # Now takes bot_instance
    bag1_info = "\n".join(
        [f"{v} SS ({p:.2%})" for v, p in bot_instance.BAG_I_DEFINITION]
    )
    bag2_info = "\n".join(
        [f"{v} SS ({p:.2%})" for v, p in bot_instance.BAG_II_DEFINITION]
    )

    avg_bag1, _ = get_bag_stats(bot_instance.BAG_I_DEFINITION)
    avg_bag2, _ = get_bag_stats(bot_instance.BAG_II_DEFINITION)

    embed = discord.Embed(
        title="🛍️ Bag Information",
        description="Details about the contents and probabilities of Bag I and Bag II.",
        color=discord.Color.purple(),
    )
    if bot_instance.user and bot_instance.user.display_avatar:
        embed.set_thumbnail(url=bot_instance.user.display_avatar.url)

    embed.add_field(
        name=f"Bag I Contents (Avg: {avg_bag1:.2f} SS)",
        value=bag1_info,
        inline=True,
    )
    embed.add_field(
        name=f"Bag II Contents (Avg: {avg_bag2:.2f} SS)",
        value=bag2_info,
        inline=True,
    )

    # Add owner to baginfo footer as well for consistency
    owner_name = getattr(bot_instance, "owner_display_name", "Bot Owner")
    embed.set_footer(
        text=f"Information provided by {bot_instance.user.name} • {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')} | Made by {owner_name}"
    )
    embed.set_timestamp()
    return embed


class Bags(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- Prefix Commands ---
    @commands.command(name="bags", description="Calculates soulstone probabilities.")
    @commands.cooldown(1, 10.0, commands.BucketType.user)  # Apply cooldown decorator
    async def bags_prefix(self, ctx, bag1: int, bag2: int, ss: int):
        logger.info(
            f"Prefix command 'bags' called by {ctx.author} ({ctx.author.id}) with args: bag1={bag1}, bag2={bag2}, ss={ss}"
        )

        if bag1 < 0 or bag2 < 0 or ss < 0:
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

        async with ctx.typing():  # Show typing indicator during calculation
            try:
                result_data, method_used = await asyncio.wait_for(
                    async_parser(self.bot, bag1, bag2, ss),
                    timeout=self.bot.CALCULATION_TIMEOUT,
                )
                prob_at_least_target, top_sums, prob_exact_target = result_data
                logger.info(
                    f"Calculation for {ctx.author.id} successful (method: {method_used})."
                )

                final_embed = await create_bags_embed(
                    self.bot,  # Pass bot instance
                    bag1,
                    bag2,
                    ss,
                    prob_at_least_target,
                    top_sums,
                    method_used,
                    prob_exact_target,
                )
                await ctx.send(embed=final_embed)

            except asyncio.TimeoutError:
                embed = discord.Embed(
                    title="⏰ Calculation Timeout",
                    description=f"The calculation took too long (more than `{self.bot.CALCULATION_TIMEOUT}` seconds) and was cancelled. Please try with smaller bag numbers.",
                    color=discord.Color.orange(),
                )
                await ctx.send(embed=embed)
                logger.warning(
                    f"Calculation for {ctx.author.id} timed out for 'bags' prefix command."
                )
            except ValueError as e:
                embed = discord.Embed(
                    title="❌ Calculation Error",
                    description=f"Input error: {e}",
                    color=discord.Color.red(),
                )
                await ctx.send(embed=embed)
                logger.error(
                    f"Value error for {ctx.author.id} in 'bags' prefix command: {e}"
                )
            except Exception as e:
                embed = discord.Embed(
                    title="⚠️ Unexpected Error",
                    description=f"An unexpected error occurred during calculation: `{e}`",
                    color=discord.Color.red(),
                )
                await ctx.send(embed=embed)
                logger.exception(
                    f"Unexpected error for {ctx.author.id} in 'bags' prefix command."
                )

    # --- Slash Commands ---
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

        # Defer the response immediately with thinking indicator
        await interaction.response.defer(
            ephemeral=False, thinking=True
        )  # Added thinking=True

        # Use local variable for display, not directly from bot.
        # This prevents calculation_method_display from changing mid-way if bot properties are modified.
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
                self.bot,  # Pass bot instance
                bag1,
                bag2,
                ss,
                prob_at_least_target,
                top_sums,
                method_used,
                prob_exact_target,
            )
            await interaction.edit_original_response(content=None, embed=final_embed)

        except asyncio.TimeoutError:
            embed = discord.Embed(
                title="⏰ Calculation Timeout",
                description=f"The calculation took too long (more than `{self.bot.CALCULATION_TIMEOUT}` seconds) and was cancelled. Please try with smaller bag numbers.",
                color=discord.Color.orange(),
            )
            await interaction.edit_original_response(content=None, embed=embed)
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
            await interaction.edit_original_response(content=None, embed=embed)
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
            await interaction.edit_original_response(content=None, embed=embed)
            logger.exception(
                f"Unexpected error for {interaction.user.id} in 'bags' slash command."
            )
            return

    @commands.command(
        name="baginfo",
        aliases=["bagdetails"],
        description="Displays information about Bag I and Bag II contents and their average values.",
    )
    # Apply cooldown decorator for prefix command
    @commands.cooldown(1, 5.0, commands.BucketType.user)
    async def baginfo_prefix(self, ctx):
        logger.info(
            f"Prefix command 'baginfo' called by {ctx.author} ({ctx.author.id})."
        )
        async with ctx.typing():
            embed = await create_baginfo_embed(self.bot)  # Pass bot instance
            await ctx.send(embed=embed)
            logger.info(f"Sent baginfo response to {ctx.author.id}.")

    @app_commands.command(
        name="baginfo", description="Displays information about Bag I and Bag II."
    )
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id))
    async def baginfo_slash(self, interaction: discord.Interaction):
        logger.info(
            f"Slash command 'baginfo' called by {interaction.user} ({interaction.user.id})."
        )
        # Defer the response with thinking indicator
        if not interaction.response.is_done():
            await interaction.response.defer(
                ephemeral=False, thinking=True
            )  # Added thinking=True

        embed = await create_baginfo_embed(self.bot)  # Pass bot instance
        await interaction.followup.send(embed=embed)
        logger.info(f"Sent baginfo response to {interaction.user.id}.")


async def setup(bot):
    await bot.add_cog(Bags(bot))
