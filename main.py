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


def draw_number(box_definition):
    """
    Draws a random number from a given box based on its defined probabilities.

    Args:
        box_definition (list of dict): A list of dictionaries, where each dict
                                    has 'value' (the number) and 'prob' (its probability).

    Returns:
        int: The drawn number.
    """
    rand = random.random()  # Generate a random number between 0 and 1
    cumulative_probability = 0

    # Iterate through the box items to find which number corresponds to the random value
    for item in box_definition:
        cumulative_probability += item[1]
        if rand < cumulative_probability:
            return item[0]

    # Fallback: In case of floating point inaccuracies, return the last value.
    # This should rarely be reached if probabilities sum exactly to 1.
    return box_definition[-1][0]


def run_simulation(
    box1_def, box2_def, draws_box1, draws_box2, target_sum, num_simulations
):
    """
    Runs the Monte Carlo simulation to estimate probabilities and collect sum frequencies.

    Args:
        box1_def (list of dict): Definition of Box 1 (values and probabilities).
        box2_def (list of dict): Definition of Box 2 (values and probabilities).
        draws_box1 (int): Number of draws from Box 1.
        draws_box2 (int): Number of draws from Box 2.
        target_sum (int): The sum that needs to be reached or exceeded for the primary calculation.
        num_simulations (int): The total number of simulation trials to run.

    Returns:
        tuple: A tuple containing:
            - estimated_probability_at_least_target (float): Probability of sum >= target_sum.
            - successful_outcomes (int): Count of sums >= target_sum.
            - top_3_sums (list of tuples): List of (sum, probability) for the top 3 most likely sums.
    """
    successful_outcomes = 0
    # Use Counter to efficiently store frequencies of all generated sums
    sum_frequencies = Counter()

    for _ in range(num_simulations):
        current_sum = 0

        # Draw from Box 1
        for _ in range(draws_box1):
            current_sum += draw_number(box1_def)

        # Draw from Box 2
        for _ in range(draws_box2):
            current_sum += draw_number(box2_def)

        # Record the current sum's frequency
        sum_frequencies[current_sum] += 1

        # Check if the sum meets the target for the primary calculation
        if current_sum >= target_sum:
            successful_outcomes += 1

    # Calculate probability for the primary target
    estimated_probability_at_least_target = (
        successful_outcomes / num_simulations
    ) * 100

    return (
        estimated_probability_at_least_target,
        successful_outcomes,
        sum_frequencies.most_common(3),
    )


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

    number_of_simulations = 1000000

    return run_simulation(
        box1_definition,
        box2_definition,
        num_draws_box1,
        num_draws_box2,
        target_sum_value,
        number_of_simulations,
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
            value=f" 1. Total Soulstones: {top_sums[0][0]}, Chance: {top_sums[0][1]/10000:.4f}%\n 2. Total Soulstones: {top_sums[1][0]}, Chance: {top_sums[1][1]/10000:.4f}%\n 3. Total Soulstones: {top_sums[2][0]}, Chance: {top_sums[2][1]/10000:.4f}%",
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
        value=f" 1. Total Soulstones: {top_sums[0][0]}, Chance: {top_sums[0][1]/10000:.4f}%\n 2. Total Soulstones: {top_sums[1][0]}, Chance: {top_sums[1][1]/10000:.4f}%\n 3. Total Soulstones: {top_sums[2][0]}, Chance: {top_sums[2][1]/10000:.4f}%",
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
