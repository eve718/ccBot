# cogs/bags.py

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import collections
import logging
import discord.utils  # Added for utcnow()

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
        value=f"**Bag I Draws:** `{bag1}`\\n**Bag II Draws:** `{bag2}`\\n**Target Soulstones (at least):** `{ss}`",
        inline=False,
    )

    box1_exp_val = sum(val * prob for val, prob in bot_instance.BAG_I_DEFINITION)
    box2_exp_val = sum(val * prob for val, prob in bot_instance.BAG_II_DEFINITION)
    total_expected_value = (box1_exp_val * bag1) + (box2_exp_val * bag2)

    embed.add_field(
        name="Expected Soulstones",
        value=f"`{total_expected_value:.2f}`",
        inline=True,
    )

    if method_used == "exact":
        embed.add_field(
            name="Method Used", value="`Exact Probability Calculation`", inline=True
        )
        prob_display = f"`{prob_at_least_target:.4f}`"
        if prob_exact_target is not None:
            prob_display += f" (Exact: `{prob_exact_target:.4f}`)"
        embed.add_field(
            name="Probability (at least target)", value=prob_display, inline=False
        )

        if top_sums:
            top_sums_str = "\n".join(
                [f" `{s}`: `{p:.4f}`" for s, p in top_sums.items()]
            )
            embed.add_field(
                name="Top Sums & Probabilities", value=top_sums_str, inline=False
            )
    else:  # Normal approximation
        embed.add_field(name="Method Used", value="`Normal Approximation`", inline=True)
        embed.add_field(
            name="Probability (at least target)",
            value=f"`{prob_at_least_target:.4f}`",
            inline=False,
        )
        if prob_exact_target is not None:
            embed.add_field(
                name="Probability (exact target)",
                value=f"`{prob_exact_target:.4f}`",
                inline=False,
            )

    embed.set_footer(
        text=f"Calculated by RNGesus | Data from {bot_instance.OWNER_DISPLAY_NAME}"
    )
    embed.timestamp = discord.utils.utcnow()  # Fixed: set_timestamp() -> timestamp
    return embed


async def create_baginfo_embed(bot_instance):
    embed = discord.Embed(
        title="🛍️ Bag Information",
        description="Detailed information about the contents and averages of Bag I and Bag II.",
        color=discord.Color.gold(),
    )
    if bot_instance.user and bot_instance.user.display_avatar:
        embed.set_thumbnail(url=bot_instance.user.display_avatar.url)

    # Calculate statistics for Bag I
    bag1_definition = bot_instance.BAG_I_DEFINITION
    bag1_stats = get_bag_stats(bag1_definition)
    embed.add_field(
        name="Bag I Contents & Stats",
        value=(
            f"**Contents:** {', '.join([f'{val} SS ({int(prob*100)}%)' for val, prob in bag1_definition])}\n"
            f"**Expected Value:** `{bag1_stats['expected_value']:.2f}`\n"
            f"**Variance:** `{bag1_stats['variance']:.2f}`\n"
            f"**Standard Deviation:** `{bag1_stats['std_dev']:.2f}`"
        ),
        inline=False,
    )

    # Calculate statistics for Bag II
    bag2_definition = bot_instance.BAG_II_DEFINITION
    bag2_stats = get_bag_stats(bag2_definition)
    embed.add_field(
        name="Bag II Contents & Stats",
        value=(
            f"**Contents:** {', '.join([f'{val} SS ({int(prob*100)}%)' for val, prob in bag2_definition])}\n"
            f"**Expected Value:** `{bag2_stats['expected_value']:.2f}`\n"
            f"**Variance:** `{bag2_stats['variance']:.2f}`\n"
            f"**Standard Deviation:** `{bag2_stats['std_dev']:.2f}`"
        ),
        inline=False,
    )

    embed.set_footer(text=f"Data provided by {bot_instance.OWNER_DISPLAY_NAME}")
    embed.timestamp = discord.utils.utcnow()  # Fixed: set_timestamp() -> timestamp
    return embed


