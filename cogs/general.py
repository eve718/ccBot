# cogs/general.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
import datetime
import discord.utils  # Added for utcnow()

# Import COMMAND_MENU from config.py
from config import COMMAND_MENU

logger = logging.getLogger("discord_bot")


async def create_welcome_embed():
    embed = discord.Embed(
        title="🤖 Welcome to the Command Menu!",
        description=(
            "Use the buttons below to navigate through different command categories. "
            "Click on a category to see its commands and usage instructions.\\n\\n"
            "**General Help:** If you need assistance with the bot or have questions, feel free to ask!"
        ),
        color=discord.Color.blue(),
    )
    embed.set_thumbnail(
        url="https://cdn.discordapp.com/attachments/1098656123019085885/1246241315668613140/rngBot.png?ex=666113b9&is=665fc239&hm=70a0d9f0b18206d289196b996160893026210f9a566580556e9c20a4b3f89025&"
    )  # Consider using bot.user.display_avatar.url here if available
    return embed


async def create_info_embed(bot_instance):
    embed = discord.Embed(
        title="ℹ️ Bot Information",
        description="Here's some information about me!",
        color=discord.Color.blue(),
    )
    if bot_instance.user and bot_instance.user.display_avatar:
        embed.set_thumbnail(url=bot_instance.user.display_avatar.url)

    embed.add_field(
        name="Developer", value=bot_instance.OWNER_DISPLAY_NAME, inline=True
    )

    # Check if bot_online_since is available before using it
    if hasattr(bot_instance, "bot_online_since") and bot_instance.bot_online_since:
        uptime = discord.utils.utcnow() - bot_instance.bot_online_since
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
        embed.add_field(name="Uptime", value=uptime_str, inline=True)
        embed.add_field(
            name="Online Since",
            value=bot_instance.bot_online_since.strftime("%Y-%m-%d %H:%M:%S UTC"),
            inline=False,
        )
    else:
        embed.add_field(
            name="Uptime",
            value="N/A (Bot online since data not available)",
            inline=True,
        )
        embed.add_field(name="Online Since", value="N/A", inline=False)

    embed.add_field(
        name="Latency", value=f"`{bot_instance.latency * 1000:.2f}ms`", inline=True
    )
    embed.add_field(
        name="Commands Synced",
        value=f"`{len(bot_instance.tree.get_commands())}`",
        inline=True,
    )
    embed.add_field(name="Library", value="`discord.py`", inline=True)
    embed.add_field(name="Version", value=f"`{discord.__version__}`", inline=True)
    embed.set_footer(text="Information last updated:")
    embed.timestamp = discord.utils.utcnow()  # Fixed: set_timestamp() -> timestamp
    return embed


