# -*- coding: utf-8 -*-
"""
Created on Sun May 25 23:24:13 2025

@author: utente
"""

import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import collections

from keep_alive import keep_alive

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
OWNER = os.getenv("OWNER_ID")

keep_alive()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


def calculate_exact_probabilities(box_def, num_draws):
    """
    Calculates the exact probability distribution of sums from a box using dynamic programming.

    Args:
        box_def (list of tuples): List of (value, probability) tuples.
        num_draws (int): Number of draws.

    Returns:
        dict: A dictionary where keys are sums and values are their exact probabilities.
    """
    # Initialize DP state: {sum: probability}
    # After 0 draws, sum is 0 with 100% probability
    current_probabilities = {0: 1.0}

    for _ in range(num_draws):
        next_probabilities = collections.defaultdict(
            float
        )  # Use defaultdict for easier accumulation
        for prev_sum, prev_prob in current_probabilities.items():
            for value, prob_of_value in box_def:
                new_sum = prev_sum + value
                new_prob = prev_prob * prob_of_value
                next_probabilities[new_sum] += new_prob
        current_probabilities = next_probabilities

    return current_probabilities


def run_exact_calculation(box1_def, box2_def, draws_box1, draws_box2, target_sum):
    # Calculate probabilities for Box 1 sums
    box1_sums_probs = calculate_exact_probabilities(box1_def, draws_box1)

    # Calculate probabilities for Box 2 sums
    box2_sums_probs = calculate_exact_probabilities(box2_def, draws_box2)

    # Combine probabilities from Box 1 and Box 2 draws
    combined_sums_probs = collections.defaultdict(float)
    for sum1, prob1 in box1_sums_probs.items():
        for sum2, prob2 in box2_sums_probs.items():
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


def parser(num_draws_box1, num_draws_box2, target_sum_value):
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

    return run_exact_calculation(
        box1_definition,
        box2_definition,
        num_draws_box1,
        num_draws_box2,
        target_sum_value,
    )


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged on as {bot.user}!")


@bot.event
async def on_message(message):
    if message.author.id == bot.user.id:
        return

    content = message.content
    if content[0:8] == "!chance ":
        info = content[8:].split(",")

        if len(info) != 3:
            embed = discord.Embed(
                title="",
                description="Wrong input. It should be like this:",
                color=discord.Color.red(),
            )
            embed.add_field(
                name="!chance [number of bags I], [number of bags II], [soulstones goal]",
                value="",
            )
            await message.channel.send(embed=embed)
            return

        for i in range(3):
            tmp = info[i].strip()

            if tmp.isnumeric() and int(tmp) >= 0:
                info[i] = int(tmp)
            else:
                embed = discord.Embed(
                    title="",
                    description="Wrong input. It should be like this:",
                    color=discord.Color.red(),
                )
                embed.add_field(
                    name="!chance [number of bags I], [number of bags II], [soulstones goal]",
                    value="",
                )
                await message.channel.send(embed=embed)
                return

        prob_at_least_target, successful_count, top_sums = parser(
            info[0], info[1], info[2]
        )

        if not top_sums:
            embed = discord.Embed(
                title="",
                description="Something went wrong",
                color=discord.Color.red(),
            )
            await message.channel.send(embed=embed)
            return

        embed = discord.Embed(
            title="",
            description="",
            color=discord.Color.red(),
        )
        embed.add_field(
            name="--- Parameters ---",
            value=f"Bag I Draws: {info[0]}\nBag II Draws: {info[1]}\nTarget Soulstones (at least): {info[2]}",
            inline=False,
        )
        embed.add_field(
            name="--- Pre-results ---",
            value=f"Average Soulstones Expected: {3.75*info[0]+18.95*info[1]}",
            inline=False,
        )
        embed.add_field(
            name="--- Results ---",
            value=f"Probability of Soulstones being at least {info[2]}: {prob_at_least_target:.4f}%",
            inline=False,
        )
        embed.add_field(
            name="--- Three Most Likely Total Soulstones Count and Their Chances ---",
            value=f" 1. Total Soulstones: {top_sums[0][0]}, Chance: {top_sums[0][1]*100:.4f}%\n 2. Total Soulstones: {top_sums[1][0]}, Chance: {top_sums[1][1]*100:.4f}%\n 3. Total Soulstones: {top_sums[2][0]}, Chance: {top_sums[2][1]*100:.4f}%",
            inline=False,
        )
        embed.add_field(
            name="",
            value=f"Bot made by <@{OWNER}>",
            inline=False,
        )
        await message.channel.send(embed=embed)