class Bags(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        name="bags",
        description="Calculates soulstone probabilities from bag draws.",
        usage="<bag I count> <bag II count> <target soulstones>",
    )
    @commands.cooldown(1, 10.0, commands.BucketType.user)
    async def bags_prefix(self, ctx, bag1: int, bag2: int, ss: int):
        logger.info(
            f"Prefix command 'bags' called by {ctx.author} ({ctx.author.id}) with args: bag1={bag1}, bag2={bag2}, ss={ss}"
        )
        if bag1 < 0 or bag2 < 0 or ss < 0:
            await ctx.send("Bag counts and target soulstones cannot be negative.")
            logger.warning(
                f"Negative input by {ctx.author.id}: bag1={bag1}, bag2={bag2}, ss={ss}"
            )
            return

        async with ctx.typing():
            try:
                prob_at_least_target, top_sums, method_used, prob_exact_target = (
                    await asyncio.wait_for(
                        async_parser(self.bot, bag1, bag2, ss),
                        timeout=self.bot.CALCULATION_TIMEOUT,
                    )
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
                await ctx.send(embed=final_embed)
                logger.info(
                    f"Calculation for {ctx.author.id} successful (method: {method_used})."
                )

            except asyncio.TimeoutError:
                error_embed = discord.Embed(
                    title="⏰ Calculation Timeout",
                    description=(
                        "The calculation is taking too long. Please try with smaller bag counts. "
                        "Exact calculation might be too complex for these inputs."
                    ),
                    color=discord.Color.orange(),
                )
                await ctx.send(embed=error_embed)
                logger.warning(
                    f"Calculation timed out for {ctx.author.id} with bag1={bag1}, bag2={bag2}, ss={ss}."
                )
            except ValueError as e:
                error_embed = discord.Embed(
                    title="❌ Input Error",
                    description=str(e),
                    color=discord.Color.red(),
                )
                await ctx.send(embed=error_embed)
                logger.error(f"Input error for {ctx.author.id}: {e}")
            except Exception as e:
                error_embed = discord.Embed(
                    title="⚠️ An Error Occurred",
                    description=f"An unexpected error occurred during calculation: `{e}`",
                    color=discord.Color.red(),
                )
                await ctx.send(embed=error_embed)
                logger.exception(
                    f"Unexpected error for {ctx.author.id} in 'bags' prefix command."
                )

    @app_commands.command(
        name="bags", description="Calculates soulstone probabilities from bag draws."
    )
    @app_commands.describe(
        bag1="Number of draws from Bag I",
        bag2="Number of draws from Bag II",
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
                description="Bag counts and target soulstones cannot be negative.",
                color=discord.Color.red(),
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
            logger.warning(
                f"Negative input by {interaction.user.id}: bag1={bag1}, bag2={bag2}, ss={ss}"
            )
            return

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=True)

        try:
            prob_at_least_target, top_sums, method_used, prob_exact_target = (
                await asyncio.wait_for(
                    async_parser(self.bot, bag1, bag2, ss),
                    timeout=self.bot.CALCULATION_TIMEOUT,
                )
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
            await interaction.followup.send(content=None, embed=final_embed)
            logger.info(
                f"Calculation for {interaction.user.id} successful (method: {method_used})."
            )

        except asyncio.TimeoutError:
            embed = discord.Embed(
                title="⏰ Calculation Timeout",
                description=(
                    "The calculation is taking too long. Please try with smaller bag counts. "
                    "Exact calculation might be too complex for these inputs."
                ),
                color=discord.Color.orange(),
            )
            await interaction.edit_original_response(content=None, embed=embed)
            logger.warning(
                f"Calculation timed out for {interaction.user.id} with bag1={bag1}, bag2={bag2}, ss={ss}."
            )
        except ValueError as e:
            embed = discord.Embed(
                title="❌ Input Error", description=str(e), color=discord.Color.red()
            )
            await interaction.edit_original_response(content=None, embed=embed)
            logger.error(f"Input error for {interaction.user.id}: {e}")
        except Exception as e:
            embed = discord.Embed(
                title="⚠️ An Error Occurred",
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