class CommandMenuView(discord.ui.View):
    def __init__(self, bot_instance, timeout=180):
        super().__init__(timeout=timeout)
        self.bot_instance = bot_instance
        self.message = None
        self._add_command_buttons()  # Renamed for clarity

    def _add_command_buttons(self):  # Adjusted logic to add buttons for each command
        # Sort commands alphabetically by name for consistent display
        sorted_commands = sorted(COMMAND_MENU.items(), key=lambda item: item[0].lower())
        for cmd_name, cmd_info in sorted_commands:
            # Skip the 'menu' command itself to avoid recursion or odd display
            if cmd_name == "menu":
                continue

            button = discord.ui.Button(
                label=cmd_name.capitalize(),
                style=discord.ButtonStyle.primary,
                custom_id=f"menu_command_{cmd_name}",
                emoji=cmd_info.get("emoji"),
            )
            button.callback = self._button_callback  # Bind to the new callback name
            self.add_item(button)

    async def _button_callback(
        self, interaction: discord.Interaction
    ):  # Renamed callback
        await interaction.response.defer()

        # Fixed: Access custom_id from interaction.data for robustness
        if "custom_id" in interaction.data:
            command_name = interaction.data["custom_id"].replace("menu_command_", "")
        else:
            logger.error(
                f"Interaction data missing 'custom_id' for menu button: {interaction.data}"
            )
            await interaction.followup.send(
                "An unexpected error occurred with the menu. Please try again.",
                ephemeral=True,
            )
            return

        cmd_info = COMMAND_MENU.get(command_name)
        if not cmd_info:
            logger.warning(
                f"Attempted to access info for unknown command '{command_name}' via menu."
            )
            await interaction.followup.send(
                "Information for this command could not be found.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"{cmd_info.get('emoji', '')} {command_name.capitalize()} Command",
            description=cmd_info.get("description", "No description available."),
            color=discord.Color.blue(),
        )

        if "usage_prefix" in cmd_info:
            embed.add_field(
                name="Prefix Usage", value=cmd_info["usage_prefix"], inline=False
            )
        if "usage_slash" in cmd_info:
            embed.add_field(
                name="Slash Usage", value=cmd_info["usage_slash"], inline=False
            )

        embed.set_footer(
            text=f"Bot online since: {self.bot_instance.bot_online_since.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        embed.timestamp = discord.utils.utcnow()  # Fixed: set_timestamp() -> timestamp

        await self.message.edit(embed=embed, view=self)


class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ping", description="Checks the bot's latency.")
    async def ping_prefix(self, ctx):
        logger.info(f"Prefix command 'ping' called by {ctx.author} ({ctx.author.id}).")
        async with ctx.typing():
            latency_ms = round(self.bot.latency * 1000, 2)
            embed = discord.Embed(
                title="🏓 Pong!",
                description=f"Latency: `{latency_ms}ms`",
                color=discord.Color.green(),
            )
            await ctx.send(embed=embed)
            logger.info(f"Sent ping response to {ctx.author.id}.")

    @app_commands.command(name="ping", description="Checks the bot's latency.")
    async def ping_slash(self, interaction: discord.Interaction):
        logger.info(
            f"Slash command 'ping' called by {interaction.user} ({interaction.user.id})."
        )
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=True)
        latency_ms = round(self.bot.latency * 1000, 2)
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Latency: `{latency_ms}ms`",
            color=discord.Color.green(),
        )
        await interaction.followup.send(embed=embed)
        logger.info(f"Sent ping response to {interaction.user.id}.")

    @commands.command(
        name="info", description="Displays general information about the bot."
    )
    async def info_prefix(self, ctx):
        logger.info(f"Prefix command 'info' called by {ctx.author} ({ctx.author.id}).")
        async with ctx.typing():
            embed = await create_info_embed(self.bot)  # Pass bot instance
            await ctx.send(embed=embed)
            logger.info(f"Sent info response to {ctx.author.id}.")

    @app_commands.command(
        name="info", description="Displays general information about the bot."
    )
    async def info_slash(self, interaction: discord.Interaction):
        logger.info(
            f"Slash command 'info' called by {interaction.user} ({interaction.user.id})."
        )
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=True)
        embed = await create_info_embed(self.bot)  # Pass bot instance
        await interaction.followup.send(embed=embed)
        logger.info(f"Sent info response to {interaction.user.id}.")

    @commands.command(name="menu", description="Displays a list of available commands.")
    async def menu_prefix(self, ctx):
        logger.info(f"Prefix command 'menu' called by {ctx.author} ({ctx.author.id}).")
        async with ctx.typing():
            initial_embed = await create_welcome_embed()
            view = CommandMenuView(bot_instance=self.bot)
            message = await ctx.send(embed=initial_embed, view=view)
            view.message = message
            logger.info(f"Sent menu response to {ctx.author.id}.")

    @app_commands.command(
        name="menu", description="Displays a list of available commands."
    )
    async def menu_slash(self, interaction: discord.Interaction):
        logger.info(
            f"Slash command 'menu' called by {interaction.user} ({interaction.user.id})."
        )
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=True)
        initial_embed = await create_welcome_embed()
        view = CommandMenuView(bot_instance=self.bot)
        message = await interaction.followup.send(embed=initial_embed, view=view)
        view.message = message
        logger.info(f"Sent menu response to {interaction.user.id}.")


async def setup(bot):
    await bot.add_cog(General(bot))