@bot.tree.command(
    name="chance",
    description=f"Will calc the chance to obtain at least [ss] soulstones from [bag1] bags I plus [bag2] bags II",
)
async def chance(interaction: discord.Interaction, bag1: int, bag2: int, ss: int):
    await interaction.response.defer()

    prob_at_least_target, successful_count, top_sums = parser(bag1, bag2, ss)
    if not top_sums:
        embed = discord.Embed(
            title="",
            description="Something went wrong",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed)
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
    embed.add_field(
        name="--- Results ---",
        value=f"Probability of Soulstones being at least {ss}: {prob_at_least_target:.4f}%",
        inline=False,
    )
    embed.add_field(
        name="--- Three Most Likely Total Soulstones Count and Their Chances ---",
        value=f" 1. Total Soulstones: {top_sums[0][0]}, Chance: {top_sums[0][1]*100:.4f}%\n 2. Total Soulstones: {top_sums[1][0]}, Chance: {top_sums[1][1]*100:.4f}%\n 3. Total Soulstones: {top_sums[2][0]}, Chance: {top_sums[2][1]*1000:.4f}%",
        inline=False,
    )
    embed.add_field(
        name="",
        value=f"Bot made by <@{OWNER}>",
        inline=False,
    )
    await asyncio.sleep(delay=0)
    await interaction.followup.send(embed=embed)


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
        name=" 1. !chance [number of bags I], [number of bags II], [soulstones goal]",
        value="This will calc the chance to obtain at least [soulstones goal] soulstones from [number of bags I] bags I plus [number of bags II] bags II",
        inline=False,
    )

    await guild.system_channel.send(embed=embed)


# @client.tree.command(name="hello", description="Say hello!", guild=GUILD_ID)
# async def sayHello(interaction: discord.Interaction):
#    await interaction.response.send_message("Hi there!")


# @client.tree.command(
#    name="printer", description="I will print whatever you give me!", guild=GUILD_ID
# )
# async def printer(interaction: discord.Interaction, printer: str):
#    await interaction.response.send_message(printer)


# @client.tree.command(name="embed", description="Embed demo!", guild=GUILD_ID)
# async def embed(interaction: discord.Interaction):
#    embed = discord.Embed(
#        title="I am a Title",
#        url="https://google.com",
#        description="I am the description",
#        color=discord.Color.red(),
#    )
#    embed.set_thumbnail(
#        url="https://www.androidp1.com/uploads/posts/2022-01/castle-clash-guild-royale.webp"
#    )
#    embed.add_field(name="Field 1 Title", value="Description of Field 1", inline=False)
#    embed.add_field(name="Field 2 Title", value="Description of Field 2")
#    embed.add_field(name="Field 3 Title", value="Description of Field 3")
#    embed.set_footer(text="This is the footer!")
#    await interaction.response.send_message(embed=embed)


# @client.tree.command(
#    name="creator", description="Prints creator of the bot", guild=GUILD_ID
# )
# async def creator(interaction: discord.Interaction):
#    await interaction.response.send_message(f"<@{OWNER_ID}>")


# class View(discord.ui.View):
#    @discord.ui.button(label="Click me!", style=discord.ButtonStyle.red, emoji="🔥")
#    async def button_callback(self, button, interaction):
#        await button.response.send_message("You have clicked the button!")


# @client.tree.command(name="button", description="Displaying a button", guild=GUILD_ID)
# async def myButton(interaction: discord.Interaction):
#    await interaction.response.send_message(view=View())


bot.run(TOKEN)
